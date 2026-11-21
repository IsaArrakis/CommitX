"""Auditoria orientada de rotulos do TREINO do CommitX, sem editar rótulos.

Uso: python -m commitx.auditoria_rotulos_treino --quantidade 30
Lê candidatos gerados por melhoria_svm e inspeciona SOMENTE Git local.
Não acessa rede, não abre partições de validação/teste, nem retreina modelos.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess

PADRAO_SHA = re.compile(r"^[0-9a-f]{40}$")
ALVOS = ("docs", "refactor")
COLUNAS = ("id", "titulo", "repositorios", "rotulo_registrado",
           "original", "palavras_caracteres", "erros_modelos")


def ler_candidatos(arquivo):
    with Path(arquivo).open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        if not set(COLUNAS).issubset(leitor.fieldnames or []):
            raise ValueError("Arquivo de candidatos sem colunas esperadas")
        linhas = list(leitor)
    ids = [r["id"] for r in linhas]
    if not linhas or not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Candidatos vazios ou IDs invalidos/repetidos")
    return [r for r in linhas if r["rotulo_registrado"] in ALVOS]


def repositorios_locais(raiz):
    raiz = Path(raiz)
    if not raiz.is_dir():
        return []
    return sorted(p for p in raiz.iterdir()
                  if p.is_dir() and (p / ".git").exists())


def git(repo, *args, limite=12):
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=limite, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def localizar_commit(sha, repos):
    if not PADRAO_SHA.fullmatch(sha):
        return None
    for repo in repos:
        if git(repo, "cat-file", "-e", sha + "^{commit}", limite=4) is not None:
            return repo
    return None


def escolher(candidatos, localizados, quantidade):
    """Alterna docs/refactor e prefere contexto Git, 2 erros e diversidade."""
    por_classe = {classe: [] for classe in ALVOS}
    for r in candidatos:
        por_classe[r["rotulo_registrado"]].append(r)
    escolhidos = []
    usados = set()
    grupos = Counter()
    while len(escolhidos) < quantidade:
        classe = ALVOS[len(escolhidos) % len(ALVOS)]
        pool = [r for r in por_classe[classe]
                if r["id"] not in usados
                and " ".join(r["titulo"].casefold().split()) not in usados]
        if not pool:
            outra = next((x for x in ALVOS if por_classe[x]
                           and any(r["id"] not in usados and
                                   " ".join(r["titulo"].casefold().split()) not in usados
                                   for r in por_classe[x])), None)
            if outra is None:
                break
            pool = [r for r in por_classe[outra]
                    if r["id"] not in usados
                    and " ".join(r["titulo"].casefold().split()) not in usados]
        def prioridade(r):
            repo = (r["repositorios"].split("|")[0] or "desconhecido")
            return (-int(localizados.get(r["id"]) is not None),
                    -int(r["erros_modelos"]), grupos[repo],
                    len(r["titulo"]), r["id"])
        candidato = min(pool, key=prioridade)
        escolhidos.append(candidato)
        usados.add(candidato["id"])
        usados.add(" ".join(candidato["titulo"].casefold().split()))
        grupos[candidato["repositorios"].split("|")[0]] += 1
    if len(escolhidos) < quantidade:
        raise ValueError(
            f"Somente {len(escolhidos)} candidatos distintos de docs/refactor; "
            "reduza --quantidade.")
    return escolhidos


def sinal_caminhos(caminhos):
    if not caminhos:
        return "sem_evidencia_de_arquivos"
    def documentacao(caminho):
        nome = Path(caminho).name.lower()
        partes = Path(caminho.lower()).parts
        return ("docs" in partes or "doc" in partes or
                nome.startswith(("readme", "changelog", "contributing", "license")) or
                Path(nome).suffix in (".md", ".rst", ".adoc"))
    n = sum(documentacao(x) for x in caminhos)
    if n == len(caminhos):
        return "somente_arquivos_documentacao"
    if n:
        return "documentacao_e_outros_arquivos"
    return "sem_caminhos_tipicos_documentacao"


def auditar(candidatos, repos_dir, saida, quantidade=30):
    destino = Path(saida)
    if destino.exists() or destino.is_symlink():
        raise FileExistsError("Saida ja existe: " + str(destino))
    if not 2 <= quantidade <= 100:
        raise ValueError("Quantidade deve estar entre 2 e 100")
    candidatos = ler_candidatos(candidatos)
    if len(candidatos) < quantidade:
        raise ValueError("Nao ha candidatos suficientes para a quantidade")
    repos = repositorios_locais(repos_dir)
    localizados = {r["id"]: localizar_commit(r["id"], repos) for r in candidatos}
    escolhidos = escolher(candidatos, localizados, quantidade)

    resultados, detalhes = [], [
        "# Evidencias Git locais para revisao dos rotulos",
        "",
        "Somente leitura. Trechos podem conter dados privados: revise antes de compartilhar.",
        "Nenhum sinal de caminho comprova, isoladamente, uma categoria.",
        "",
    ]
    for numero, r in enumerate(escolhidos, 1):
        repo = localizados[r["id"]]
        caminhos = []
        if repo is not None:
            nomes = git(repo, "show", "--format=", "--name-only",
                        "--no-renames", r["id"])
            if nomes is not None:
                caminhos = [x.strip() for x in nomes.splitlines() if x.strip()]
        sinal = sinal_caminhos(caminhos)
        status = "encontrado" if caminhos else "nao_disponivel"
        row = {
            "numero": numero,
            "id": r["id"],
            "titulo": r["titulo"],
            "rotulo_registrado": r["rotulo_registrado"],
            "original": r["original"],
            "palavras_caracteres": r["palavras_caracteres"],
            "erros_modelos": r["erros_modelos"],
            "repositorio_informado": r["repositorios"].split("|")[0],
            "repositorio_git_local": str(repo) if repo else "",
            "contexto_git": status,
            "sinal_caminhos": sinal,
            "quantidade_arquivos": len(caminhos),
            "arquivos": " | ".join(caminhos[:25]),
            "decisao_humana": "",
            "justificativa_humana": "",
        }
        resultados.append(row)
        detalhes += [
            f"## {numero:02d} — {r['titulo']}",
            "",
            f"- ID: {r['id']}",
            f"- Rótulo registrado: **{r['rotulo_registrado']}**",
            f"- SVM original: {r['original']}",
            f"- SVM caracteres: {r['palavras_caracteres']}",
            f"- Git local: {status}",
            f"- Sinal de arquivos: {sinal}",
            "",
        ]
        if repo and caminhos:
            detalhes.append("Arquivos: " + ", ".join(caminhos[:12]))
            detalhes.append("")
            patch = git(repo, "show", "--format=", "--unified=1",
                        "--no-ext-diff", "--no-renames", r["id"], limite=15)
            if patch is not None:
                trecho = "\n".join(patch.splitlines()[:32])[:3600]
                # Fences adicionais evitam quebrar o markdown com trechos Git.
                detalhes += ["~~~diff", trecho, "~~~", ""]
            else:
                detalhes.append("Diff indisponivel localmente.\n")
        else:
            detalhes.append("Diff nao confirmado em clones locais. Nao inferir o rotulo.\n")

    destino.mkdir(parents=True, exist_ok=False)
    with (destino / "casos_para_auditoria.csv").open(
            "x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(resultados[0]))
        writer.writeheader()
        writer.writerows(resultados)
    (destino / "evidencias_git.md").write_text(
        "\n".join(detalhes) + "\n", encoding="utf-8")

    resumo = {
        "protocolo": "auditoria-docs-refactor-apenas-treino",
        "total": len(resultados),
        "por_classe": dict(Counter(r["rotulo_registrado"] for r in resultados)),
        "com_contexto_git_local": sum(r["contexto_git"] == "encontrado"
                                      for r in resultados),
        "sinais": dict(Counter(r["sinal_caminhos"] for r in resultados)),
        "regra": "nenhum rotulo alterado; evidencias para decisao humana",
        "origem": "somente casos_para_revisao.csv gerado por OOF no treino",
    }
    (destino / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    md = [
        "# Auditoria direcionada de rotulos — CommitX",
        "",
        "Somente registros de treino. Nenhuma alteracao no banco SQLite.",
        "O modelo pode estar errado quando discorda do rotulo.",
        "",
        f"- Casos selecionados: {len(resultados)}",
        f"- Contexto Git local confirmado: {resumo['com_contexto_git_local']}",
        f"- Distribuicao: {resumo['por_classe']}",
        "",
        "| # | Rotulo | Previsao original | Evidencia Git | Titulo |",
        "|---:|---|---|---|---|",
    ]
    for r in resultados:
        titulo = r["titulo"].replace("|", "/").replace("\n", " ")[:95]
        md.append(
            f"| {r['numero']} | {r['rotulo_registrado']} | {r['original']} "
            f"| {r['sinal_caminhos']} | {titulo} |")
    md.extend([
        "", "## Revisao",
        "",
        "Examinar evidencias_git.md; registrar decisao_humana e",
        "justificativa_humana em copia de casos_para_auditoria.csv.",
        "Nao mudar automaticamente os rotulos do SQLite e nao usar a avaliacao",
        "externa V1 nem a particao de teste para treinamento.",
        "",
    ])
    (destino / "relatorio.md").write_text(
        "\n".join(md), encoding="utf-8")
    return resumo


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidatos", type=Path,
                   default=Path("resultados/comparacao-svm-caracteres-01/"
                                "casos_para_revisao.csv"))
    p.add_argument("--repos-dir", type=Path, default=Path("repos"))
    p.add_argument("--saida", type=Path,
                   default=Path("resultados/auditoria-treino-30-01"))
    p.add_argument("--quantidade", type=int, default=30)
    args = p.parse_args(argv)
    try:
        resumo = auditar(args.candidatos, args.repos_dir,
                         args.saida, args.quantidade)
    except (OSError, ValueError, csv.Error) as exc:
        p.error(str(exc))
    print("Selecionados:", resumo["total"])
    print("Categorias:", resumo["por_classe"])
    print("Contexto Git local:", resumo["com_contexto_git_local"])
    print("Relatorio:", args.saida / "relatorio.md")
    print("Evidencias:", args.saida / "evidencias_git.md")
    print("CSV revisavel:", args.saida / "casos_para_auditoria.csv")


if __name__ == "__main__":
    main()
