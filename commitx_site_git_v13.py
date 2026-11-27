#!/usr/bin/env python3
"""Interface local da V13 experimental com classificação e análise Git independentes."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from commitx.analise_diff import analisar_diff
from commitx.comparador_commit import comparar_commit
from commitx.escrita import revisar_escrita
from commitx.leitor_diff import _git, _previa_patch, analisar_commit
from commitx.modelo_v13 import MODOS, SAIDA, analisar_modelo, situacao
from commitx_site_git_v10 import _analise_estrutural

RAIZ = Path(__file__).resolve().parent
HTML = RAIZ / "commitx" / "site_v13.html"
LIMITE_PREVIA = 6000
LIMITE_ANALISE = 100000
REFERENCIA = re.compile(r"(?:HEAD(?:~[0-9]{1,3})?|[0-9a-fA-F]{7,64})")


def listar_commits(repositorio):
    raiz = Path(_git(repositorio, "rev-parse", "--show-toplevel").strip()).resolve()
    if raiz != repositorio:
        raise ValueError("Informe a pasta raiz do repositório Git.")
    # Sem HEAD num repositório novo, a lista fica vazia.
    try:
        _git(raiz, "rev-parse", "--verify", "HEAD^{commit}")
    except ValueError:
        return []
    lista, truncada = _previa_patch(
        raiz, "log", "-30", "--no-show-signature", "--no-notes", "--no-decorate",
        "-z", "--format=%H%x00%<(180,trunc)%s", "HEAD", "--", max_chars=65536,
    )
    if truncada:
        raise ValueError("A lista de commits excedeu o limite de leitura.")
    campos = lista.split("\0")[:-1]
    return [{"sha": sha, "titulo": titulo.rstrip()} for sha, titulo in zip(campos[::2], campos[1::2])]


def classificar(dados, artefatos, modo=None):
    titulo, descricao = dados.get("titulo"), dados.get("descricao", "")
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 500 or "\n" in titulo or "\r" in titulo:
        raise ValueError("Informe um título de uma linha, entre 1 e 500 caracteres.")
    if not isinstance(descricao, str) or len(descricao) > 2500:
        raise ValueError("Descrição inválida (máximo 2500 caracteres).")
    classificacao = analisar_modelo(artefatos, titulo, modo or dados.get("modo", "auto"))
    try:
        escrita = revisar_escrita(titulo, descricao)
    except ValueError:
        # Títulos que consistem somente em um prefixo já têm motivo de abstenção.
        if not classificacao["motivo"]:
            raise
        escrita = {}
    return {"classificacao": classificacao, "escrita": escrita}


def analisar_git(dados, repositorio, artefatos):
    referencia = dados.get("commit")
    if not isinstance(referencia, str) or not referencia.strip():
        raise ValueError("Selecione um commit ou informe HEAD ou um SHA.")
    if not REFERENCIA.fullmatch(referencia):
        raise ValueError("Use HEAD, HEAD~1 ou um SHA hexadecimal de 7 a 64 caracteres.")
    solicitar_ast = dados.get("analise_estrutural", False)
    if not isinstance(solicitar_ast, bool):
        raise ValueError("A opção de análise estrutural deve ser verdadeira ou falsa.")
    try:
        git = analisar_commit(repositorio, referencia, max_chars=LIMITE_ANALISE)
    except (ValueError, OSError) as erro:
        raise ValueError("Não foi possível ler o commit. Verifique a referência e o repositório.") from erro

    classificacao = None
    aviso = None
    try:
        classificacao = analisar_modelo(artefatos, git["titulo"])
    except FileNotFoundError:
        aviso = "Modelo V13 indisponível."
    except Exception as erro:
        print(f"[Modelo V13] {type(erro).__name__}", file=sys.stderr)
        aviso = "A classificação textual da V13 não está disponível para este commit."

    diff = None
    try:
        diff = analisar_diff(git)
        comparacao = comparar_commit(classificacao or {}, diff, versao="V13", trecho="amostra de análise")
        if aviso and not diff["diff_truncado"] and diff["estado"] == "completo":
            comparacao["explicacao"] = aviso
    except Exception as erro:
        print(f"[Diff V13] {type(erro).__name__}", file=sys.stderr)
        comparacao = {"status": "inconclusivo", "explicacao": "A análise do diff falhou para este commit.",
                      "categorias_codigo": [], "evidencias": []}
    patch = git["diff_previa"]
    previa = {**git, "diff_previa": patch[:LIMITE_PREVIA],
              "diff_truncado": git["diff_truncado"] or len(patch) > LIMITE_PREVIA}
    resposta = {
        "git": previa, "analise": {"classificacao": classificacao} if classificacao else None,
        "aviso_modelo": aviso, "analise_codigo": {"diff": diff, "comparacao": comparacao},
    }
    if solicitar_ast:
        resposta["analise_estrutural"] = _analise_estrutural(repositorio, git)
    return resposta


def criar_handler(artefatos: Path, repositorio: Path):
    pagina = HTML.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def _responder(self, status, tipo, payload):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status, dados):
            payload = json.dumps(dados, ensure_ascii=False).encode("utf-8", "backslashreplace")
            self._responder(status, "application/json; charset=utf-8", payload)

        def _origem_permitida(self):
            # Protege inclusive a leitura da lista de commits de outros sites.
            host = f"127.0.0.1:{self.server.server_port}"
            return (self.headers.get("Host") == host
                    and self.headers.get("Origin", f"http://{host}") == f"http://{host}"
                    and self.headers.get("Sec-Fetch-Site") != "cross-site")

        def do_GET(self):
            rota = urlsplit(self.path).path
            if not self._origem_permitida():
                self._json(403, {"erro": "Origem não permitida."})
            elif rota in ("/", "/index.html"):
                self._responder(200, "text/html; charset=utf-8", pagina)
            elif rota == "/api/status":
                self._json(200, situacao(artefatos))
            elif rota == "/api/git/commits":
                dados = {"repositorio": str(repositorio), "commits": []}
                try:
                    dados["commits"] = listar_commits(repositorio)
                except (ValueError, OSError):
                    dados["erro"] = "Não foi possível listar commits do repositório configurado."
                self._json(200, dados)
            else:
                self.send_error(404)

        def do_POST(self):
            rota = urlsplit(self.path).path
            if rota not in ("/api/classificar", "/api/comparar", "/api/git/analisar"):
                self.send_error(404)
                return
            if not self._origem_permitida():
                self._json(403, {"erro": "Origem não permitida."})
                return
            if self.headers.get_content_type() != "application/json":
                self._json(415, {"erro": "Content-Type deve ser application/json."})
                return
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if not 2 <= tamanho <= 40000:
                    raise ValueError("JSON vazio ou muito grande.")
                dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                if not isinstance(dados, dict):
                    raise ValueError("Envie um objeto JSON.")
                if rota == "/api/git/analisar":
                    resultado = analisar_git(dados, repositorio, artefatos)
                elif rota == "/api/comparar":
                    resultado = {modo: classificar(dados, artefatos, modo)["classificacao"] for modo in MODOS}
                else:
                    resultado = classificar(dados, artefatos)
                self._json(200, resultado)
            except (ValueError, OSError) as erro:
                self._json(400, {"erro": str(erro)})
            except Exception as erro:
                print(f"[Erro V13] {type(erro).__name__}", file=sys.stderr)
                self._json(500, {"erro": "Falha interna. Verifique o terminal do CommitX."})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--artefatos", type=Path, default=SAIDA)
    parser.add_argument("--repositorio", type=Path, default=RAIZ)
    args = parser.parse_args(argv)
    if not 1024 <= args.porta <= 65535:
        parser.error("A porta deve estar entre 1024 e 65535.")
    artefatos = args.artefatos.expanduser().resolve()
    repositorio = args.repositorio.expanduser().resolve()
    with ThreadingHTTPServer(("127.0.0.1", args.porta), criar_handler(artefatos, repositorio)) as servidor:
        print(f"CommitX V13 disponível em http://127.0.0.1:{args.porta}", flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
