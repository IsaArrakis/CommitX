"""Verifica localmente SHAs recuperados sem acessar rede nem alterar dados.

Entrada: CSV gerado por commitx.fase2_vinculos.
Saidas: novo CSV de diagnostico e JSON resumido; nenhum rotulo e modificado.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import subprocess

ENTRADA = Path("resultados/fase2/vinculos-rotulados-01.csv")
SAIDA = Path("resultados/fase2/verificacao-locais-01.csv")
RESUMO = Path("resultados/fase2/verificacao-locais-01.json")
SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
CAMPOS = (
    "id", "particao", "sha_original", "repositorio", "fonte",
    "integridade_id", "situacao_origem", "verificacao_local",
    "arquivos_alterados", "linhas_adicionadas", "linhas_removidas",
)


def _git(repo, *args):
    """Executa somente consultas Git, com timeout e sem shell."""
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def _status(linha):
    if linha.get("integridade_id") != "valido":
        return "integridade_nao_confirmada", None
    if linha.get("fonte") != "git:local":
        return "nao_e_git_local", None
    repo = linha.get("repositorio") or ""
    sha = (linha.get("sha_original") or "").strip()
    if not repo.startswith("git:") or "," in repo:
        return "origem_local_ambigua", None
    if not SHA40.fullmatch(sha):
        return "sha_invalido", None
    pasta = Path(repo[4:]).expanduser()
    if not pasta.is_absolute():
        return "caminho_nao_absoluto", None
    if not pasta.is_dir():
        return "repositorio_ausente", None
    raiz = _git(pasta, "rev-parse", "--show-toplevel")
    if raiz is None:
        return "nao_e_git", None
    if Path(raiz.strip()).resolve() != pasta.resolve():
        return "caminho_nao_e_raiz", None
    verificado = _git(pasta, "rev-parse", "--verify", f"{sha}^{{commit}}")
    if verificado is None or verificado.strip().lower() != sha.lower():
        return "commit_indisponivel", None
    return "sha_verificado_local", pasta


def verificar(entrada=ENTRADA, saida=SAIDA, resumo=RESUMO):
    entrada, saida, resumo = map(Path, (entrada, saida, resumo))
    if len({p.resolve() for p in (entrada, saida, resumo)}) != 3:
        raise ValueError("Entrada e saidas precisam de caminhos diferentes.")
    if not entrada.is_file():
        raise ValueError("CSV de vinculos nao encontrado: " + str(entrada))
    if any(p.exists() or p.is_symlink() for p in (saida, resumo)):
        raise FileExistsError("Saida ja existe. Use outro nome de arquivo.")

    cont = Counter()
    with entrada.open(encoding="utf-8-sig", newline="") as origem:
        leitor = csv.DictReader(origem)
        necessarios = {
            "id", "particao", "sha_original", "repositorio",
            "fonte", "integridade_id", "situacao_origem",
        }
        if not necessarios.issubset(leitor.fieldnames or []):
            raise ValueError("CSV sem colunas: " + ", ".join(
                sorted(necessarios - set(leitor.fieldnames or []))
            ))
        saida.parent.mkdir(parents=True, exist_ok=True)
        with saida.open("x", encoding="utf-8", newline="") as destino:
            escritor = csv.DictWriter(destino, fieldnames=CAMPOS)
            escritor.writeheader()
            for linha in leitor:
                estado, pasta = _status(linha)
                cont["registros"] += 1
                cont["status_" + estado] += 1
                arquivos = acrescimos = remocoes = ""
                # Apenas estatisticas, jamais ler ou publicar conteudo do patch.
                if pasta is not None:
                    sha = linha["sha_original"].strip()
                    pais = _git(pasta, "rev-list", "--parents", "-n", "1", sha)
                    if pais:
                        p = pais.strip().split()[1:]
                        if p:
                            raw = _git(pasta, "diff", "--no-ext-diff",
                                       "--no-renames", "--numstat", p[0], sha, "--")
                        else:
                            raw = _git(pasta, "diff-tree", "--root", "--no-commit-id",
                                       "--no-renames", "--numstat", "-r", sha)
                        if raw is not None:
                            entries = [row.split("\t", 2) for row in raw.splitlines()]
                            entries = [e for e in entries if len(e) == 3]
                            arquivos = len(entries)
                            acrescimos = sum(int(e[0]) for e in entries if e[0].isdigit())
                            remocoes = sum(int(e[1]) for e in entries if e[1].isdigit())
                            cont["diff_estatisticas_disponiveis"] += 1
                        else:
                            cont["diff_estatisticas_indisponiveis"] += 1
                escritor.writerow({
                    **{c: linha.get(c, "") for c in CAMPOS},
                    "verificacao_local": estado,
                    "arquivos_alterados": arquivos,
                    "linhas_adicionadas": acrescimos,
                    "linhas_removidas": remocoes,
                })

    relatorio = {
        "contagens": dict(sorted(cont.items())),
        "entrada": str(entrada),
        "saida_csv": str(saida),
        "nota": (
            "Apenas verifica objetos Git locais e estatisticas de alteracao. "
            "Nao baixa repositorios, nao le patches completos, nao altera rotulos, "
            "nao treina modelos e nao avalia particoes de teste."
        ),
    }
    resumo.parent.mkdir(parents=True, exist_ok=True)
    with resumo.open("x", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--resumo", type=Path, default=RESUMO)
    args = parser.parse_args(argv)
    try:
        relatorio = verificar(args.entrada, args.saida, args.resumo)
    except (ValueError, OSError, csv.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
