"""Testes offline da auditoria V5: sem modificar repositorios, bancos e rotulos."""
import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

from commitx.auditoria_contexto_v5 import _nomes_locais, auditar_erro, executar


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class TestAuditoriaContextoV5(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.repos = self.raiz / "repos"
        self.repos.mkdir()
        self.repo = self.repos / "projeto"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.com")
        (self.repo / "README.md").write_text("Inicial\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-qm", "docs: Add guide")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.entrada = self.raiz / "erros.csv"
        self.saida = self.raiz / "saida"

    def linha(self, **overrides):
        data = {
            "id": self.sha, "titulo": "docs: Add guide",
            "real": "docs", "hibrido": "feat", "svm_titulo": "fix",
            "repositorio": "git:" + str(self.repo),
        }
        data.update(overrides)
        return data

    def test_confirma_sha_titulo_e_nomes_de_arquivos(self):
        item = auditar_erro(self.linha(), raiz=self.repos)
        self.assertEqual(item["situacao"], "git_local_verificado")
        self.assertIn("README.md", item["nomes_arquivos"])
        self.assertIn("todos_arquivos_documentacao", item["pistas_arquivos"])

    def test_nao_verifica_titulo_divergente(self):
        item = auditar_erro(self.linha(titulo="docs: Outro titulo"), raiz=self.repos)
        self.assertEqual(item["situacao"], "nao_verificado")
        self.assertIn("titulo_diverge", item["causa_nao_verificado"])

    def test_nao_aceita_caminho_fora_da_raiz_e_entradas_remotas(self):
        self.assertEqual(_nomes_locais("git:" + str(self.raiz), self.repos), [])
        item = auditar_erro(self.linha(repositorio="user/repo,other/repo"), raiz=self.repos)
        self.assertEqual(item["situacao"], "nao_verificado")
        self.assertEqual(item["causa_nao_verificado"], "sem_repositorio_git_local_acessivel")

    def test_gera_relatorio_sem_sobrescrever(self):
        before = git(self.repo, "status", "--porcelain")
        with self.entrada.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(self.linha()))
            w.writeheader()
            w.writerow(self.linha())
        r = executar(self.entrada, self.saida, self.repos)
        self.assertEqual(r["git_local_verificado"], 1)
        self.assertTrue((self.saida / "auditoria.csv").is_file())
        self.assertTrue((self.saida / "relatorio.md").is_file())
        with self.assertRaises(FileExistsError):
            executar(self.entrada, self.saida, self.repos)
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)


if __name__ == "__main__":
    unittest.main()
