"""Exercita a rota Git em loopback com commits temporários."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from commitx.escrita import revisar_escrita
from commitx.leitor_diff import analisar_commit
from commitx_site_git_v10 import criar_handler


class TestApiGit(unittest.TestCase):
    def setUp(self):
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.artefatos = Path(pasta.name) / "artefatos"
        self.artefatos.mkdir()
        self.repo = Path(pasta.name) / "repo"
        self.repo.mkdir()
        configuracao = patch.dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        configuracao.start()
        self.addCleanup(configuracao.stop)
        self.git("init", "-q")
        self.git("config", "user.name", "Teste CommitX")
        self.git("config", "user.email", "teste@example.com")
        self.git("config", "core.autocrlf", "false")

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), criar_handler(self.artefatos, self.repo))
        thread = Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(servidor.shutdown)
        self.porta = servidor.server_port

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, conteudo="# Guia\n"):
        (self.repo / "README.md").write_text(conteudo, encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "docs: atualizar guia", "-m", "Descrição de exemplo")
        return self.git("rev-parse", "HEAD")

    def post(self, dados):
        conexao = HTTPConnection("127.0.0.1", self.porta, timeout=5)
        try:
            conexao.request("POST", "/api/git/analisar", json.dumps(dados),
                            {"Content-Type": "application/json"})
            resposta = conexao.getresponse()
            self.assertEqual(resposta.getheader("Content-Type"), "application/json; charset=utf-8")
            return resposta.status, json.loads(resposta.read())
        finally:
            conexao.close()

    def test_commit_existente_e_compatibilidade_do_json(self):
        sha = self.commit()
        v12 = {"categoria_sugerida": "docs", "modo": "com_prefixo", "avisos": ["Aviso V12."]}
        with patch("commitx_site_git_v10.analisar_modelo", return_value=v12) as modelo:
            status, dados = self.post({"commit": sha, "repositorio": str(self.repo / "inexistente")})
        self.assertEqual(status, 200)
        self.assertEqual(set(dados), {"git", "analise", "sinais", "analise_codigo"})
        self.assertEqual(dados["git"], analisar_commit(self.repo, sha, max_chars=6000))
        modelo.assert_called_once_with(self.artefatos, dados["git"]["titulo"], "auto")
        self.assertEqual(dados["analise"], {
            "classificacao": v12,
            "escrita": revisar_escrita(dados["git"]["titulo"], dados["git"]["descricao"]),
        })
        self.assertEqual(dados["sinais"], {
            "indicio_forte": "docs",
            "observacao": ("Todos os arquivos listados parecem ser documentação. "
                           "A previsão textual é compatível com esse indício, mas não confirma a intenção."),
        })
        analise = dados["analise_codigo"]
        self.assertEqual(analise["diff"]["indicios"]["categoria"], "docs")
        self.assertEqual(analise["comparacao"]["status"], "compativel")

    def test_sha_invalido_ou_inexistente(self):
        self.commit()
        for referencia in ["--help", "0" * 40]:
            with self.subTest(referencia=referencia):
                status, dados = self.post({"commit": referencia})
                self.assertEqual(status, 400)
                self.assertIn("erro", dados)
                self.assertNotIn(str(self.repo), dados["erro"])

    def test_diff_vazio(self):
        self.commit()
        self.git("commit", "--allow-empty", "-qm", "docs: sem alterações")
        with patch("commitx_site_git_v10.analisar_modelo", return_value={"categoria_sugerida": "docs"}):
            status, dados = self.post({})
        self.assertEqual(status, 200)
        self.assertEqual(dados["git"]["diff_previa"], "")
        comparacao = dados["analise_codigo"]["comparacao"]
        self.assertEqual(comparacao["status"], "inconclusivo")
        self.assertEqual(comparacao["evidencias"], [])
        self.assertIn("indícios", comparacao["explicacao"])

    def test_diff_truncado(self):
        self.commit("# Guia\n" * 1200)
        with patch("commitx_site_git_v10.analisar_modelo", return_value={"categoria_sugerida": "docs"}):
            status, dados = self.post({"commit": "HEAD"})
        self.assertEqual(status, 200)
        self.assertTrue(dados["git"]["diff_truncado"])
        self.assertEqual(len(dados["git"]["diff_previa"]), 6000)
        comparacao = dados["analise_codigo"]["comparacao"]
        self.assertEqual(comparacao["status"], "inconclusivo")
        self.assertTrue(any("truncada" in aviso for aviso in comparacao["avisos"]))

    def test_modelos_ausentes(self):
        self.commit()
        status, dados = self.post({"commit": "HEAD"})
        self.assertEqual(status, 200)
        self.assertIsNone(dados["analise"])
        self.assertEqual(dados["sinais"]["indicio_forte"], "docs")
        analise = dados["analise_codigo"]
        self.assertEqual(analise["diff"]["indicios"]["categoria"], "docs")
        self.assertEqual(analise["comparacao"]["status"], "inconclusivo")
        self.assertIn("indisponíveis", analise["comparacao"]["explicacao"])

    def test_falha_semantica_preserva_campos_anteriores(self):
        self.commit()
        with (
            patch("commitx_site_git_v10.analisar_modelo", return_value={"categoria_sugerida": "docs"}),
            patch("commitx_site_git_v10.analisar_diff", side_effect=ValueError("conteúdo reservado")),
        ):
            status, dados = self.post({"commit": "HEAD"})
        self.assertEqual(status, 200)
        self.assertEqual(dados["analise"]["classificacao"]["categoria_sugerida"], "docs")
        self.assertEqual(dados["sinais"]["indicio_forte"], "docs")
        self.assertIsNone(dados["analise_codigo"]["diff"])
        self.assertEqual(dados["analise_codigo"]["comparacao"]["status"], "inconclusivo")
        self.assertNotIn("conteúdo reservado", json.dumps(dados))
