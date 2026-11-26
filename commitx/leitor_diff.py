"""Leitura segura e somente leitura do diff de um commit local.

Uso:
    python -m commitx.leitor_diff --repositorio . --commit HEAD
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager, suppress
import json
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic


_TIMEOUT_GIT = 20


def _ambiente_git():
    # A consulta a um clone parcial também deve ser somente leitura.
    return {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "",
            "GIT_OPTIONAL_LOCKS": "0"}


@contextmanager
def _erros_git():
    try:
        yield
    except FileNotFoundError as erro:
        raise ValueError("Git não encontrado. Instale o Git para continuar.") from erro
    except subprocess.TimeoutExpired as erro:
        raise ValueError(f"Consulta Git demorou mais de {_TIMEOUT_GIT} segundos.") from erro


def _verificar_saida(codigo, detalhe):
    if codigo:
        raise ValueError(
            "Git não conseguiu executar a consulta: "
            + (detalhe.strip() or "repositório ou commit inválido")
        )


def _git(repositorio, *argumentos, bruto=False):
    with _erros_git():
        processo = subprocess.run(
            ["git", "-C", str(repositorio), *argumentos],
            capture_output=True, env=_ambiente_git(), encoding=None if bruto else "utf-8",
            errors=None if bruto else "replace", timeout=_TIMEOUT_GIT, check=False,
        )
    detalhe = processo.stderr.decode("utf-8", "replace") if bruto else processo.stderr
    _verificar_saida(processo.returncode, detalhe)
    return processo.stdout


def _capturar_prefixo(fluxo, limite):
    # TextIOWrapper resolve UTF-8 e quebras de linha antes de contar caracteres.
    prefixo = fluxo.read(limite + 1)
    truncado = len(prefixo) > limite
    if truncado:
        # Drena o restante em blocos para obter o status real de saída do Git.
        while fluxo.buffer.read(65536):
            pass
    return prefixo[:limite], truncado


def _previa_patch(repositorio, *argumentos, max_chars):
    with _erros_git(), subprocess.Popen(
        ["git", "-C", str(repositorio), *argumentos],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_ambiente_git(),
        text=True, encoding="utf-8", errors="replace", start_new_session=os.name == "posix",
    ) as processo, ThreadPoolExecutor(max_workers=2) as leitores:
        prazo = monotonic() + _TIMEOUT_GIT
        try:
            # As duas saídas precisam escoar mesmo quando uma delas enche o pipe.
            previa = leitores.submit(_capturar_prefixo, processo.stdout, max_chars)
            diagnostico = leitores.submit(_capturar_prefixo, processo.stderr, 4096)
            _, pendentes = wait((previa, diagnostico), timeout=_TIMEOUT_GIT)
            if pendentes:
                raise subprocess.TimeoutExpired(processo.args, _TIMEOUT_GIT)
            codigo = processo.wait(timeout=max(0, prazo - monotonic()))
        except BaseException:
            # Um auxiliar do Git também pode manter o pipe aberto após a saída do pai.
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(processo.pid, signal.SIGKILL)
            else:
                processo.kill()
            raise
        _verificar_saida(codigo, diagnostico.result()[0])
        return previa.result()


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
    # Para commits com pais, compara sempre com o primeiro pai. Isso evita
    # a saída vazia que "git show" pode produzir em commits de merge.
    pais = _git(raiz, "rev-list", "--parents", "-n", "1", sha).strip().split()[1:]
    if pais:
        linhas = _git(
            raiz, "diff", "--numstat", "-z", "--no-ext-diff", "--no-renames",
            "--no-textconv", pais[0], sha, "--", bruto=True,
        )
    else:
        linhas = _git(
            raiz, "diff-tree", "--root", "--no-commit-id", "--numstat", "-z",
            "-r", "--no-renames", "--no-ext-diff", "--no-textconv", sha, "--", bruto=True,
        )
    arquivos = []
    adicionadas = removidas = 0
    for registro in linhas.split(b"\0"):
        if not registro:
            continue
        a, r, nome = registro.split(b"\t", 2)
        adicoes = None if a == b"-" else int(a)
        remocoes = None if r == b"-" else int(r)
        adicionadas += adicoes or 0
        removidas += remocoes or 0
        arquivos.append({"arquivo": nome.decode("utf-8", "replace"),
                         "adicionadas": adicoes, "removidas": remocoes})
    if pais:
        previa, truncado = _previa_patch(
            raiz, "diff", "--patch", "--no-ext-diff", "--no-renames",
            "--no-color", "--no-textconv", pais[0], sha, "--", max_chars=max_chars,
        )
    else:
        previa, truncado = _previa_patch(
            raiz, "show", "--format=", "--no-ext-diff",
            "--no-renames", "--no-color", "--no-textconv", sha, "--", max_chars=max_chars,
        )
    return {
        "commit": sha,
        "comparado_com": pais[0] if pais else None,
        "merge": len(pais) > 1,
        "titulo": titulo,
        "descricao": corpo,
        "quantidade_arquivos": len(arquivos),
        "linhas_adicionadas": adicionadas,
        "linhas_removidas": removidas,
        "arquivos": arquivos,
        "diff_previa": previa,
        "diff_truncado": truncado,
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
    if resultado["merge"]:
        print("Commit de merge: diferenças em relação ao primeiro pai.")
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
