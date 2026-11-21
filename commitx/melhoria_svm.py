"""Comparacao controlada: SVM original versus TF-IDF palavras + caracteres.

Somente rotulos da particao TREINO antiga via carregar_treino().
Nunca consulta a avaliacao externa V1, a validacao V5 ou o teste reservado.
Nao modifica SQLite, rotulos, modelos existentes nem previsoes dos 97 mil.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .academico import _modelo as modelo_original
from .experimento_v3 import carregar_treino, componentes
from .treino_real import ENTRADA, BANCO, CATEGORIAS_VALIDAS

CLASSES = tuple(CATEGORIAS_VALIDAS)


def modelo_palavras_caracteres():
    """Mesmo classificador do original, acrescentando n-gramas de caracteres."""
    return Pipeline([
        ("tfidf", FeatureUnion([
            ("palavras", TfidfVectorizer(
                ngram_range=(1, 2), strip_accents="unicode",
                sublinear_tf=True, max_features=50000)),
            ("caracteres", TfidfVectorizer(
                analyzer="char_wb", ngram_range=(3, 5),
                strip_accents="unicode", sublinear_tf=True, max_features=30000)),
        ])),
        ("model", LinearSVC(class_weight="balanced", random_state=42, C=1.0)),
    ])


def comparar(registros, saida, folds=5):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Pasta ja existe; informe uma saida nova: " + str(saida))
    if not 3 <= folds <= 8:
        raise ValueError("Use de 3 a 8 folds")
    if len(registros) < 30:
        raise ValueError("Treinamento insuficiente: minimo 30 registros")
    ids = [r["id"] for r in registros]
    if len(set(ids)) != len(ids):
        raise ValueError("IDs duplicados no treino")
    titulos = [r["titulo"].strip() for r in registros]
    if not all(titulos):
        raise ValueError("Titulo vazio no treino")
    y = np.asarray([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Treinamento deve conter as cinco categorias")
    grupos = componentes(registros)
    if len(set(grupos)) < folds:
        raise ValueError("Grupos independentes insuficientes")

    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=42)
    cortes = list(cv.split(np.zeros(len(registros)), y, grupos))
    previsoes = {"original": [None] * len(registros),
                 "palavras_caracteres": [None] * len(registros)}
    contagens_folds = []

    # Congelamos as duas configuracoes antes de olhar as previsoes de cada fold.
    for numero, (treino, verificacao) in enumerate(cortes, 1):
        if set(grupos[treino]) & set(grupos[verificacao]):
            raise ValueError("Vazamento de repositorios/titulos entre treino e verificacao")
        if set(y[treino]) != set(CLASSES):
            raise ValueError("Fold sem todas as classes no treino; reduza os folds")
        xt = [titulos[int(i)] for i in treino]
        xv = [titulos[int(i)] for i in verificacao]
        for nome, modelo in (
            ("original", modelo_original()),
            ("palavras_caracteres", modelo_palavras_caracteres()),
        ):
            modelo.fit(xt, y[treino])
            for indice, prev in zip(verificacao, modelo.predict(xv)):
                if previsoes[nome][int(indice)] is not None:
                    raise ValueError("Registro previsto mais de uma vez")
                previsoes[nome][int(indice)] = str(prev)
        contagens_folds.append({
            "fold": numero, "treino": len(treino),
            "verificacao": len(verificacao),
            "repositorios_independentes": len(set(grupos[verificacao])),
        })
    if any(any(p is None for p in ps) for ps in previsoes.values()):
        raise ValueError("Previsoes fora de fold incompletas")

    metricas = {}
    for nome, pred in previsoes.items():
        por_classe = classification_report(
            y, pred, labels=list(CLASSES), output_dict=True, zero_division=0)
        metricas[nome] = {
            "acertos": sum(real == estimado for real, estimado in zip(y, pred)),
            "acuracia": round(float(accuracy_score(y, pred)), 4),
            "macro_f1": round(float(f1_score(
                y, pred, labels=list(CLASSES), average="macro", zero_division=0)), 4),
            "por_classe": {c: {k: round(float(v), 4)
                              for k, v in por_classe[c].items()}
                          for c in CLASSES},
            "matriz_confusao": confusion_matrix(
                y, pred, labels=list(CLASSES)).tolist(),
        }

    linhas = []
    revisar = []
    for i, r in enumerate(registros):
        linha = {
            "id": ids[i],
            "titulo": titulos[i],
            "repositorios": "|".join(r["repositorios"]),
            "rotulo_registrado": str(y[i]),
            "original": previsoes["original"][i],
            "palavras_caracteres": previsoes["palavras_caracteres"][i],
        }
        linhas.append(linha)
        erros = sum(linha[n] != linha["rotulo_registrado"]
                    for n in ("original", "palavras_caracteres"))
        if erros:
            revisar.append({**linha, "erros_modelos": erros})
    # Apenas priorizacao da auditoria, nunca correcao automatica dos rotulos.
    revisar.sort(key=lambda r: (-r["erros_modelos"],
                               r["rotulo_registrado"] != "docs",
                               r["rotulo_registrado"] != "refactor",
                               r["titulo"]))

    resumo = {
        "protocolo": "comparacao-fixa-svm-palavras-caracteres-grupos-treino",
        "quantidade_treino": len(registros),
        "distribuicao_treino": dict(Counter(y)),
        "grupos_independentes": len(set(grupos)),
        "folds": contagens_folds,
        "classes": list(CLASSES),
        "modelos": metricas,
        "casos_para_revisao": len(revisar),
        "observacoes": [
            "Apenas rotulos registrados na particao treino; dados de validacao e teste nao lidos.",
            "Mesmos folds por repositorios relacionados e titulos iguais nos dois modelos.",
            "Configuracoes fixas: nenhuma calibracao feita no conjunto externo de 45 commits.",
            "A lista de casos para revisar nao altera os rotulos nem representa correcoes confirmadas.",
            "Parte dos rotulos existentes recebeu assistencia de IA.",
            "Os resultados OOF nao sao desempenho final em repositorios ineditos.",
            "Nao executa previsoes nos 97.001 commits nem modifica os modelos publicados.",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for nome, rows, campos in (
        ("previsoes_oof.csv", linhas, list(linhas[0])),
        ("casos_para_revisao.csv", revisar,
         list(linhas[0]) + ["erros_modelos"]),
    ):
        with (saida / nome).open("x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            writer.writerows(rows)
    md = [
        "# Comparacao controlada - CommitX",
        "",
        f"Treino: {len(registros)} rotulos | Grupos independentes: {len(set(grupos))}",
        "",
        "| Modelo | Acuracia OOF | Macro-F1 OOF | Acertos |",
        "|---|---:|---:|---:|",
    ]
    for nome, resultado in metricas.items():
        md.append(
            f"| {nome} | {resultado['acuracia']:.1%} | "
            f"{resultado['macro_f1']:.3f} | "
            f"{resultado['acertos']}/{len(registros)} |")
    md.extend([
        "",
        "## Recall por classe (comparacao nos mesmos folds)",
        "",
        "| Categoria | Original | Palavras e caracteres |",
        "|---|---:|---:|",
    ])
    for classe in CLASSES:
        md.append(
            f"| {classe} | {metricas['original']['por_classe'][classe]['recall']:.1%} | "
            f"{metricas['palavras_caracteres']['por_classe'][classe]['recall']:.1%} |")
    md.extend([
        "", "## Proximo passo",
        "",
        f"Consultar {len(revisar)} candidatos em casos_para_revisao.csv, ",
        "validar seus rotulos e contexto sem usar a avaliacao externa como treino.",
        "Nao afirmar que a melhoria atingiu 80% em novos repositorios.",
        "",
    ])
    (saida / "relatorio.md").write_text("\n".join(md), encoding="utf-8")
    return resumo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path,
                        default=Path("resultados/comparacao-svm-caracteres-01"))
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        treino = carregar_treino(args.entrada, args.banco)
        resultado = comparar(treino, args.saida, args.folds)
    except (ValueError, OSError, csv.Error) as erro:
        parser.error(str(erro))
    for nome, m in resultado["modelos"].items():
        print(f"{nome}: acuracia OOF={m['acuracia']:.1%} "
              f"macro-F1 OOF={m['macro_f1']:.3f} "
              f"acertos={m['acertos']}/{resultado['quantidade_treino']}")
    print("Grupos independentes:", resultado["grupos_independentes"])
    print("Casos para revisar:", resultado["casos_para_revisao"])
    print("Relatorio:", args.saida / "relatorio.md")


if __name__ == "__main__":
    main()
