"""Coleta REAL de commits Git locais para um novo conjunto de rotulagem.

O problema: IDs de corpus externo (p.ex. Hugging Face) nao sao hashes Git.
Esta ferramenta consulta apenas Git ja clonado em ./repos/ e preserva SHA,
repositorio, arquivos e contagem de linhas de cada commit.

NAO baixa repositorios, NAO infere etiquetas, NAO treina modelo, NAO modifica
os 500 rotulos existentes, NAO usa particoes de validacao ou teste.

Exemplo:
    python -m commitx.coleta_git_real --raiz repos --por-repo 150 \
        --saida resultados/coleta-git-real-v5-01
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess


SHA = re.compile(r"[0-9a-f]{40}\Z")
PREFIXO = re.compile(r"^(fix|feat|docs|refactor|test)(?:\([^)]+\))?!?:\s*", re.I)
COLUNAS = (
    "id", "titulo", "descricao", "repositorio", "origem",
    "arquivos", "arquivos_modificados", "linhas_adicionadas",
    "linhas_removidas", "indicador_docs", "indicador_testes",
    "prefixo_declarado", "categoria_humana", "clareza_humana",
    "particao",
)


def _git(pasta, *argumentos, timeout=60):
    proc = subprocess.run(
        ["git", "-C", str(pasta), *argumentos], capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False, timeout=timeout,
    )
    if proc.returncode:
        raise ValueError(proc.stderr.strip()[:600] or "Falha ao consultar Git")
    return proc.stdout


def _listar_repos(raiz):
    raiz = Path(raiz).expanduser().resolve()
    if not raiz.is_dir():
        raise ValueError("Pasta de repositorios nao encontrada: " + str(raiz))
    encontrados = []
    for pasta in sorted(raiz.iterdir()):
        if not pasta.is_dir() or pasta.is_symlink():
            continue
        local = pasta.resolve()
        if not local.is_relative_to(raiz):
            continue
        try:
            topo = Path(_git(local, "rev-parse", "--show-toplevel", timeout=10).strip()).resolve()
        except (ValueError, subprocess.TimeoutExpired):
            continue
        if topo == local:
            encontrados.append(local)
    return encontrados


def _ler_log(raiz, *, por_repo):
    """Uma consulta Git por repositorio, sem exportar o patch nem abrir arquivos."""
    bruto = _git(
        raiz, "log", "--all", "--no-merges", f"--max-count={por_repo}",
        "--format=%x1e%H%x1f%s%x1f%b%x1f",
        "--numstat", "--no-renames", "--no-ext-diff",
        timeout=120,
    )
    vistos = set()
    for bloco in bruto.split("\x1e"):
        if not bloco.strip():
            continue
        partes = bloco.split("\x1f", 3)
        if len(partes) != 4:
            continue
        sha, titulo, descricao, estatisticas = partes
        sha, titulo = sha.strip().lower(), titulo.strip()
        if not SHA.fullmatch(sha) or sha in vistos or not titulo:
            continue
        vistos.add(sha)
        arquivos = []
        adicionadas = removidas = 0
        for linha in estatisticas.splitlines():
            campos = linha.split("\t", 2)
            if len(campos) != 3:
                continue
            add, rem, caminho = campos
            if not caminho or caminho.startswith("/") or ".." in Path(caminho).parts:
                continue
            arquivos.append(caminho)
            if add.isdecimal():
                adicionadas += int(add)
            if rem.isdecimal():
                removidas += int(rem)
        if not arquivos:
            # Commits sem numstat nao servem para o experimento de contexto.
            continue
        yield {
            "id": sha,
            "titulo": titulo,
            "descricao": descricao.strip()[:2000],
            "repositorio": "git:" + str(raiz),
            "origem": "git:local_verificado_log",
            "arquivos": " | ".join(arquivos[:60]),
            "arquivos_modificados": len(arquivos),
            "linhas_adicionadas": adicionadas,
            "linhas_removidas": removidas,
            "indicador_docs": int(any(
                p.lower().endswith((".md", ".rst", ".adoc"))
                or p.lower().startswith(("docs/", "doc/"))
                for p in arquivos
            )),
            "indicador_testes": int(any(
                p.lower().startswith(("test/", "tests/"))
                or "/test/" in p.lower()
                or "/tests/" in p.lower()
                or "_test." in p.lower()
                or ".test." in p.lower()
                or ".spec." in p.lower()
                for p in arquivos
            )),
            "prefixo_declarado": (
                m.group(1).lower() if (m := PREFIXO.match(titulo)) else ""
            ),
            # Importante: prefixo e nome de arquivo NAO sao gabarito.
            "categoria_humana": "",
            "clareza_humana": "",
            "particao": "nao_atribuida",
        }


def executar(*, raiz=Path("repos"), por_repo=150, max_repos=20,
             saida=Path("resultados/coleta-git-real-v5-01")):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("A saida ja existe. Informe outro --saida: " + str(saida))
    if not 1 <= por_repo <= 2000:
        raise ValueError("--por-repo deve estar entre 1 e 2000")
    if not 1 <= max_repos <= 100:
        raise ValueError("--max-repos deve estar entre 1 e 100")
    repos = _listar_repos(raiz)[:max_repos]
    if not repos:
        raise ValueError("Nenhum repositorio Git local encontrado diretamente em " + str(raiz))

    linhas, vistos, registros_repos = [], set(), []
    for pasta in repos:
        try:
            candidatos = list(_ler_log(pasta, por_repo=por_repo))
        except (ValueError, subprocess.TimeoutExpired) as erro:
            registros_repos.append({
                "repositorio": str(pasta), "coletados": 0,
                "erro": f"{type(erro).__name__}: {str(erro)[:250]}",
            })
            continue
        aceitos = 0
        for candidato in candidatos:
            if candidato["id"] in vistos:
                # Mesmo commit em forks/repositórios diferentes:
                # nao permitir duplicatas de conteudo entre grupos.
                continue
            vistos.add(candidato["id"])
            linhas.append(candidato)
            aceitos += 1
        registros_repos.append({
            "repositorio": str(pasta), "coletados": aceitos, "erro": "",
        })
    if not linhas:
        raise ValueError("Nenhum commit com arquivos e SHA real foi encontrado")
    relatorio = {
        "protocolo": "coleta-git-real-v5-somente-leitura",
        "total_commits_sha40": len(linhas),
        "repositorios_consultados": len(repos),
        "repositorios_com_commits": sum(r["coletados"] > 0 for r in registros_repos),
        "por_repositorio": registros_repos,
        "prefixos_apenas_informativos": dict(Counter(
            r["prefixo_declarado"] or "sem_prefixo" for r in linhas
        )),
        "sem_rotulos": True,
        "sem_particao": True,
        "limites": [
            "Amostra dos commits recentes e visiveis nas refs locais; nao e representativa por si so.",
            "Nomes de arquivo e prefixos nao comprovam classe; nenhuma etiqueta foi inferida.",
            "Separar futuros treino e validacao por repositorio antes de modelar.",
            "A coleta nao serve ainda como evidência de >80 por cento.",
            "Codigo de terceiros pode conter segredos em mensagens/caminhos; revisar antes de compartilhar CSV.",
            "O patch completo nao foi exportado; somente nomes de arquivos e numstat.",
            "Nenhum rotulo anterior, modelo, particao de teste ou arquivo Git foi alterado.",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    with (saida / "commits_git_reais.csv").open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(linhas)
    (saida / "resumo.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rel = [
        "# Coleta Git real - CommitX V5", "",
        f"- Commits SHA40 com arquivos: **{len(linhas)}**",
        f"- Repositórios locais consultados: **{len(repos)}**",
        f"- Repositórios com commits: **{relatorio['repositorios_com_commits']}**",
        "", "## Repositórios", "",
    ] + [
        f"- {r['repositorio']}: {r['coletados']} commits"
        + (f"; aviso: {r['erro']}" if r["erro"] else "")
        for r in registros_repos
    ] + ["", "## Limitações", ""] + ["- " + t for t in relatorio["limites"]]
    (saida / "resumo.md").write_text("\n".join(rel) + "\n", encoding="utf-8")
    return relatorio


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raiz", type=Path, default=Path("repos"))
    p.add_argument("--por-repo", type=int, default=150)
    p.add_argument("--max-repos", type=int, default=20)
    p.add_argument("--saida", type=Path, default=Path("resultados/coleta-git-real-v5-01"))
    a = p.parse_args(argv)
    try:
        res = executar(raiz=a.raiz, por_repo=a.por_repo,
                       max_repos=a.max_repos, saida=a.saida)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        p.error(str(e))
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print("CSV sem rotulos:", a.saida / "commits_git_reais.csv")


if __name__ == "__main__":
    main()
