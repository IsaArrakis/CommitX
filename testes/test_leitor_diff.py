"""Testes do leitor de diff usando um repositório Git temporário."""
import os
import subprocess
import sys
import tracemalloc
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from commitx.leitor_diff import _previa_patch, analisar_commit


class TestLeitorDiff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)

        config = patch.dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        config.start()
        self.addCleanup(config.stop)

        def git(*args):
            return subprocess.run(["git", "-C", str(self.raiz), *args], check=True,
                           capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

        self.git = git
        git("init", "-q")
        git("config", "user.name", "Teste CommitX")
        git("config", "user.email", "teste@example.com")
        (self.raiz / "exemplo.py").write_text("idade = 18\n", encoding="utf-8")
        git("add", "exemplo.py")
        git("commit", "-qm", "feat: adicionar idade")
        (self.raiz / "exemplo.py").write_text("idade = 20\n", encoding="utf-8")
        git("add", "exemplo.py")
        git("commit", "-qm", "fix: ajustar idade")

    def test_ler_commit_mais_recente(self):
        resultado = analisar_commit(self.raiz)
        self.assertEqual(resultado["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(resultado["comparado_com"], self.git("rev-parse", "HEAD^").strip())
        self.assertFalse(resultado["merge"])
        self.assertFalse(resultado["diff_truncado"])
        self.assertEqual(resultado["titulo"], "fix: ajustar idade")
        self.assertEqual(resultado["quantidade_arquivos"], 1)
        self.assertEqual(resultado["linhas_adicionadas"], 1)
        self.assertEqual(resultado["linhas_removidas"], 1)
        self.assertIn("+idade = 20", resultado["diff_previa"])
        self.assertIn("-idade = 18", resultado["diff_previa"])

    def test_ler_primeiro_commit(self):
        resultado = analisar_commit(self.raiz, "HEAD~1")
        self.assertIsNone(resultado["comparado_com"])
        self.assertFalse(resultado["merge"])
        self.assertEqual(resultado["titulo"], "feat: adicionar idade")
        self.assertEqual(resultado["quantidade_arquivos"], 1)
        self.assertIn("+idade = 18", resultado["diff_previa"])

    def test_pode_truncar_previa(self):
        resultado = analisar_commit(self.raiz, max_chars=100)
        self.assertEqual(len(resultado["diff_previa"]), 100)
        self.assertTrue(resultado["diff_truncado"])

    def test_merge_compara_com_primeiro_pai(self):
        self.git("switch", "-qc", "experimento", "HEAD~1")
        (self.raiz / "ramo.txt").write_text("novo ramo\n", encoding="utf-8")
        self.git("add", "ramo.txt")
        self.git("commit", "-qm", "feat: criar arquivo no ramo")
        self.git("switch", "-q", "-")
        self.git("merge", "--no-ff", "-qm", "merge: integrar experimento", "experimento")
        resultado = analisar_commit(self.raiz)
        self.assertTrue(resultado["merge"])
        self.assertEqual(resultado["comparado_com"], self.git("rev-parse", "HEAD^1").strip())
        self.assertEqual(resultado["quantidade_arquivos"], 1)
        self.assertIn("ramo.txt", resultado["diff_previa"])

    def test_caminhos_literais_e_binario_no_commit_raiz(self):
        self.git("switch", "--orphan", "raiz")
        nomes = ["com espaço", "ação", "tab\ta", "linha\nb", "cr\r\nc"]
        for nome in nomes:
            (self.raiz / nome).write_bytes(b"linha\n")
        (self.raiz / "imagem.bin").write_bytes(b"\x00\xff")
        self.git("add", "--all")
        self.git("commit", "-qm", "Título", "-m", "Descrição")
        resultado = analisar_commit(self.raiz)
        self.assertEqual((resultado["titulo"], resultado["descricao"]), ("Título", "Descrição"))
        registros = {a["arquivo"]: (a["adicionadas"], a["removidas"]) for a in resultado["arquivos"]}
        self.assertEqual(registros, {**dict.fromkeys(nomes, (1, 0)), "imagem.bin": (None, None)})
        self.assertEqual(resultado["quantidade_arquivos"], len(nomes) + 1)
        self.assertEqual((resultado["linhas_adicionadas"], resultado["linhas_removidas"]), (5, 0))

    def test_renome_preserva_remocao_e_adicao(self):
        nome = "novo\tç\n.py"
        self.git("mv", "--", "exemplo.py", nome)
        self.git("commit", "-qm", "Renomear")
        resultado = analisar_commit(self.raiz)
        self.assertCountEqual(resultado["arquivos"], [
            {"arquivo": "exemplo.py", "adicionadas": 0, "removidas": 1},
            {"arquivo": nome, "adicionadas": 1, "removidas": 0},
        ])

    def test_limite_em_caracteres_e_tamanho_exato(self):
        # Força sequências UTF-8 a atravessarem os blocos de leitura do pipe.
        (self.raiz / "texto").write_bytes(("é🦉ç" * 6000 + "\r\nfim\n").encode())
        self.git("add", "texto")
        self.git("commit", "-qm", "Unicode")
        completo = self.git("diff", "--no-color", "--no-renames", "HEAD^", "HEAD", "--")
        inicio = completo.index("é🦉ç")
        for limite in (inicio + 2, 8193, len(completo) - 1, len(completo), len(completo) + 1):
            with self.subTest(limite=limite):
                resultado = analisar_commit(self.raiz, max_chars=limite)
                self.assertEqual(resultado["diff_previa"], completo[:limite])
                self.assertEqual(resultado["diff_truncado"], limite < len(completo))

    def test_patch_grande_com_captura_limitada(self):
        with (self.raiz / "grande").open("wb") as arquivo:
            arquivo.write(b"x" * 4_000_000 + b"\n")
        self.git("add", "grande")
        self.git("commit", "-qm", "Uma linha longa")
        tracemalloc.start()
        try:
            resultado = analisar_commit(self.raiz, max_chars=100)
            _, pico = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertTrue(resultado["diff_truncado"])
        self.assertEqual(len(resultado["diff_previa"]), 100)
        self.assertEqual(resultado["linhas_adicionadas"], 1)
        self.assertLess(pico, 1_000_000)  # Memória Python, exclui o processo Git.

    def test_analise_preserva_objetos_indice_e_arvore_de_trabalho(self):
        arquivo = self.raiz / "exemplo.py"
        arquivo.write_bytes(b"no indice\n")
        self.git("add", "exemplo.py")
        arquivo.write_bytes(b"pendente\n")
        (self.raiz / "nao rastreado").write_bytes(b"local")

        def conteudos():
            return {p.relative_to(self.raiz): p.read_bytes()
                    for p in self.raiz.rglob("*") if p.is_file()}

        antes = conteudos()
        analisar_commit(self.raiz, max_chars=100)
        self.assertEqual(conteudos(), antes)

    def test_referencia_inexistente(self):
        with self.assertRaisesRegex(ValueError, "Git não conseguiu"):
            analisar_commit(self.raiz, "referencia-inexistente")

    def test_git_indisponivel(self):
        with patch.dict(os.environ, PATH=str(self.raiz)):
            with self.assertRaisesRegex(ValueError, "Git não encontrado"):
                analisar_commit(self.raiz)

    def simular_git_do_patch(self, programa):
        iniciar = subprocess.Popen

        def iniciar_simulado(args, **opcoes):
            self.processo_patch = iniciar([sys.executable, "-c", programa], **opcoes)
            return self.processo_patch

        return patch("commitx.leitor_diff.subprocess.Popen", side_effect=iniciar_simulado)

    def test_timeout_do_patch_encerra_processo(self):
        with self.simular_git_do_patch("import time; time.sleep(30)"):
            with patch("commitx.leitor_diff._TIMEOUT_GIT", 0.1):
                with self.assertRaisesRegex(ValueError, "Consulta Git demorou"):
                    _previa_patch(self.raiz, "show", "HEAD", max_chars=100)
        self.assertIsNotNone(self.processo_patch.returncode)
        self.assertNotEqual(self.processo_patch.returncode, 0)

    def test_erro_do_patch_apos_truncamento(self):
        programa = ("import sys\n"
                    "sys.stdout.write('x' * 200000)\n"
                    "sys.stderr.write('falha controlada' + '!' * 200000)\n"
                    "sys.exit(1)")
        with self.simular_git_do_patch(programa):
            with self.assertRaisesRegex(ValueError, "falha controlada") as erro:
                _previa_patch(self.raiz, "diff", max_chars=100)
        self.assertLess(len(str(erro.exception)), 4200)

    def test_rejeita_opcao_como_referencia(self):
        with self.assertRaisesRegex(ValueError, "commit válido"):
            analisar_commit(self.raiz, "--help")

    def test_rejeita_pasta_nao_git(self):
        pasta = self.raiz / "nao-e-git"
        pasta.mkdir()
        # A pasta interna deve ser rejeitada, mesmo dentro de um repo.
        with self.assertRaises(ValueError):
            analisar_commit(pasta)


if __name__ == "__main__":
    unittest.main()
