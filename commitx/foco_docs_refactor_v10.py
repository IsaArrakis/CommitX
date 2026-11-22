"""CommitX V10: diagnostico dirigido de docs/refactor no TREINO existente.

Exploratorio. Compara pesos predefinidos nos mesmos folds agrupados do V9.
Nao acessa conjunto externo, validacao/teste ou pseudorrotulos.
Nao modifica modelos, dados ou rotulos.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.utils.class_weight import compute_class_weight

from .comparacao_prefixos import CLASSES, prefixo, raw_titles
from .experimento_v3 import carregar_treino, componentes

CONFIGS = {
    "base_c03": (1.0, 1.0),
    "docs_125_refactor_125": (1.25, 1.25),
    "docs_150_refactor_150": (1.5, 1.5),
    "docs_175_refactor_150": (1.75, 1.5),
    "docs_150_refactor_175": (1.5, 1.75),
}


def pipeline(pesos):
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2), strip_accents="unicode",
            sublinear_tf=True, max_features=50000,
        )),
        ("model", LinearSVC(
            C=0.3, class_weight=pesos, random_state=42,
        )),
    ])


def pesos_do_fold(y_treino, docs_factor, refactor_factor):
    """class_weight='balanced' calculado APENAS no fold de treino."""
    classes = np.unique(y_treino)
    w = compute_class_weight(
        class_weight="balanced", classes=classes, y=y_treino,
    )
    resultado = {str(c): float(v) for c, v in zip(classes, w)}
    if set(resultado) != set(CLASSES):
        raise ValueError("Fold sem as cinco classes")
    resultado["docs"] *= docs_factor
    resultado["refactor"] *= refactor_factor
    return resultado


def medir(registros, originais, saida, n_folds=5):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Saida ja existe: " + str(saida))
    ids = [r["id"] for r in registros]
    if len(ids) < 30 or len(ids) != len(set(ids)) or set(ids) != set(originais):
        raise ValueError("Treino ausente, duplicado ou incompleto")
    if n_folds < 3 or n_folds > 8:
        raise ValueError("Use entre 3 e 8 folds")
    x = [originais[uid] for uid in ids]
    y = np.array([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Treino deve conter as cinco categorias")
    grupos = componentes(registros)
    if len(set(grupos)) < n_folds:
        raise ValueError("Grupos insuficientes")
    cortes = list(StratifiedGroupKFold(
        n_splits=n_folds, shuffle=True, random_state=42,
    ).split(np.zeros(len(y)), y, grupos))
    oof = {nome: [None] * len(x) for nome in CONFIGS}
    for it, iv in cortes:
        if set(grupos[it]) & set(grupos[iv]):
            raise ValueError("Vazamento de grupo")
        yt = y[it]
        if set(yt) != set(CLASSES):
            raise ValueError("Fold treino nao inclui as cinco classes")
        for nome, (fd, fr) in CONFIGS.items():
            m = pipeline(pesos_do_fold(yt, fd, fr))
            m.fit([x[int(i)] for i in it], yt)
            previsoes = m.predict([x[int(i)] for i in iv])
            for pos, pred in zip(iv, previsoes):
                j = int(pos)
                if oof[nome][j] is not None:
                    raise ValueError("OOF duplicado")
                oof[nome][j] = str(pred)
    if any(v is None for linhas in oof.values() for v in linhas):
        raise ValueError("OOF incompleto")
    resumo = {
        "protocolo": "v10-pesos-docs-refactor-train-only-oof",
        "rotulos_treino": len(y),
        "grupos_independentes": len(set(grupos)),
        "folds": n_folds,
        "classes": list(CLASSES),
        "pesos_multiplicadores": {k: list(v) for k,v in CONFIGS.items()},
        "resultados": {},
        "limites": [
            "Exploratorio em 397 rotulos de treino assistidos anteriormente por IA.",
            "Pesos base calculados em cada fold; validacao/teste e externo nunca usados.",
            "Escolher entre varias configuracoes usando a mesma OOF pode superestimar desempenho.",
            "Aumentar recall pode aumentar falsos positivos; observar precision, F1 e acuracia.",
            "Nao modificar rotulos, modelos existentes ou banco SQLite.",
            "Acuracia externa nova so pode ser estimada com teste novo e cego.",
        ],
    }
    for nome, prev in oof.items():
        precision, recall, f1, suporte = precision_recall_fscore_support(
            y, prev, labels=CLASSES, zero_division=0,
        )
        matrix = confusion_matrix(y, prev, labels=CLASSES)
        resumo["resultados"][nome] = {
            "acertos": sum(str(a) == b for a,b in zip(y, prev)),
            "acuracia": round(float(accuracy_score(y, prev)), 4),
            "macro_f1": round(float(f1_score(
                y, prev, labels=CLASSES, average="macro", zero_division=0
            )), 4),
            "por_classe": {
                cls: {
                    "precision": round(float(precision[i]), 4),
                    "recall": round(float(recall[i]), 4),
                    "f1": round(float(f1[i]), 4),
                    "suporte": int(suporte[i]),
                    "falsos_positivos": int(matrix[:,i].sum()-matrix[i,i]),
                    "falsos_negativos": int(matrix[i,:].sum()-matrix[i,i]),
                } for i,cls in enumerate(CLASSES)
            },
            "matriz_confusao": matrix.tolist(),
        }
    saida.mkdir(parents=True, exist_ok=False)
    (saida/"resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2)+"\n",encoding="utf-8"
    )
    with (saida/"previsoes_oof.csv").open("x", newline="", encoding="utf-8") as f:
        campos = ["id","titulo","rotulo_registrado","prefixo_declarado",*CONFIGS]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for i, uid in enumerate(ids):
            writer.writerow({
                "id":uid, "titulo":x[i], "rotulo_registrado":str(y[i]),
                "prefixo_declarado":prefixo(x[i]),
                **{nome:oof[nome][i] for nome in CONFIGS},
            })
    principal = "base_c03"
    com_mudanca = []
    for i, uid in enumerate(ids):
        if any(oof[nome][i] != oof[principal][i] for nome in CONFIGS if nome != principal):
            com_mudanca.append({
                "id":uid, "titulo":x[i], "real":str(y[i]),
                **{nome:oof[nome][i] for nome in CONFIGS},
            })
    with (saida/"mudancas.csv").open("x",newline="",encoding="utf-8") as f:
        campos=["id","titulo","real",*CONFIGS]
        writer=csv.DictWriter(f,fieldnames=campos)
        writer.writeheader()
        writer.writerows(com_mudanca)
    linhas=[
        "# CommitX V10 — melhorando docs/refactor",
        "",
        "Somente treino agrupado com 5 folds; diagnostico exploratorio.",
        f"Treino: {len(y)} | grupos: {len(set(grupos))} | mudancas em previsoes: {len(com_mudanca)}",
        "",
        "| Variante | Acuracia | Macro-F1 | docs R/P/F1 | refactor R/P/F1 |",
        "|---|---:|---:|---|---|",
    ]
    for nome,r in resumo["resultados"].items():
        def descr(c):
            z=r["por_classe"][c]
            return f"{z['recall']:.1%} / {z['precision']:.1%} / {z['f1']:.3f}"
        linhas.append(
            f"| {nome} | {r['acuracia']:.1%} | {r['macro_f1']:.3f} | "
            f"{descr('docs')} | {descr('refactor')} |"
        )
    linhas += [
        "", "## Interpretacao",
        "- R = recall, P = precision. Recall maior sem precision adequada pode ser pior.",
        "- Examinar mudancas.csv e matriz_confusao no resumo.json.",
        "- Prefixos declarados nao sao rotulos garantidos.",
        "- Nenhuma acuracia foi medida em novos repositorios nesta rodada.",
    ]
    (saida/"relatorio.md").write_text("\n".join(linhas)+"\n",encoding="utf-8")
    return resumo


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada",default="resultados/preparacao-inicial/commits_preparados.csv")
    p.add_argument("--saida",default="resultados/comparacao-v10-docs-refactor-01")
    p.add_argument("--folds",type=int,default=5)
    a=p.parse_args(argv)
    try:
        treino=carregar_treino()
        titulos=raw_titles(a.entrada,{r["id"] for r in treino})
        resumo=medir(treino,titulos,a.saida,a.folds)
    except (ValueError,OSError,csv.Error) as e:
        p.error(str(e))
    for nome,r in resumo["resultados"].items():
        d=r["por_classe"]["docs"]
        f=r["por_classe"]["refactor"]
        print(
            f"{nome}: acuracia {r['acuracia']:.1%} | macro-F1 {r['macro_f1']:.3f} | "
            f"docs recall {d['recall']:.1%} precision {d['precision']:.1%} | "
            f"refactor recall {f['recall']:.1%} precision {f['precision']:.1%}"
        )
    print("Relatorio:",Path(a.saida)/"relatorio.md")
    print("Mudancas:",Path(a.saida)/"mudancas.csv")


if __name__=="__main__":
    main()
