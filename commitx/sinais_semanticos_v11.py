"""V11: teste controlado de sinais semanticos docs/refactor em treino existente.

Os sinais sao recursos do modelo, NAO regras que forcam rotulos.
Todos os testes sao exploratorios, em cinco folds agrupados e congelados.
Nenhum teste externo, rótulo reservado, modelo persistido ou SQLite é alterado.
"""
import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .comparacao_prefixos import CLASSES, prefixo, raw_titles
from .experimento_v3 import carregar_treino, componentes
from .foco_docs_refactor_v10 import pesos_do_fold

# Indicadores definidos ANTES de executar a V11. Nao sao rotulos definitivos.
TERMS = {
    "docs": (
        r"\b(?:docs?|documentation|readme|changelog|guide|tutorial|"
        r"docstring|docstrings|comments?|typos?|spelling|grammar|"
        r"wording|examples?|explain|clarify|descriptions?)\b",
    ),
    "refactor": (
        r"\b(?:refactor(?:ing|ed)?|restructure|reorganize|"
        r"rename|renamed|extract|extracting|simplify|cleanup|clean up|"
        r"consolidate|migrate|migration|move|rework|reformat|"
        r"indentation|deprecated|deprecate|remove unused)\b",
    ),
}
PATTERNS = {key: re.compile(text, re.I) for key, text in TERMS.items()}
VARIANTES = {
    "base_v10": 0.0,
    "sinais_leves": 0.5,
    "sinais_moderados": 1.0,
}


class SinaisSemanticos(BaseEstimator, TransformerMixin):
    """Extrae dois indicadores binarios. Sem classificar nem olhar os rotulos."""
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        data = [
            [float(bool(PATTERNS["docs"].search(text))),
             float(bool(PATTERNS["refactor"].search(text)))]
            for text in X
        ]
        return csr_matrix(np.asarray(data, dtype=np.float64))


def modelo(pesos, intensidade):
    palavras = TfidfVectorizer(
        ngram_range=(1, 2), strip_accents="unicode",
        sublinear_tf=True, max_features=50000,
    )
    if intensidade:
        features = FeatureUnion([
            ("palavras", palavras),
            ("sinais", SinaisSemanticos()),
        ], transformer_weights={"palavras": 1.0, "sinais": intensidade})
    else:
        features = palavras
    return Pipeline([
        ("tfidf", features),
        ("model", LinearSVC(
            C=0.3, class_weight=pesos, random_state=42,
        )),
    ])


