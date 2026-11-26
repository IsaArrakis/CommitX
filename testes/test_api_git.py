"""Exercita a rota Git em loopback com commits temporários."""

from hashlib import sha256
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
from commitx.v12_final import MANIFESTO, MODEL_COM, MODEL_SEM
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

    def post(self, dados, rota="/api/git/analisar"):
        return self.requisitar("POST", rota, json.dumps(dados))

    def requisitar(self, metodo, rota, corpo=None):
        conexao = HTTPConnection("127.0.0.1", self.porta, timeout=5)
        try:
            conexao.request(metodo, rota, corpo,
                            {"Content-Type": "application/json"})
            resposta = conexao.getresponse()
            self.assertEqual(resposta.getheader("Content-Type"), "application/json; charset=utf-8")
            return resposta.status, json.loads(resposta.read())
        finally:
            conexao.close()

    def criar_artefatos_temporarios(self):
        hashes = {}
        for nome in (MODEL_COM, MODEL_SEM):
            conteudo = f"Bytes de teste para {nome}".encode("utf-8")
            (self.artefatos / nome).write_bytes(conteudo)
            hashes[nome] = sha256(conteudo).hexdigest()
        manifesto = {"versao": "V12-final-v12_extra_030", "artefatos_sha256": hashes,
                     "paridade_oof": {"com_prefixo": {"paridade": True}}}
        self.gravar_manifesto(manifesto)
        return manifesto

    def gravar_manifesto(self, dados):
        (self.artefatos / MANIFESTO).write_text(json.dumps(dados), encoding="utf-8")

    def verificar_status_v12(self, estado, oof):
        with patch("commitx.v12_final.joblib.load") as carregar:
            status, dados = self.requisitar("GET", "/api/status")
        carregar.assert_not_called()
        self.assertEqual(status, 200)
        self.assertEqual(dados, {"pronto": estado == "pronto", "oof": oof, "estado": estado})

    def test_status_pronto_com_hashes_validos(self):
        manifesto = self.criar_artefatos_temporarios()
        self.verificar_status_v12("pronto", manifesto["paridade_oof"])

    def test_status_indica_cada_artefato_ausente(self):
        for nome in (MANIFESTO, MODEL_COM, MODEL_SEM):
            with self.subTest(nome=nome):
                manifesto = self.criar_artefatos_temporarios()
                (self.artefatos / nome).unlink()
                oof = {} if nome == MANIFESTO else manifesto["paridade_oof"]
                self.verificar_status_v12("artefatos_ausentes", oof)

    def test_status_manifesto_incompativel(self):
        manifesto = self.criar_artefatos_temporarios()
        self.gravar_manifesto({**manifesto, "versao": "outra-versao"})
        self.verificar_status_v12("manifesto_incompativel", manifesto["paridade_oof"])
        self.gravar_manifesto([])
        self.verificar_status_v12("manifesto_incompativel", {})
        (self.artefatos / MANIFESTO).write_bytes(b"{")
        self.verificar_status_v12("manifesto_incompativel", {})

    def test_status_detecta_adulteracao_em_cada_modelo(self):
        for nome in (MODEL_COM, MODEL_SEM):
            with self.subTest(nome=nome):
                manifesto = self.criar_artefatos_temporarios()
                (self.artefatos / nome).write_bytes(b"artefato alterado")
                self.verificar_status_v12("integridade_invalida", manifesto["paridade_oof"])

    def test_status_exige_os_dois_hashes_no_manifesto(self):
        manifesto = self.criar_artefatos_temporarios()
        del manifesto["artefatos_sha256"][MODEL_SEM]
        self.gravar_manifesto(manifesto)
        self.verificar_status_v12("integridade_invalida", manifesto["paridade_oof"])

    def test_classificar_sem_modelos_preserva_erro_e_abstencao(self):
        status, dados = self.post({"titulo": "docs: atualizar guia"}, "/api/classificar")
        self.assertEqual(status, 400)
        self.assertEqual(set(dados), {"erro"})
        status, dados = self.post({"titulo": "ci: atualizar workflow"}, "/api/classificar")
        self.assertEqual(status, 200)
        self.assertEqual(set(dados), {"classificacao", "escrita"})
        self.assertIsNone(dados["classificacao"]["categoria_sugerida"])

    def test_classificar_rejeita_artefato_alterado_antes_de_carregar(self):
        self.criar_artefatos_temporarios()
        (self.artefatos / MODEL_SEM).write_bytes(b"artefato alterado")
        with patch("commitx.v12_final.joblib.load") as carregar:
            status, dados = self.post({"titulo": "docs: atualizar guia", "modo": "sem_prefixo"},
                                      "/api/classificar")
        carregar.assert_not_called()
        self.assertEqual(status, 400)
        self.assertEqual(set(dados), {"erro"})
        self.assertIn("Artefato ausente ou alterado", dados["erro"])

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

    def test_repositorio_sem_commits(self):
        status, dados = self.post({"commit": "HEAD"})
        self.assertEqual(status, 400)
        self.assertIn("Verifique a referência", dados["erro"])

    def test_codigo_do_commit_nao_e_executado(self):
        sentinela = self.repo.parent / "sentinela"
        (self.repo / "modulo.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(sentinela)!r}).write_text('executado')\n"
            "def exemplo():\n    return 1\n",
            encoding="utf-8",
        )
        self.git("add", "modulo.py")
        self.git("commit", "-qm", "feat: adicionar módulo")
        sha = self.git("rev-parse", "HEAD")
        status, dados = self.post({"commit": sha})
        self.assertEqual(status, 200)
        analise = dados["analise_codigo"]
        self.assertEqual(analise["diff"]["indicios_codigo"]["candidatas"], ["feat"])
        self.assertIn("declaracao", [e["tipo"] for e in analise["comparacao"]["evidencias"]])
        self.assertFalse(sentinela.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), sha)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_classificacao_git_e_rotas_textuais_repassam_a_v12(self):
        sha = self.commit()
        titulo = "docs: atualizar guia"
        descricao = "Descrição de exemplo"
        entrada = {"titulo": titulo, "descricao": descricao}
        resultados = {
            "auto": {"categoria_sugerida": "docs", "modo": "com_prefixo", "margem_svm": 0.4},
            "com_prefixo": {"categoria_sugerida": "docs", "modo": "com_prefixo"},
            "sem_prefixo": {"categoria_sugerida": "test", "modo": "sem_prefixo"},
        }

        def classificar(_artefatos, _titulo, modo):
            return resultados[modo]

        with patch("commitx_site_git_v10.analisar_modelo", side_effect=classificar) as modelo:
            status_git, dados_git = self.post({"commit": sha})
            status_texto, dados_texto = self.post(entrada, "/api/classificar")
            status_comparar, comparacao = self.post(entrada, "/api/comparar")

        self.assertEqual((status_git, status_texto, status_comparar), (200, 200, 200))
        self.assertEqual(dados_git["analise"], dados_texto)
        self.assertEqual(dados_texto["classificacao"], resultados["auto"])
        self.assertEqual(comparacao, {modo: resultados[modo] for modo in ("com_prefixo", "sem_prefixo")})
        self.assertEqual([chamada.args for chamada in modelo.call_args_list], [
            (self.artefatos, titulo, modo) for modo in ("auto", "auto", "com_prefixo", "sem_prefixo")
        ])

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

    def commit_python(self, conteudo, nome="modulo.py"):
        (self.repo / nome).write_text(conteudo, encoding="utf-8")
        self.git("add", "--", nome)
        self.git("commit", "-qm", "feat: atualizar módulo")
        return self.git("rev-parse", "HEAD")

    def test_ast_desligada_por_padrao_e_com_false(self):
        sha = self.commit_python("def nova(): pass\n")
        with patch("commitx.versoes_git.ler_versoes_git") as leitor:
            status_antigo, antigo = self.post({"commit": sha})
            status_false, desligado = self.post({"commit": sha, "analise_estrutural": False})
        leitor.assert_not_called()
        self.assertEqual((status_antigo, status_false), (200, 200))
        self.assertEqual(desligado, antigo)
        self.assertEqual(set(antigo), {"git", "analise", "sinais", "analise_codigo"})

    def test_ast_ligada_acrescenta_evidencias_sem_mudar_os_campos_anteriores(self):
        pai = self.commit_python("def calcular(n):\n    if n > 0:\n        return n\n")
        (self.repo / "guia.txt").write_text("descrição", encoding="utf-8")
        self.git("add", "guia.txt")
        sha = self.commit_python("def calcular(n):\n    if n >= 0:\n        return n\n")
        v12 = {"categoria_sugerida": "feat", "modo": "com_prefixo"}
        with patch("commitx_site_git_v10.analisar_modelo", return_value=v12):
            _, antigo = self.post({"commit": sha})
            status, dados = self.post({"commit": sha[:8], "analise_estrutural": True,
                                      "repositorio": str(self.repo / "inexistente")})
        self.assertEqual(status, 200)
        ast = dados.pop("analise_estrutural")
        self.assertEqual(dados, antigo)
        self.assertEqual((ast["commit"], ast["comparado_com"], ast["cobertura"]),
                         (sha, pai, "completa"))
        self.assertEqual(ast["arquivos_ignorados"], [
            {"caminho": "guia.txt", "motivo": "extensao_nao_suportada"},
        ])
        self.assertEqual([e["tipo"] for e in ast["evidencias"]], ["condicao_modificada"])
        self.assertEqual(ast["evidencias"][0]["posterior"]["linha"], 2)
        self.assertNotIn("conteudo", json.dumps(ast))

    def test_ast_sem_arquivos_python(self):
        self.commit()
        status, dados = self.post({"analise_estrutural": True})
        self.assertEqual(status, 200)
        ast = dados["analise_estrutural"]
        self.assertEqual((ast["cobertura"], ast["arquivos"], ast["evidencias"]), ("completa", [], []))
        self.assertEqual([a["caminho"] for a in ast["arquivos_ignorados"]], ["README.md"])

    def test_ast_codigo_invalido(self):
        self.commit_python("def invalida(:\n")
        status, dados = self.post({"analise_estrutural": True})
        self.assertEqual(status, 200)
        ast = dados["analise_estrutural"]
        self.assertEqual(ast["cobertura"], "erro_sintaxe")
        self.assertEqual(ast["arquivos"][0]["limitacoes"][0]["motivo"], "erro_sintaxe")
        self.assertEqual(ast["evidencias"], [])

    def test_ast_arquivo_grande_propaga_limite_de_leitura(self):
        self.commit_python("# " + "x" * (256 * 1024) + "\n")
        status, dados = self.post({"analise_estrutural": True})
        self.assertEqual(status, 200)
        ast = dados["analise_estrutural"]
        self.assertEqual(ast["cobertura"], "parcial")
        self.assertIn("limite_bytes_arquivo", ast["limitacoes"])
        self.assertEqual(ast["arquivos"][0]["limitacoes"][0]["motivo"], "limite_bytes_arquivo")
        self.assertEqual(ast["evidencias"], [])

    def test_falha_ast_mantem_git_modelo_e_comparacao(self):
        sha = self.commit_python("def nova(): pass\n")
        v12 = {"categoria_sugerida": "feat"}
        with patch("commitx_site_git_v10.analisar_modelo", return_value=v12):
            _, antigo = self.post({})
            for funcao in ("commitx.analise_ast.analisar_ast", "commitx.versoes_git.ler_versoes_git"):
                with self.subTest(funcao=funcao), patch(funcao, side_effect=RuntimeError("detalhe interno")):
                    status, dados = self.post({"analise_estrutural": True})
                    self.assertEqual(status, 200)
                    ast = dados.pop("analise_estrutural")
                    self.assertEqual(dados, antigo)
                    self.assertEqual((ast["commit"], ast["cobertura"]), (sha, "indisponivel"))
                    self.assertEqual(ast["limitacoes"], ["falha_analise_estrutural"])
                    self.assertNotIn("detalhe interno", json.dumps(ast))

    def test_ast_funciona_sem_modelo_v12(self):
        self.commit_python("def nova(): pass\n")
        status, dados = self.post({"analise_estrutural": True})
        self.assertEqual(status, 200)
        self.assertIsNone(dados["analise"])
        self.assertEqual(dados["analise_codigo"]["comparacao"]["status"], "inconclusivo")
        self.assertEqual(dados["analise_estrutural"]["evidencias"][0]["tipo"], "funcao_adicionada")

    def test_ast_requer_booleano(self):
        self.commit()
        with patch("commitx_site_git_v10.analisar_commit") as git:
            for valor in (1, "true", None):
                with self.subTest(valor=valor):
                    status, dados = self.post({"analise_estrutural": valor})
                    self.assertEqual(status, 400)
                    self.assertIn("booleano", dados["erro"])
        git.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "Caminho Git com bytes não UTF-8 exige POSIX.")
    def test_ast_caminho_nao_utf8_preserva_resposta_json(self):
        nome = os.fsdecode(b"modulo-\xff.py")
        self.commit_python("def nova(): pass\n", nome)
        status, dados = self.post({"analise_estrutural": True})
        self.assertEqual(status, 200)
        ast = dados["analise_estrutural"]
        self.assertEqual(ast["arquivos"][0]["caminho"], nome)
        self.assertEqual(ast["evidencias"][0]["posterior"]["arquivo"], nome)
