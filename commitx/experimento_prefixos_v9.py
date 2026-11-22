"""Experimento V9: texto completo com prefixos e n-gramas de caracteres.

Somente rotulos existentes da particao treino. 5 folds fixos agrupados
por repositorio e titulo. Nao consulta validacao externa nem teste reservado,
nao usa pseudorrotulos e nao modifica qualquer modelo anterior.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .academico import _modelo
from .comparacao_prefixos import CLASSES, prefixo, raw_titles
from .experimento_v3 import carregar_treino, componentes

NOMES = (
    "titulo_prefixo_palavras",
    "titulo_prefixo_misto_1a1",
    "titulo_prefixo_misto_2a1",
    "titulo_prefixo_palavras_c03",
)


def palavras():
    return TfidfVectorizer(
        ngram_range=(1, 2), strip_accents="unicode",
        sublinear_tf=True, max_features=50000,
    )


def caracteres():
    return TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5),
        strip_accents="unicode", sublinear_tf=True, max_features=30000,
    )


def modelo(nome):
    if nome == "titulo_prefixo_palavras":
        return _modelo()
    if nome == "titulo_prefixo_palavras_c03":
        return Pipeline([
            ("tfidf", palavras()),
            ("model", LinearSVC(C=0.3, class_weight="balanced", random_state=42)),
        ])
    if nome in ("titulo_prefixo_misto_1a1", "titulo_prefixo_misto_2a1"):
        peso_palavras = 1.0 if nome.endswith("1a1") else 2.0
        return Pipeline([
            ("tfidf", FeatureUnion(
                [("palavras", palavras()), ("caracteres", caracteres())],
                transformer_weights={
                    "palavras": peso_palavras,
                    "caracteres": 1.0,
                },
            )),
            ("model", LinearSVC(
                C=1.0, class_weight="balanced", random_state=42,
            )),
        ])
    raise ValueError("Modelo desconhecido: " + nome)


def avaliar(registros, titulos, saida, n_folds=5):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Pasta ja existe; escolha outra saida")
    if len(registros) < 30 or not 3 <= n_folds <= 8:
        raise ValueError("Quantidade de dados/folds invalida")
    ids = [r["id"] for r in registros]
    if len(set(ids)) != len(ids) or set(ids) != set(titulos):
        raise ValueError("IDs de treino ausentes ou repetidos")
    x = [titulos[uid] for uid in ids]
    if any(not t for t in x):
        raise ValueError("Titulo vazio")
    y = np.asarray([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Treino deve incluir as cinco classes")
    grupos = componentes(registros)
    if len(set(grupos)) < n_folds:
        raise ValueError("Grupos insuficientes para os folds")
    cortes = list(StratifiedGroupKFold(
        n_splits=n_folds, shuffle=True, random_state=42,
    ).split(np.zeros(len(y)), y, grupos))

    # Folds, classe-alvo e dados sao identicos em todos os modelos.
    oof = {nome: [None] * len(x) for nome in NOMES}
    for tr, va in cortes:
        if set(grupos[tr]) & set(grupos[va]):
            raise ValueError("Sobreposicao de grupos treino/validacao")
        if set(y[tr]) != set(CLASSES):
            raise ValueError("Fold de treino sem classe valida")
        xt = [x[int(i)] for i in tr]
        xv = [x[int(i)] for i in va]
        for nome in NOMES:
            m = modelo(nome)
            m.fit(xt, y[tr])
            previsao = m.predict(xv)
            for indice, cat in zip(va, previsao):
                i = int(indice)
                if oof[nome][i] is not None:
                    raise ValueError("Registro previsto duas vezes")
                oof[nome][i] = str(cat)
    if any(v is None for row in oof.values() for v in row):
        raise ValueError("Predicao OOF incompleta")

    metricas = {}
    for nome in NOMES:
        previsto = oof[nome]
        metricas[nome] = {
            "acertos": sum(a == b for a, b in zip(y, previsto)),
            "acuracia": round(float(accuracy_score(y, previsto)), 4),
            "macro_f1": round(float(f1_score(
                y, previsto, labels=CLASSES, average="macro", zero_division=0,
            )), 4),
            "recall_por_classe": {
                cat: round(float(recall_score(
                    y, previsto, labels=[cat], average="macro", zero_division=0,
                )), 4) for cat in CLASSES
            },
            "confusao": confusion_matrix(y, previsto, labels=CLASSES).tolist(),
        }

    # Sinal de prefixo declarado apenas como diagnostico, nunca rótulo.
    prefixos = [prefixo(t) for t in x]
    resumo = {
        "protocolo": "v9-treino-prefixos-caracteres-folds-agrupados",
        "total_treino": len(x),
        "grupos_independentes": len(set(grupos)),
        "folds": n_folds,
        "classes": list(CLASSES),
        "com_prefixo_reconhecido": sum(bool(t) for t in prefixos),
        "prefixos_divergentes_dos_rotulos": sum(
            bool(t) and t != classe for t, classe in zip(prefixos, y)
        ),
        "metricas": metricas,
        "restricoes": [
            "Somente registros e titulos da particao TREINO antiga.",
            "Nenhum dado do teste externo, V5 ou reservado usado.",
            "Nenhum modelo nem rotulo existente foi alterado.",
            "Resultados exploratorios OOF, nao acuracia externa comprovada.",
            "Rotulos antigos podem ter recebido assistencia por IA.",
            "Selecionar modelo pela mesma OOF repetidamente aumenta o risco de sobreajuste.",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (saida / "previsoes_oof.csv").open(
        "x", encoding="utf-8", newline=""
    ) as arq:
        campos = [
            "id", "titulo", "rotulo_registrado", "prefixo_declarado", *NOMES,
        ]
        writer = csv.DictWriter(arq, fieldnames=campos)
        writer.writeheader()
        for i, uid in enumerate(ids):
            writer.writerow({
                "id": uid,
                "titulo": x[i],
                "rotulo_registrado": str(y[i]),
                "prefixo_declarado": prefixos[i],
                **{nome: oof[nome][i] for nome in NOMES},
            })

    md = [
        "# CommitX — V9 prefixos e n-gramas de caracteres",
        "",
        f"- Treino: {len(x)} rótulos (nao sao os 97 mil commits).",
        f"- Grupos independentes: {len(set(grupos))}.",
        f"- Prefixos reconhecidos: {resumo['com_prefixo_reconhecido']}.",
        f"- Prefixos divergentes: {resumo['prefixos_divergentes_dos_rotulos']}.",
        "",
        "| Variante | Acuracia OOF | Macro-F1 OOF | Acertos |",
        "|---|---:|---:|---:|",
    ]
    for nome in NOMES:
        m = metricas[nome]
        md.append(f"| {nome} | {m['acuracia']:.1%} | "
                  f"{m['macro_f1']:.3f} | {m['acertos']}/{len(x)} |")
    md += [
        "", "## Recall por classe", "",
        "| Classe | Palavras | Misto 1:1 | Misto 2:1 | Palavras C=0.3 |",
        "|---|---:|---:|---:|---:|",
    ]
    for classe in CLASSES:
        md.append("| " + classe + " | " + " | ".join(
            f"{metricas[nome]['recall_por_classe'][classe]:.1%}"
            for nome in NOMES
        ) + " |")
    md += [
        "", "## Limites",
        "- Comparacao apenas interna usando rótulos antigos.",
        "- Nao substituir resultado do teste externo por esta OOF.",
        "- Nao classificar 97 mil como acertos comprovados.",
        "- Comparar macro-F1 e recall por classe, nao somente acuracia.",
        "- Caso uma variante melhore, validar depois em novos repositorios.",
    ]
    (saida / "relatorio.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8",
    )
    return resumo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--entrada", default="resultados/preparacao-inicial/commits_preparados.csv",
    )
    p.add_argument("--saida", default="resultados/comparacao-v9-prefixos-01")
    p.add_argument("--folds", type=int, default=5)
    args = p.parse_args(argv)
    try:
        registros = carregar_treino()
        titulos = raw_titles(args.entrada, {r["id"] for r in registros})
        resumo = avaliar(registros, titulos, args.saida, args.folds)
    except (OSError, ValueError, csv.Error) as erro:
        p.error(str(erro))
    for nome, m in resumo["metricas"].items():
        print(f"{nome}: {m['acuracia']:.1%} | macro-F1 {m['macro_f1']:.3f} "
              f"| {m['acertos']}/{resumo['total_treino']}")
    print("Relatorio:", Path(args.saida) / "relatorio.md")


if __name__ == "__main__":
    main()
