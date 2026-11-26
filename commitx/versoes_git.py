"""Recupera versões de arquivos Python diretamente dos objetos Git locais."""

import math
import os
import re
import selectors
import subprocess
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from time import monotonic


_SHA = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")
_STATUS = {b"A": "adicionado", b"D": "removido", b"M": "modificado", b"T": "modificado"}


@dataclass(frozen=True)
class OrcamentoLeitura:
    """Limites da consulta. Os bytes por arquivo somam as duas versões."""

    max_arquivos: int = 100
    max_bytes_arquivo: int = 256 * 1024
    max_bytes_totais: int = 2 * 1024 * 1024
    segundos: float = 10

    def __post_init__(self):
        limites = (self.max_arquivos, self.max_bytes_arquivo, self.max_bytes_totais)
        if any(type(valor) is not int or valor < 0 for valor in limites):
            raise ValueError("Os limites de arquivos e bytes devem ser inteiros não negativos.")
        if type(self.segundos) not in (int, float) or not math.isfinite(self.segundos) or self.segundos < 0:
            raise ValueError("O prazo deve ser finito e não negativo.")


class _Git:
    def __init__(self, repositorio, segundos):
        self.prazo = monotonic() + segundos
        self.comando = [
            "git", "--no-replace-objects", "-C", str(Path(repositorio).resolve(strict=True)),
            "-c", "core.fsmonitor=false", "-c", f"core.hooksPath={os.devnull}",
        ]
        self.ambiente = {
            "PATH": os.defpath, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "",
        }

    def restante(self):
        tempo = self.prazo - monotonic()
        if tempo <= 0:
            raise TimeoutError
        return tempo

    def blocos(self, *args):
        self.restante()
        with subprocess.Popen(self.comando + list(args), env=self.ambiente,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL) as proc:
            try:
                with selectors.DefaultSelector() as seletor:
                    seletor.register(proc.stdout, selectors.EVENT_READ)
                    while seletor.select(self.restante()):
                        bloco = os.read(proc.stdout.fileno(), 64 * 1024)
                        if not bloco:
                            if proc.wait(timeout=self.restante()):
                                raise OSError("Consulta ao Git local falhou.")
                            return
                        yield bloco
                    raise TimeoutError
            finally:
                if proc.poll() is None:
                    proc.kill()

    def ler(self, limite, *args):
        dados = bytearray()
        with closing(self.blocos(*args)) as blocos:
            for bloco in blocos:
                if len(dados) + len(bloco) > limite:
                    raise OSError("Saída Git maior que o limite previsto.")
                dados.extend(bloco)
        return dados

    def campos(self, separador, *args):
        pendente = bytearray()
        with closing(self.blocos(*args)) as blocos:
            for bloco in blocos:
                partes = bloco.split(separador)
                pendente.extend(partes[0])
                if len(pendente) > 1024 * 1024:
                    raise OSError("Campo Git excede o limite de metadados.")
                if len(partes) > 1:
                    yield bytes(pendente)
                    yield from partes[1:-1]
                    pendente = bytearray(partes[-1])
        if pendente:
            raise OSError("Campo Git incompleto.")

    def primeiro_pai(self, sha):
        # O cabeçalho do objeto mantém o pai real inclusive em clones rasos.
        with closing(self.campos(b"\n", "cat-file", "commit", sha)) as linhas:
            arvore = next(linhas, b"")
            if not arvore.startswith(b"tree "):
                raise OSError("Cabeçalho do commit indisponível.")
            linha = next(linhas, b"")
            if linha.startswith(b"parent "):
                pai = linha[7:].decode("ascii")
                if len(pai) != len(sha) or not _SHA.fullmatch(pai):
                    raise OSError("Identificador do primeiro pai inválido.")
                return pai
            return None


def _alteracoes(git, sha, pai):
    args = ["diff-tree", "--raw", "-z", "-r", "--no-commit-id", "--no-abbrev",
            "--no-renames", "--no-ext-diff", "--no-textconv", "--ignore-submodules=none"]
    revisoes = [pai, sha] if pai else ["--root", sha]
    with closing(git.campos(b"\0", *args, *revisoes, "--")) as campos:
        for cabecalho in campos:
            git.restante()
            caminho = next(campos, None)
            if caminho is None:
                raise OSError("Inventário Git incompleto.")
            if caminho.endswith((b".py", b".pyi")):
                modo_a, modo_p, oid_a, oid_p, status = cabecalho[1:].split()
                if status not in _STATUS:
                    raise OSError("Tipo de alteração Git inesperado.")
                yield os.fsdecode(caminho), _STATUS[status], (modo_a, oid_a), (modo_p, oid_p)


