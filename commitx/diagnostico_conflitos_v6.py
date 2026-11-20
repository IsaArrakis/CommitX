"""Diagnostico dos conflitos da triagem V6. Apenas leitura; nao mede acuracia."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

ENTRADA = Path("resultados/triagem-automatica-v6-01/triagem.csv")
SAIDA = Path("resultados/diagnostico-v6-01")


def _ler(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"id", "repositorio", "titulo", "categoria_svm",
                    "categoria_ollama", "margem_svm", "prioridade"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("triagem.csv sem colunas essenciais")
        rows = list(reader)
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("IDs repetidos")
    return rows


def _margem(row):
    try:
        return float(row["margem_svm"])
    except (TypeError, ValueError):
        return float("inf")


def _diversos(casos, limite, max_repo=5):
    grupos = {}
    for r in casos:
        grupos.setdefault((r["categoria_svm"], r["categoria_ollama"]), []).append(r)
    for g in grupos.values():
        g.sort(key=lambda r: (_margem(r), r["id"]))
    escolhidos, repos = [], Counter()
    while len(escolhidos) < limite and any(grupos.values()):
        progresso = False
        for par in sorted(grupos, key=lambda p: (-len(grupos[p]), p)):
            g = grupos[par]
            idx = next((i for i, r in enumerate(g)
                        if repos[r["repositorio"]] < max_repo), None)
            if idx is None:
                continue
            r = g.pop(idx)
            escolhidos.append(r)
            repos[r["repositorio"]] += 1
            progresso = True
            if len(escolhidos) >= limite:
                break
        if not progresso:
            if max_repo >= len(casos) + 1:
                break
            max_repo = len(casos) + 1
    return escolhidos


def analisar(*, entrada=ENTRADA, saida=SAIDA, quantidade=30):
    if not 1 <= quantidade <= 300:
        raise ValueError("Quantidade deve estar entre 1 e 300")
    rows = _ler(entrada)
    comparados = [r for r in rows if r["categoria_ollama"].strip()]
    divergentes = [r for r in comparados
                   if r["categoria_svm"] != r["categoria_ollama"]]
    concordantes = [r for r in comparados
                    if r["categoria_svm"] == r["categoria_ollama"]]
    pares = Counter((r["categoria_svm"], r["categoria_ollama"]) for r in divergentes)
    n_div = min(len(divergentes), max(1, round(quantidade * 0.8)))
    n_con = min(len(concordantes), quantidade - n_div)
    escolhidos = _diversos(divergentes, n_div)
    escolhidos.extend(_diversos(concordantes, n_con, max_repo=2))
    ids = {r["id"] for r in escolhidos}
    if len(escolhidos) < quantidade:
        extras = [r for r in comparados if r["id"] not in ids]
        escolhidos.extend(_diversos(extras, quantidade-len(escolhidos)))
    out = Path(saida)
    out.mkdir(parents=True, exist_ok=True)
    csv_out = out / "amostra_para_auditoria.csv"
    cols = ["id", "repositorio", "titulo", "categoria_svm", "margem_svm",
            "categoria_ollama", "clareza_ollama", "duvida_ollama",
            "prioridade", "motivo", "proveniencia", "rotulo_humano"]
    with csv_out.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(escolhidos)
    resumo = {
        "total_registros_csv": len(rows),
        "comparados_svm_ollama": len(comparados),
        "divergentes": len(divergentes),
        "concordantes_nao_verificados": len(concordantes),
        "apenas_svm": len(rows)-len(comparados),
        "proporcao_divergente": round(len(divergentes)/len(comparados), 4) if comparados else None,
        "principais_conflitos": [
            {"svm": a, "ollama": b, "quantidade": n}
            for (a,b),n in pares.most_common()
        ],
        "amostra_auditoria": len(escolhidos),
        "amostra_divergentes": sum(r["categoria_svm"] != r["categoria_ollama"] for r in escolhidos),
        "amostra_concordantes": sum(r["categoria_svm"] == r["categoria_ollama"] for r in escolhidos),
        "observacao": "Amostra priorizada e nao aleatoria; sem gabarito. NAO mede acuracia.",
        "arquivo": str(csv_out),
    }
    (out / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Diagnostico dos conflitos - CommitX V6", "",
        f"- Comparados: **{len(comparados)}**",
        f"- Divergencias: **{len(divergentes)}**",
        f"- Concordancias nao verificadas: **{len(concordantes)}**",
        f"- Sem Ollama: **{len(rows)-len(comparados)}**", "",
        "## Pares de categorias (SVM -> Ollama)", "",
    ]
    md.extend(f"- \`{a}\` -> \`{b}\`: {n}" for (a,b), n in pares.most_common())
    md.extend(["", "## Exemplos prioritarios (NAO sao erros comprovados)", ""])
    md.extend(
        f"{i}. \`{r['id'][:12]}\` | SVM \`{r['categoria_svm']}\` -> "
        f"Ollama \`{r['categoria_ollama']}\` | {r['titulo'][:110].replace(chr(10), ' ')}"
        for i,r in enumerate(escolhidos,1)
    )
    md.extend([
        "", "## Proximas acoes",
        "- Inspecionar o diff dos casos divergentes usando SHA e repositorio local.",
        "- Auditar tambem alguns casos de concordancia; concordar nao e acertar.",
        "- Nao substituir rotulos humanos nem reusar validacao/teste como treino.",
        "- Testar a melhoria em repositorios novos e revisao independente.",
        "", "Este diagnostico nao altera bancos, rotulos, modelos ou particoes.",
        "Titulos podem conter dados privados: revisar antes de compartilhar."
    ])
    (out / "relatorio.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return resumo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--saida", type=Path, default=SAIDA)
    p.add_argument("--quantidade", type=int, default=30)
    args = p.parse_args(argv)
    try:
        resultado = analisar(entrada=args.entrada, saida=args.saida, quantidade=args.quantidade)
    except (OSError, ValueError) as ex:
        p.error(str(ex))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    print("Relatorio:", args.saida / "relatorio.md")


if __name__ == "__main__":
    main()
