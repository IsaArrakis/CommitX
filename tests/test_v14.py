"""Integração HTTP da interface V14 com o formato original da V12."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.request import Request, urlopen

import joblib

from commitx.escrita import texto_modelo
from commitx.foco_docs_refactor_v10 import pesos_do_fold
from commitx.v12_final import (
    CLASSES, MANIFESTO, MODEL_COM, MODEL_SEM, _sha256, analisar_modelo, novo_modelo_v12,
)
from commitx_site_git_v13 import criar_handler
from commitx_site_git_v14 import CLASSIFICADOR_V12


def pacote_v12(pasta):
    titulos = ["fix: Correct parser bug", "feat: Add an API", "docs: Update README",
               "refactor: Extract helper method", "test: Add tests for parser"]
    hashes = {}
    for nome, textos in ((MODEL_COM, titulos), (MODEL_SEM, [texto_modelo(t) for t in titulos])):
        arq = pasta / nome
        joblib.dump(novo_modelo_v12(pesos_do_fold(CLASSES, 1.75, 1.50)).fit(textos, CLASSES), arq)
        hashes[nome] = _sha256(arq)
    (pasta / MANIFESTO).write_text(
        json.dumps({"versao": "V12-final-v12_extra_030", "artefatos_sha256": hashes}), encoding="utf-8",
    )
    return hashes


class InterfaceV14Test(unittest.TestCase):
    def test_pagina_e_endpoints_reutilizam_v12(self):
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            hashes = pacote_v12(pasta)
            handler = criar_handler(pasta, pasta, classificador=CLASSIFICADOR_V12, interface="V14")
            with ThreadingHTTPServer(("127.0.0.1", 0), handler) as servidor:
                tarefa = Thread(target=servidor.serve_forever)
                tarefa.start()
                base = f"http://127.0.0.1:{servidor.server_port}"
                try:
                    with urlopen(base, timeout=3) as resposta:
                        pagina = resposta.read().decode("utf-8")
                    self.assertIn("Interface V14 · Classificador V12 oficial", pagina)
                    self.assertIn('data-classificador="V12"', pagina)
                    with urlopen(base + "/api/status", timeout=3) as resposta:
                        status = json.load(resposta)
                    self.assertTrue(status["pronto"])
                    self.assertEqual((status["interface"], status["classificador"]), ("V14", "V12"))

                    def enviar(rota, titulo):
                        req = Request(base + rota, json.dumps({"titulo": titulo}).encode(),
                                      {"Content-Type": "application/json"})
                        with urlopen(req, timeout=3) as resposta:
                            return json.load(resposta)

                    titulo = "feat: Add an API"
                    self.assertEqual(enviar("/api/classificar", titulo)["classificacao"],
                                     analisar_modelo(pasta, titulo))
                    for modo, resultado in enviar("/api/comparar", titulo).items():
                        original = analisar_modelo(pasta, titulo, modo)
                        self.assertEqual({k: resultado[k] for k in original}, original)
                    abstencao = enviar("/api/classificar", "chore: Update dependencies")["classificacao"]
                    self.assertIsNone(abstencao["categoria_sugerida"])
                    self.assertIn("fora das cinco classes", abstencao["motivo"])
                finally:
                    servidor.shutdown()
                    tarefa.join()
            self.assertEqual(hashes, {nome: _sha256(pasta / nome) for nome in hashes})
