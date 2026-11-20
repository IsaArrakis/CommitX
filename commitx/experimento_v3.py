"""CommitX V3: nested grouped cross-validation on TRAIN only; never modifies SQLite."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sqlite3

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .escrita import texto_modelo
from .treino_real import ENTRADA, BANCO, CATEGORIAS_VALIDAS

CLASSES = tuple(CATEGORIAS_VALIDAS)


def carregar_treino(entrada=ENTRADA, banco=BANCO):
    entrada, banco = Path(entrada), Path(banco)
    if not entrada.is_file() or not banco.is_file():
        raise ValueError("CSV preparado ou banco SQLite nao encontrado")
    registros = []
    ids = set()
    with entrada.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        obrigatorias = {"id", "titulo", "descricao", "repositorio", "particao"}
        if not obrigatorias.issubset(leitor.fieldnames or []):
            raise ValueError("CSV preparado sem colunas essenciais")
        for linha in leitor:
            if linha["particao"] != "treino":
                continue
            uid = linha["id"]
            if not uid or uid in ids:
                raise ValueError("ID ausente ou repetido")
            ids.add(uid)
            registros.append(linha)
    con = sqlite3.connect("file:" + banco.resolve().as_posix() + "?mode=ro", uri=True)
    try:
        humanos = dict(con.execute("SELECT id, categoria FROM avaliacoes").fetchall())
    finally:
        con.close()
    saida = []
    for r in registros:
        categoria = humanos.get(r["id"])
        if categoria not in CLASSES:
            continue
        titulo_original = (r["titulo"] or "").strip()
        if not titulo_original:
            continue
        titulo = texto_modelo(titulo_original, "")
        repos = tuple(sorted(x.strip() for x in (r["repositorio"] or "").split(",") if x.strip()))
        if not repos or not titulo:
            raise ValueError("Registro de treino sem repositorio ou titulo")
        saida.append({
            "id": r["id"], "titulo": titulo,
            "texto_completo": texto_modelo(titulo_original, r.get("descricao") or ""),
            "categoria": categoria, "repositorios": repos,
        })
    return saida


def componentes(registros):
    """Conecta repositorios relacionados e titulos duplicados antes de dividir folds."""
    parent = {}
    def root(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = root(parent[x])
        return parent[x]
    def unir(x, y):
        a, b = root(x), root(y)
        if a != b:
            parent[max(a, b)] = min(a, b)
    keys = []
    for r in registros:
        repos = ["repo:" + x for x in r["repositorios"]]
        if not repos:
            raise ValueError("Registro sem repositorios")
        same_title = "title:" + " ".join(r["titulo"].casefold().split())
        for x in repos[1:] + [same_title]:
            unir(repos[0], x)
        keys.append(repos[0])
    return np.array([root(x) for x in keys])


def _words():
    return TfidfVectorizer(analyzer="word", ngram_range=(1, 2),
                           strip_accents="unicode", sublinear_tf=True,
                           max_features=20000)


def _model(name, c):
    if name in ("svm_words_title", "svm_words_full"):
        vectorizer = _words()
        classifier = LinearSVC(C=c, class_weight="balanced", random_state=42)
    elif name == "svm_chars_title":
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5),
                                     strip_accents="unicode", sublinear_tf=True,
                                     max_features=40000)
        classifier = LinearSVC(C=c, class_weight="balanced", random_state=42)
    elif name == "svm_mixed_title":
        vectorizer = FeatureUnion([
            ("words", _words()),
            ("chars", TfidfVectorizer(analyzer="char", ngram_range=(3, 5),
                                      sublinear_tf=True, max_features=30000)),
        ])
        classifier = LinearSVC(C=c, class_weight="balanced", random_state=42)
    elif name == "logreg_title":
        vectorizer = _words()
        classifier = LogisticRegression(C=c, class_weight="balanced",
                                        random_state=42, max_iter=1000)
    else:
        raise ValueError("Modelo desconhecido")
    return Pipeline([("tfidf", vectorizer), ("model", classifier)])


CONFIGS = [
    ("svm_words_title", .25), ("svm_words_title", 1.0), ("svm_words_title", 4.0),
    ("svm_chars_title", .5), ("svm_chars_title", 2.0),
    ("svm_mixed_title", .5), ("svm_mixed_title", 2.0),
    ("svm_words_full", 1.0), ("logreg_title", 1.0),
]


def _text(row, name):
    return row["texto_completo"] if name == "svm_words_full" else row["titulo"]


def avaliar(registros, saida, externos=5, internos=3):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Saida ja existe: " + str(saida))
    if not 3 <= externos <= 8 or not 2 <= internos <= 5:
        raise ValueError("Folds externos 3-8; internos 2-5")
    if len(registros) < 30 or len({x["id"] for x in registros}) != len(registros):
        raise ValueError("Exemplos insuficientes ou IDs repetidos")
    y = np.array([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Precisamos das cinco classes no treino")
    groups = componentes(registros)
    if len(set(groups)) < externos:
        raise ValueError("Grupos insuficientes")
    outer = StratifiedGroupKFold(n_splits=externos, shuffle=True, random_state=42)
    previsoes, selecoes = [], []
    for fold, (it, iv) in enumerate(outer.split(np.zeros(len(y)), y, groups), 1):
        if set(groups[it]) & set(groups[iv]):
            raise ValueError("Vazamento em folds externos")
        if set(y[it]) != set(CLASSES):
            raise ValueError("Fold externo sem classe; revise composicao da base")
        train = [registros[int(j)] for j in it]
        yin, gin = y[it], groups[it]
        if len(set(gin)) < internos:
            raise ValueError("Grupos internos insuficientes")
        inner = StratifiedGroupKFold(n_splits=internos, shuffle=True, random_state=100+fold)
        cuts = list(inner.split(np.zeros(len(yin)), yin, gin))
        if any(set(gin[a]) & set(gin[b]) for a, b in cuts):
            raise ValueError("Vazamento em folds internos")
        scores = []
        for name, c in CONFIGS:
            truths, preds = [], []
            for a, b in cuts:
                if len(set(yin[a])) < 2:
                    raise ValueError("Fold interno com apenas uma classe")
                model = _model(name, c)
                model.fit([_text(train[int(j)], name) for j in a], yin[a])
                truths.extend(yin[b])
                preds.extend(model.predict([_text(train[int(j)], name) for j in b]))
            scores.append(float(f1_score(truths, preds, labels=list(CLASSES),
                                         average="macro", zero_division=0)))
        winner = max(range(len(scores)), key=lambda j: scores[j])
        name, c = CONFIGS[winner]
        selection = _model(name, c)
        selection.fit([_text(r, name) for r in train], yin)
        pred = selection.predict([_text(registros[int(j)], name) for j in iv])
        ref = _model("svm_words_title", 1.)
        ref.fit([r["titulo"] for r in train], yin)
        pred_ref = ref.predict([registros[int(j)]["titulo"] for j in iv])
        dummy = DummyClassifier(strategy="most_frequent")
        dummy.fit(np.zeros((len(it), 1)), yin)
        pred_dummy = dummy.predict(np.zeros((len(iv), 1)))
        selecoes.append({
            "fold": fold, "n_treino": len(it), "n_verificacao": len(iv),
            "escolhido": name, "C": c, "macro_f1_interno": round(scores[winner], 4),
        })
        for model_name, predictions in (
            ("selecionado_interno", pred),
            ("svm_titulo_fixa", pred_ref),
            ("baseline_maioria", pred_dummy),
        ):
            for j, p in zip(iv, predictions):
                r = registros[int(j)]
                previsoes.append({
                    "id": r["id"], "fold": fold, "modelo": model_name,
                    "real": r["categoria"], "previsto": str(p),
                    "acertou": int(r["categoria"] == str(p)),
                })
    metricas = {}
    for name in ("selecionado_interno", "svm_titulo_fixa", "baseline_maioria"):
        rows = [r for r in previsoes if r["modelo"] == name]
        if len(rows) != len(registros) or len({r["id"] for r in rows}) != len(registros):
            raise ValueError("Previsoes fora de fold incompletas")
        a = [r["real"] for r in rows]
        b = [r["previsto"] for r in rows]
        metricas[name] = {
            "acuracia": float(accuracy_score(a, b)),
            "macro_f1": float(f1_score(a, b, labels=list(CLASSES),
                                       average="macro", zero_division=0)),
            "recall_por_classe": {
                cls: float(recall_score(a, b, labels=[cls],
                                         average="macro", zero_division=0))
                for cls in CLASSES
            },
            "matriz_confusao": confusion_matrix(a, b, labels=list(CLASSES)).tolist(),
        }
    result = {
        "protocolo": "nested-stratified-groupcv-title-repo-v3",
        "quantidade_treino": len(registros),
        "grupos_independentes": len(set(groups)),
        "classes": list(CLASSES),
        "folds_externos": externos,
        "folds_internos": internos,
        "selecoes": selecoes, "metricas": metricas,
        "restricoes": [
            "Somente particao treino. Validacao/teste nao foram usados.",
            "Escolha de modelo ocorre apenas em folds internos.",
            "Agrupamento por repositorio e titulo igual; sem sobreposicao de grupo.",
            "Esta e comparacao exploratoria e nao substitui teste em projetos novos.",
            "Rotulos assistidos por IA podem conter inconsistencias.",
            "Nenhum rotulo ou SQLite foi modificado.",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    with (saida / "resumo.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with (saida / "previsoes_oof.csv").open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(previsoes[0]))
        writer.writeheader()
        writer.writerows(previsoes)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--banco", type=Path, default=BANCO)
    p.add_argument("--saida", type=Path, default=Path("resultados/experimento-v3-01"))
    p.add_argument("--folds-externos", type=int, default=5)
    p.add_argument("--folds-internos", type=int, default=3)
    a = p.parse_args(argv)
    try:
        dados = carregar_treino(a.entrada, a.banco)
        resumo = avaliar(dados, a.saida, a.folds_externos, a.folds_internos)
    except (ValueError, OSError, sqlite3.Error, csv.Error) as e:
        p.error(str(e))
    print("Exemplos:", resumo["quantidade_treino"])
    print("Grupos:", resumo["grupos_independentes"])
    for name, m in resumo["metricas"].items():
        print(f"{name}: acuracia={m['acuracia']:.3f} macro-F1={m['macro_f1']:.3f}")
    print("Resumo:", a.saida / "resumo.json")


if __name__ == "__main__":
    main()
