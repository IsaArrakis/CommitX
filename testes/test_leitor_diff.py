"""Testes do leitor de diff usando um repositório Git temporário."""
import subprocess
import tempfile
from pathlib import Path
import unittest

from commitx.leitor_diff import analisar_commit


class TestLeitorDiff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)

        def git(*args):
            subprocess.run(["git", "-C", str(self.raiz), *args], check=True,
                           capture_output=True, text=True)

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
        self.assertEqual(resultado["titulo"], "fix: ajustar idade")
        self.assertEqual(resultado["quantidade_arquivos"], 1)
        self.assertEqual(resultado["linhas_adicionadas"], 1)
        self.assertEqual(resultado["linhas_removidas"], 1)
        self.assertIn("+idade = 20", resultado["diff_previa"])
        self.assertIn("-idade = 18", resultado["diff_previa"])

    def test_ler_primeiro_commit(self):
        resultado = analisar_commit(self.raiz, "HEAD~1")
        self.assertEqual(resultado["titulo"], "feat: adicionar idade")
        self.assertEqual(resultado["quantidade_arquivos"], 1)
        self.assertIn("+idade = 18", resultado["diff_previa"])

    def test_pode_truncar_previa(self):
        resultado = analisar_commit(self.raiz, max_chars=100)
        self.assertEqual(len(resultado["diff_previa"]), 100)
        self.assertTrue(resultado["diff_truncado"])

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