def _versao(git, modo, oid, limite_arquivo, limite_total):
    versao = {"conteudo": None, "tamanho_bytes": None, "motivo": None}
    if modo == b"000000":
        versao["motivo"] = "nao_aplicavel"
        return versao, 0
    if modo not in (b"100644", b"100755"):
        versao["motivo"] = "tipo_nao_suportado"
        return versao, 0

    cobrados = 0
    try:
        objeto = oid.decode("ascii")
        if not _SHA.fullmatch(objeto):
            raise ValueError("Identificador de blob inválido.")
        tamanho = int(git.ler(64, "cat-file", "-s", objeto))
        versao["tamanho_bytes"] = tamanho
        if tamanho < 0:
            raise ValueError("Tamanho de blob inválido.")
        if tamanho > limite_arquivo:
            versao["motivo"] = "limite_bytes_arquivo"
        elif tamanho > limite_total:
            versao["motivo"] = "limite_bytes_totais"
        else:
            cobrados = tamanho
            bruto = git.ler(tamanho, "cat-file", "blob", objeto)
            if len(bruto) != tamanho:
                raise OSError("Blob Git incompleto.")
            if b"\0" in bruto:
                versao["motivo"] = "binario"
            else:
                versao["conteudo"] = bruto.decode("utf-8")
    except UnicodeDecodeError:
        versao["motivo"] = "utf8_invalido"
    except (TimeoutError, subprocess.TimeoutExpired):
        versao["motivo"] = "limite_tempo"
    except (OSError, ValueError):
        versao["motivo"] = "objeto_indisponivel"
    return versao, cobrados


def ler_versoes_git(repositorio, sha, orcamento=OrcamentoLeitura()):
    """Retorna cobertura e duas versões por caminho, usando o primeiro pai.

    A ausência esperada de um lado (adição ou remoção) mantém a cobertura.
    Um SHA inválido ou que não identifique um commit local gera ValueError.
    """
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("Informe um SHA completo em hexadecimal.")
    sha = sha.lower()
    resultado = {"commit": sha, "comparado_com": None, "arquivos": [],
                 "cobertura": "completa", "limitacoes": []}
    arquivos, limitacoes = resultado["arquivos"], resultado["limitacoes"]
    saldo = orcamento.max_bytes_totais

    try:
        git = _Git(repositorio, orcamento.segundos)
        formato = bytes(git.ler(32, "rev-parse", "--show-object-format")).strip()
        if len(sha) != {b"sha1": 40, b"sha256": 64}.get(formato):
            raise ValueError("SHA incompatível com o formato do repositório.")
        if git.ler(32, "cat-file", "-t", sha).strip() != b"commit":
            raise ValueError("O SHA deve identificar um commit.")
    except (TimeoutError, subprocess.TimeoutExpired):
        resultado.update(cobertura="indisponivel", limitacoes=["limite_tempo"])
        return resultado
    except OSError as erro:
        raise ValueError("Repositório, Git ou commit local indisponível.") from erro

    try:
        pai = git.primeiro_pai(sha)
        resultado["comparado_com"] = pai
        with closing(_alteracoes(git, sha, pai)) as alteracoes:
            for caminho, status, anterior, posterior in alteracoes:
                if len(arquivos) >= orcamento.max_arquivos:
                    limitacoes.append("limite_arquivos")
                    break
                antes, custo = _versao(git, *anterior, orcamento.max_bytes_arquivo, saldo)
                saldo -= custo
                depois, gasto = _versao(git, *posterior, orcamento.max_bytes_arquivo - custo, saldo)
                saldo -= gasto
                motivos = [v["motivo"] for v in (antes, depois) if v["motivo"] not in (None, "nao_aplicavel")]
                arquivos.append({"caminho": caminho, "status": status,
                                 "anterior": antes, "posterior": depois,
                                 "cobertura": "parcial" if motivos else "completa"})
                for motivo in motivos:
                    if motivo not in limitacoes:
                        limitacoes.append(motivo)
                if "limite_tempo" in motivos:
                    break
    except (TimeoutError, subprocess.TimeoutExpired):
        limitacoes.append("limite_tempo")
    except (OSError, ValueError):
        limitacoes.append("inventario_indisponivel")
    if limitacoes:
        resultado["cobertura"] = "parcial" if arquivos or limitacoes == ["limite_arquivos"] else "indisponivel"
    return resultado
