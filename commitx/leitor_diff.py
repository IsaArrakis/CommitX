"""Leitura segura e somente leitura do diff de um commit local.

Uso:
    python -m commitx.leitor_diff --repositorio . --commit HEAD
"""
import argparse
import json
from pathlib import Path
import subprocess


def _git(repositorio, *argumentos):
    try:
        processo = subprocess.run(
            ["git", "-C", str(repositorio), *argumentos],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20, check=False,
        )
    except FileNotFoundError as erro:
        raise ValueError("Git não encontrado. Instale o Git para continuar.") from erro
    except subprocess.TimeoutExpired as erro:
        raise ValueError("Consulta Git demorou mais de 20 segundos.") from erro
    if processo.returncode:
        raise ValueError(
            "Git não conseguiu executar a consulta: "
            + (processo.stderr.strip() or "repositório ou commit inválido")
        )
    return processo.stdout


def analisar_commit(repositorio, commit="HEAD", *, max_chars=8000):
    """Retorna metadados e trecho do patch, sem alterar arquivos ou rótulos.

    A prévia truncada não deve ser tratada como o diff completo.
    """
    caminho = Path(repositorio).expanduser().resolve()
    if not caminho.is_dir():
        raise ValueError("O caminho informado não é uma pasta.")
    if not isinstance(commit, str) or not commit or commit.startswith("-"):
        raise ValueError("Informe um commit válido, como HEAD ou um SHA.")
    if not 100 <= max_chars <= 100000:
        raise ValueError("--max-caracteres deve estar entre 100 e 100000")

    raiz = Path(_git(caminho, "rev-parse", "--show-toplevel").strip()).resolve()
    # Evita aceitar subpastas internas a outro repositório por engano.
    if caminho != raiz:
        raise ValueError("Informe a pasta raiz do repositório Git.")
    # Resolve a referência para SHA e impede confusão com opções do Git.
    sha = _git(raiz, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    titulo = _git(raiz, "show", "-s", "--format=%s", sha).strip()
    corpo = _git(raiz, "show", "-s", "--format=%b", sha).strip()
    linhas = _git(
        raiz, "diff-tree", "--root", "--no-commit-id", "--numstat",
        "-r", "--no-renames", sha,
    )
    arquivos = []
    adicionadas = removidas = 0
    for linha in linhas.splitlines():
        partes = linha.split("\t", 2)
        if len(partes) != 3:
            continue
        a, r, nome = partes
        if a.isdigit() and r.isdigit():
            adicionadas += int(a)
            removidas += int(r)
        arquivos.append({"arquivo": nome, "adicionadas": int(a) if a.isdigit() else None,
                         "removidas": int(r) if r.isdigit() else None})
    patch = _git(
        raiz, "show", "--format=", "--no-ext-diff",
        "--no-renames", "--no-color", "--no-textconv", sha,
    )
    return {
        "commit": sha,
        "titulo": titulo,
        "descricao": corpo,
        "quantidade_arquivos": len(arquivos),
        "linhas_adicionadas": adicionadas,
        "linhas_removidas": removidas,
        "arquivos": arquivos,
        "diff_previa": patch[:max_chars],
        "diff_truncado": len(patch) > max_chars,
        "observacao": "Dados descritivos; não são uma classificação automática.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mostra o que mudou em um commit Git local.")
    parser.add_argument("--repositorio", type=Path, default=Path("."))
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--max-caracteres", type=int, default=8000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        resultado = analisar_commit(
            args.repositorio, args.commit, max_chars=args.max_caracteres
        )
    except (ValueError, OSError) as erro:
        parser.error(str(erro))
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0
    print("Commit:", resultado["commit"][:12])
    print("Mensagem:", resultado["titulo"])
    print("Arquivos alterados:", resultado["quantidade_arquivos"])
    print("Linhas adicionadas:", resultado["linhas_adicionadas"])
    print("Linhas removidas:", resultado["linhas_removidas"])
    for arquivo in resultado["arquivos"]:
        print(" -", arquivo["arquivo"])
    print("\nTrecho do git diff (linhas - removidas, + adicionadas):")
    print(resultado["diff_previa"] or "(sem diff textual)")
    if resultado["diff_truncado"]:
        print("\n[Prévia truncada; o diff completo pode ser maior.]")
    print("\nAinda não há previsão de categoria nesta etapa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
