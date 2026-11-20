"""Compara classificadores usando SOMENTE a particao de treino.

Estratifica por grupos conectados de repositorios, sem consultar particoes de
validacao/teste e sem escolher modelos usando o antigo conjunto de 39 exemplos.

Uso:
  python -m commitx.avaliacao_robusta \
    --saida resultados/avaliacao-robusta-500-v1
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .treino_real import (
    ENTRADA, BANCO, CATEGORIAS_VALIDAS, carregar_revisados,
    repositorios_da_linha,
)

SAIDA_PADRAO = Path("resultados/avaliacao-robusta-500-v1")
CLASSES = tuple(CATEGORIAS_VALIDAS)


def grupos_conectados(registros):
    """Um mesmo repositorio, mesmo em listas, nunca cruza folds."""
    pais = {}

    def raiz(x):
        if x not in pais:
            pais[x] = x
        if pais[x] != x:
            pais[x] = raiz(pais[x])
        return pais[x]

    def unir(a, b):
        x, y = raiz(a), raiz(b)
        if x != y:
            pais[max(x, y)] = min(x, y)

    conjuntos = []
    for r in registros:
        repos = sorted(repositorios_da_linha(r["repositorio"]))
        if not repos:
            raise ValueError("Registro sem repositorio: nao e seguro dividir dados")
        for repo in repos[1:]:
            unir(repos[0], repo)
        conjuntos.append(repos)
    return [raiz(repos[0]) for repos in conjuntos]


def _tfidf_word():
    return TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2),
        strip_accents="unicode", sublinear_tf=True,
        min_df=1, max_features=20000,
    )


def modelos():
    return {
        "logreg_palavras_atual": Pipeline([
            ("texto", _tfidf_word()),
            ("modelo", LogisticRegression(max_iter=1000, random_state=42,
                                          class_weight="balanced")),
        ]),
        "svm_palavras": Pipeline([
            ("texto", _tfidf_word()),
            ("modelo", LinearSVC(random_state=42, class_weight="balanced")),
        ]),
        "svm_palavras_caracteres": Pipeline([
            ("texto", FeatureUnion([
                ("palavras", _tfidf_word()),
                ("caracteres", TfidfVectorizer(
                    analyzer="char", ngram_range=(3, 5), min_df=1,
                    max_features=40000, sublinear_tf=True,
                )),
            ])),
            ("modelo", LinearSVC(random_state=42, class_weight="balanced")),
        ]),
        "baseline_maioria": Pipeline([
            ("texto", _tfidf_word()),
            ("modelo", DummyClassifier(strategy="most_frequent")),
        ]),
    }


def avaliar_registros(registros, saida=SAIDA_PADRAO, folds=5):
    """Avalia apenas treino. Nao usa validacao/teste nem altera rotulos."""
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Pasta de saida ja existe: " + str(saida))
    if not 3 <= folds <= 10:
        raise ValueError("--folds deve estar entre 3 e 10")

    amostras = [
        r for r in registros
        if r["particao"] == "treino" and r["categoria"] in CLASSES
    ]
    ids = [r["id"] for r in amostras]
    if len(set(ids)) != len(ids):
        raise ValueError("IDs duplicados no treino")
    if not amostras or any(not r["texto"].strip() for r in amostras):
        raise ValueError("Sem textos validos para avaliacao")

    grupos = grupos_conectados(amostras)
    n_grupos = len(set(grupos))
    if n_grupos < folds:
        raise ValueError(
            f"Apenas {n_grupos} grupos independentes, insuficientes para {folds} folds"
        )
    resultados = {nome: [] for nome in modelos()}
    folds_relatorio = []
    for numero, (indices_treino, indices_verificacao) in enumerate(
        GroupKFold(n_splits=folds).split(
            [r["texto"] for r in amostras],
            [r["categoria"] for r in amostras], grupos,
        ), 1
    ):
        treino = [amostras[i] for i in indices_treino]
        verificacao = [amostras[i] for i in indices_verificacao]
        grupos_t = {grupos[i] for i in indices_treino}
        grupos_v = {grupos[i] for i in indices_verificacao}
        if grupos_t & grupos_v:
            raise ValueError("Vazamento de repositorios entre folds")
        rotulos_t = [r["categoria"] for r in treino]
        if len(set(rotulos_t)) < 2:
            raise ValueError("Fold com menos de duas classes no treinamento")
        faltantes = sorted(set(CLASSES) - set(rotulos_t))
        folds_relatorio.append({
            "fold": numero,
            "n_treino": len(treino),
            "n_verificacao": len(verificacao),
            "grupos_treino": len(grupos_t),
            "grupos_verificacao": len(grupos_v),
            "classes_ausentes_no_treino": faltantes,
            "distribuicao_verificacao": dict(Counter(r["categoria"] for r in verificacao)),
        })
        x_t, x_v = [r["texto"] for r in treino], [r["texto"] for r in verificacao]
        for nome, modelo in modelos().items():
            modelo.fit(x_t, rotulos_t)
            previstos = modelo.predict(x_v)
            resultados[nome].extend({
                "id": registro["id"],
                "fold": numero,
                "real": registro["categoria"],
                "previsto": str(pred),
            } for registro, pred in zip(verificacao, previstos))

    resumo_modelos = {}
    for nome, linhas in resultados.items():
        reais = [r["real"] for r in linhas]
        previstos = [r["previsto"] for r in linhas]
        if len(linhas) != len(amostras):
            raise ValueError("Nem todas as amostras foram avaliadas")
        relatorio_classes = classification_report(
            reais, previstos, labels=list(CLASSES), output_dict=True,
            zero_division=0,
        )
        resumo_modelos[nome] = {
            "acuracia": float(accuracy_score(reais, previstos)),
            "macro_f1": float(f1_score(
                reais, previstos, labels=list(CLASSES),
                average="macro", zero_division=0,
            )),
            "matriz_confusao": confusion_matrix(
                reais, previstos, labels=list(CLASSES),
            ).tolist(),
            "recall_por_classe": {
                c: float(relatorio_classes[c]["recall"]) for c in CLASSES
            },
            "acertos": sum(a == b for a, b in zip(reais, previstos)),
        }

    relatorio = {
        "protocolo": "group-kfold-somente-treino-v1",
        "treino_elegivel": len(amostras),
        "grupos_independentes": n_grupos,
        "folds": folds_relatorio,
        "classes": list(CLASSES),
        "distribuicao": dict(Counter(r["categoria"] for r in amostras)),
        "modelos": resumo_modelos,
        "limites": [
            "Os folds usam somente a particao original de treino.",
            "A antiga validacao de 39 casos e os dois testes reservados nao participam.",
            "Separacao considera conexoes entre repositorios de origem multipla.",
            "Todos os modelos usam os mesmos folds e os mesmos exemplos.",
            "Rotulos em parte assistidos por IA: sem auditoria cega independente.",
            "GroupKFold nao garante equilibrio perfeito de classes em cada fold.",
            "Usar estas metricas apenas para DESENVOLVIMENTO; nao sao teste final.",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    with (saida / "resumo.json").open("x", encoding="utf-8") as arq:
        json.dump(relatorio, arq, ensure_ascii=False, indent=2)
        arq.write("\n")
    for nome, linhas in resultados.items():
        with (saida / f"previsoes_{nome}.csv").open(
            "x", encoding="utf-8", newline=""
        ) as arq:
            w = csv.DictWriter(
                arq, fieldnames=["id", "fold", "real", "previsto"]
            )
            w.writeheader()
            w.writerows(linhas)
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        registros = carregar_revisados(args.entrada, args.banco)
        resultado = avaliar_registros(registros, args.saida, args.folds)
    except (OSError, ValueError, csv.Error) as erro:
        parser.error(str(erro))
    print("Amostras de treino:", resultado["treino_elegivel"])
    print("Grupos de repositorios:", resultado["grupos_independentes"])
    for nome, m in resultado["modelos"].items():
        print(f"{nome}: acuracia={m['acuracia']:.3f}, macro-F1={m['macro_f1']:.3f}")
    print("Relatorio:", args.saida / "resumo.json")


if __name__ == "__main__":
    main()