def executar(registros, titulos, saida, folds=5):
    destino = Path(saida)
    if destino.exists() or destino.is_symlink():
        raise FileExistsError(f"Saida existente: {destino}")
    ids = [r["id"] for r in registros]
    if len(ids) < 30 or len(ids) != len(set(ids)) or set(ids) != set(titulos):
        raise ValueError("Treino invalido, incompleto ou com IDs repetidos")
    if not (3 <= folds <= 8):
        raise ValueError("Numero de folds invalido")
    y = np.asarray([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Cinco classes obrigatorias no treino")
    x = [titulos[uid] for uid in ids]
    if any(not t.strip() for t in x):
        raise ValueError("Titulo vazio")
    grupos = componentes(registros)
    if len(set(grupos)) < folds:
        raise ValueError("Grupos insuficientes")
    cuts = list(StratifiedGroupKFold(
        n_splits=folds, shuffle=True, random_state=42,
    ).split(np.zeros(len(x)), y, grupos))
    saidas = {n: [None] * len(x) for n in VARIANTES}
    for it, iv in cuts:
        if set(grupos[it]) & set(grupos[iv]):
            raise ValueError("Vazamento de grupos")
        if set(y[it]) != set(CLASSES):
            raise ValueError("Fold nao contem todas as classes no treino")
        pesos = pesos_do_fold(y[it], 1.75, 1.50)
        for nome, intensidade in VARIANTES.items():
            m = modelo(pesos, intensidade)
            m.fit([x[int(j)] for j in it], y[it])
            p = m.predict([x[int(j)] for j in iv])
            for j, v in zip(iv, p):
                idx = int(j)
                if saidas[nome][idx] is not None:
                    raise ValueError("Previsao duplicada")
                saidas[nome][idx] = str(v)
    if any(v is None for pred in saidas.values() for v in pred):
        raise ValueError("OOF incompleto")
    metricas = {}
    for nome, pred in saidas.items():
        prec, rec, f1, support = precision_recall_fscore_support(
            y, pred, labels=CLASSES, zero_division=0,
        )
        metricas[nome] = {
            "acertos": sum(str(real) == previsto for real, previsto in zip(y, pred)),
            "acuracia": round(float(accuracy_score(y, pred)), 4),
            "macro_f1": round(float(f1_score(
                y, pred, labels=CLASSES, average="macro", zero_division=0,
            )), 4),
            "classes": {
                classe: {
                    "precision": round(float(prec[i]), 4),
                    "recall": round(float(rec[i]), 4),
                    "f1": round(float(f1[i]), 4),
                    "suporte": int(support[i]),
                } for i, classe in enumerate(CLASSES)
            },
        }
    conflitos = [
        i for i, texto in enumerate(x)
        if prefixo(texto) and prefixo(texto) != str(y[i])
    ]
    mudou = [
        i for i in range(len(x)) if any(
            saidas[n][i] != saidas["base_v10"][i]
            for n in VARIANTES if n != "base_v10"
        )
    ]
    resumo = {
        "protocolo": "v11-train-only-sinais-semanticos-exploratorio",
        "treino": len(ids),
        "grupos": len(set(grupos)),
        "folds": folds,
        "prefixos_conflitantes": len(conflitos),
        "mudancas_nas_previsoes": len(mudou),
        "metricas": metricas,
        "observacoes": [
            "Sinais semanticos sao pistas, nao rotulos forcados.",
            "Mesmo treino antigo V5 para todas as variantes; teste externo nao usado.",
            "Comparacoes repetidas na mesma OOF podem causar sobreajuste.",
            "Conflitos de prefixo nao sao prova de rotulo incorreto.",
            "Sem alteracoes em banco, rotulos ou modelos persistidos.",
        ],
    }
    destino.mkdir(parents=True, exist_ok=False)
    (destino / "resumo.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    def row(i):
        return {
            "id": ids[i],
            "titulo": x[i],
            "rotulo_registrado": str(y[i]),
            "prefixo_declarado": prefixo(x[i]),
            "sinal_docs": int(bool(PATTERNS["docs"].search(x[i]))),
            "sinal_refactor": int(bool(PATTERNS["refactor"].search(x[i]))),
            **{nome: saidas[nome][i] for nome in VARIANTES},
        }
    cols = [
        "id", "titulo", "rotulo_registrado", "prefixo_declarado",
        "sinal_docs", "sinal_refactor", *VARIANTES,
    ]
    for arquivo, indices in (
        ("previsoes_oof.csv", range(len(ids))),
        ("mudancas.csv", mudou),
        ("conflitos_para_auditoria.csv", conflitos),
    ):
        with (destino / arquivo).open("x", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(row(i) for i in indices)
    md = [
        "# CommitX V11 — docs/refactor com sinais semanticos",
        "",
        f"Treino: {len(ids)} | grupos: {len(set(grupos))} | folds: {folds}",
        f"Conflitos de prefixo para auditoria: {len(conflitos)}",
        f"Titulos com mudanca de previsao: {len(mudou)}",
        "",
        "| Variante | Acuracia | Macro-F1 | docs recall/precision | refactor recall/precision |",
        "|---|---:|---:|---|---|",
    ]
    for nome, m in metricas.items():
        d = m["classes"]["docs"]
        r = m["classes"]["refactor"]
        md.append(
            f"| {nome} | {m['acuracia']:.1%} | {m['macro_f1']:.3f} "
            f"| {d['recall']:.1%} / {d['precision']:.1%} "
            f"| {r['recall']:.1%} / {r['precision']:.1%} |"
        )
    md += [
        "",
        "## Proximo passo",
        "- Verifique mudancas.csv e conflitos_para_auditoria.csv.",
        "- Nao mude rotulos automaticamente; titulo pode ser ambiguo.",
        "- Nao use teste externo ja consultado para escolher variante.",
        "- Escolha final requer avaliacao cega em repositorios novos.",
    ]
    (destino / "relatorio.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8",
    )
    return resumo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", default="resultados/preparacao-inicial/commits_preparados.csv")
    p.add_argument("--saida", default="resultados/comparacao-v11-sinais-01")
    a = p.parse_args(argv)
    try:
        treino = carregar_treino()
        titulos = raw_titles(a.entrada, {r["id"] for r in treino})
        resumo = executar(treino, titulos, a.saida)
    except (ValueError, OSError, csv.Error) as exc:
        p.error(str(exc))
    for nome, m in resumo["metricas"].items():
        d, r = m["classes"]["docs"], m["classes"]["refactor"]
        print(
            f"{nome}: acc {m['acuracia']:.1%} | macro-F1 {m['macro_f1']:.3f} | "
            f"docs R {d['recall']:.1%} | refactor R {r['recall']:.1%}"
        )
    print("Relatorio:", Path(a.saida) / "relatorio.md")
    print("Conflitos:", Path(a.saida) / "conflitos_para_auditoria.csv")


if __name__ == "__main__":
    main()
