"""Testes offline para coleta real de commits com hashes autenticos."""
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from commitx.coleta_git_real import _listar_repos, _ler_log, executar


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


class TestColetaGitReal(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.repos = self.raiz / "repos"
        self.repos.mkdir()
        self.repo = self.repos / "codigo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "coleta@example.com")
        git(self.repo, "config", "user.name", "Coleta")
        (self.repo / "README.md").write_text("# exemplo\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "docs: Add docs")
        (self.repo / "main.py").write_text("print('hello')\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "feat: Print greeting")
        self.out = self.raiz / "coleta"

    def test_reconhecer_raiz_git_e_ignorar_pasta_nao_git(self):
        (self.repos / "pasta_comum").mkdir()
        self.assertEqual(_listar_repos(self.repos), [self.repo])

    def test_sha40_e_campos_do_git(self):
        linhas = list(_ler_log(self.repo, por_repo=20))
        self.assertEqual(len(linhas), 2)
        self.assertTrue(all(len(r["id"]) == 40 for r in linhas))
        self.assertEqual({r["titulo"] for r in linhas},
                         {"docs: Add docs", "feat: Print greeting"})
        self.assertTrue(all(r["categoria_humana"] == "" for r in linhas))
        self.assertTrue(all(r["particao"] == "nao_atribuida" for r in linhas))
        self.assertTrue(any("README.md" in r["arquivos"] for r in linhas))
        self.assertEqual({r["prefixo_declarado"] for r in linhas}, {"docs", "feat"})

    def test_gerar_csv_sem_alterar_repositorio(self):
        antes = git(self.repo, "status", "--porcelain")
        rel = executar(raiz=self.repos, por_repo=20, saida=self.out)
        self.assertEqual(rel["total_commits_sha40"], 2)
        self.assertEqual(rel["repositorios_com_commits"], 1)
        self.assertTrue((self.out / "resumo.md").is_file())
        with (self.out / "commits_git_reais.csv").open(encoding="utf-8", newline="") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 2)
        self.assertEqual(git(self.repo, "status", "--porcelain"), antes)
        with self.assertRaises(FileExistsError):
            executar(raiz=self.repos, saida=self.out)

    def test_limites_e_pasta_inexistente(self):
        with self.assertRaises(ValueError):
            executar(raiz=self.repos, por_repo=0, saida=self.out)
        with self.assertRaises(ValueError):
            executar(raiz=self.raiz / "inexistente", saida=self.out)


if __name__ == "__main__":
    unittest.main()
