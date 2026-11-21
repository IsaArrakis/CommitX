"""Compare explicit commit prefixes on TRAIN labels only.

Frozen five-fold grouped validation, no auto-correction or model writes.
The baseline strips conventional prefixes, as CommitX currently does.
Variants test raw title and a conservative prefix-only override.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import StratifiedGroupKFold

from .academico import _modelo
from .experimento_v3 import carregar_treino, componentes
from .escrita import texto_modelo

CLASSES = ("fix", "feat", "docs", "refactor", "test")
PREFIX_RE = re.compile(
    r"^(?P<tipo>fix|feat|docs|refactor|test)(?:\\([^()\\r\\n]+\\))?!?:\\s*\\S",
    flags=re.I,
)


def prefixo(titulo):
    m = PREFIX_RE.match(titulo.strip())
    return m.group("tipo").lower() if m else ""


def raw_titles(prepared, ids):
    """Read original titles from TRAIN rows, not validation/test rows."""
    titles = {}
    with Path(prepared).open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("particao") != "treino" or r.get("id") not in ids:
                continue
            uid = r["id"]
            if uid in titles:
                raise ValueError("Duplicate training ID")
            titles[uid] = (r.get("titulo") or "").strip()
    if set(titles) != set(ids):
        raise ValueError("Missing original titles for training IDs")
    return titles


def comparar(registros, brutos, saida, folds=5):
    saida = Path(saida)
    if saida.exists():
        raise FileExistsError(f"Saida existente: {saida}")
    if folds < 3 or folds > 8:
        raise ValueError("Use 3 a 8 folds")
    if len(registros) < 30 or len({r["id"] for r in registros}) != len(registros):
        raise ValueError("Treino insuficiente ou IDs repetidos")
    ids = [r["id"] for r in registros]
    if set(ids) != set(brutos):
        raise ValueError("IDs originais diferem do treino")
    y = np.array([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Treino sem as cinco categorias")
    grupos = componentes(registros)
    if len(set(grupos)) < folds:
        raise ValueError("Grupos independentes insuficientes")
    normalizados = [r["titulo"] for r in registros]
    completos = [brutos[uid] for uid in ids]
    declarados = [prefixo(t) for t in completos]
    # The prefix is signal, not ground truth. Override is reported separately.
    folds_cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=42)
    preds = {k: [None] * len(ids) for k in
             ("original", "prefixo_preservado", "prefixo_com_regra")}
    for tr, va in folds_cv.split(np.zeros(len(ids)), y, grupos):
        if set(grupos[tr]) & set(grupos[va]):
            raise ValueError("Vazamento de grupo")
        if set(y[tr]) != set(CLASSES):
            raise ValueError("Fold sem alguma das cinco classes")
        for nome, textos in (
            ("original", normalizados),
            ("prefixo_preservado", completos),
        ):
            modelo = _modelo()
            modelo.fit([textos[int(i)] for i in tr], y[tr])
            for i, predicted in zip(va, modelo.predict([textos[int(i)] for i in va])):
                preds[nome][int(i)] = str(predicted)
        # The override tests an explicit, auditable heuristic; not fitted to labels.
        for i in va:
            i = int(i)
            preds["prefixo_com_regra"][i] = (
                declarados[i] or preds["original"][i]
            )
    if any(None in rows for rows in preds.values()):
        raise ValueError("OOF incompleto")
    metricas = {}
    for nome, prev in preds.items():
        report = classification_report(
            y, prev, labels=list(CLASSES), output_dict=True, zero_division=0
        )
        metricas[nome] = {
            "acuracia": round(float(accuracy_score(y, prev)), 4),
            "macro_f1": round(float(f1_score(
                y, prev, labels=list(CLASSES), average="macro", zero_division=0
            )), 4),
            "acertos": sum(a == b for a, b in zip(y, prev)),
            "recall": {cls: round(float(report[cls]["recall"]), 4) for cls in CLASSES},
        }
    tipos = Counter(t for t in declarados if t)
    divergencias = sum(
        bool(t) and t != real for t, real in zip(declarados, y)
    )
    resumo = {
        "protocolo": "prefixos-treino-only-oof-grupos-fixos",
        "treino": len(ids),
        "folds": folds,
        "grupos": len(set(grupos)),
        "prefixos_reconhecidos": dict(tipos),
        "prefixos_divergentes_do_rotulo": divergencias,
        "modelos": metricas,
        "restricoes": [
            "Somente rotulos e titulos de treino, nunca validacao/teste",
            "Mesmos grupos e folds nos tres tratamentos",
            "Prefixo declarado nao e rotulo validado; override e hipotese exploratoria",
            "Nenhum modelo existente ou rotulo foi modificado",
            "Resultados OOF nao substituem avaliacao externa nova",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "resumo.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (saida / "previsoes.csv").open(
        "x", encoding="utf-8", newline=""
    ) as f:
        nomes = [
            "id", "titulo_original", "rotulo_registrado", "prefixo_declarado",
            "original", "prefixo_preservado", "prefixo_com_regra",
        ]
        w = csv.DictWriter(f, fieldnames=nomes)
        w.writeheader()
        for i, uid in enumerate(ids):
            w.writerow({
                "id": uid, "titulo_original": completos[i],
                "rotulo_registrado": str(y[i]), "prefixo_declarado": declarados[i],
                **{k: preds[k][i] for k in preds},
            })
    linhas = [
        "# Efeito dos prefixos no CommitX",
        "",
        f"Treino: {len(ids)} | grupos: {len(set(grupos))} | folds: {folds}",
        f"Prefixos reconhecidos: {sum(tipos.values())}",
        f"Prefixos que discordam dos rotulos registrados: {divergencias}",
        "",
        "| Variante | Acuracia OOF | Macro-F1 OOF | Acertos |",
        "|---|---:|---:|---:|",
    ]
    for nome, resultado in metricas.items():
        linhas.append(
            f"| {nome} | {resultado['acuracia']:.1%} | "
            f"{resultado['macro_f1']:.3f} | {resultado['acertos']}/{len(ids)} |"
        )
    linhas += [
        "", "## Recall por classe", "",
        "| Classe | Original | Prefixo preservado | Regra explicita |",
        "|---|---:|---:|---:|",
    ]
    for cls in CLASSES:
        linhas.append(
            f"| {cls} | {metricas['original']['recall'][cls]:.1%} | "
            f"{metricas['prefixo_preservado']['recall'][cls]:.1%} | "
            f"{metricas['prefixo_com_regra']['recall'][cls]:.1%} |"
        )
    linhas += [
        "",
        "O prefixo e declaracao de autor, nao verdade absoluta.",
        "Nunca alterar os rotulos originais automaticamente.",
        "A avaliacao externa anterior esta conhecida e nao deve ser usada "
        "para escolher modelos nem alegar generalizacao.",
    ]
    (saida / "relatorio.md").write_text(
        "\n".join(linhas) + "\n", encoding="utf-8"
    )
    return resumo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--entrada", default="resultados/preparacao-inicial/commits_preparados.csv"
    )
    p.add_argument("--saida", default="resultados/comparacao-prefixos-01")
    p.add_argument("--folds", type=int, default=5)
    args = p.parse_args(argv)
    try:
        dados = carregar_treino()
        originais = raw_titles(args.entrada, {r["id"] for r in dados})
        resumo = comparar(dados, originais, args.saida, args.folds)
    except (OSError, ValueError, csv.Error) as exc:
        p.error(str(exc))
    for nome, m in resumo["modelos"].items():
        print(f"{nome}: acuracia={m['acuracia']:.1%} macro-F1={m['macro_f1']:.3f}")
    print("Prefixos reconhecidos:", sum(resumo["prefixos_reconhecidos"].values()))
    print("Prefixos divergentes:", resumo["prefixos_divergentes_do_rotulo"])
    print("Relatorio:", str(Path(args.saida) / "relatorio.md"))


if __name__ == "__main__":
    main()
