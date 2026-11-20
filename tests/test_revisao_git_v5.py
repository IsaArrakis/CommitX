"""Tests without network for V5 repository split and review persistence."""
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from commitx.revisao_git_v5 import preparar, revisar, status, _diff


def git(folder, *args):
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


class TestRevisaoGitV5(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.repos = self.root / "repos"
        self.repos.mkdir()
        self.csv = self.root / "coleta.csv"
        self.plano = self.root / "plano.json"
        self.banco = self.root / "rotulos.sqlite3"
        rows = []
        for n in range(4):
            repo = self.repos / f"repo{n}"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.name", "Tester")
            git(repo, "config", "user.email", "test@example.org")
            (repo / "README.md").write_text("README\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", f"docs: Add docs {n}")
            sha = git(repo, "rev-parse", "HEAD")
            rows.append({"id": sha, "titulo": f"docs: Add docs {n}",
                         "repositorio": "git:" + str(repo), "particao": "nao_atribuida"})
        with self.csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        self.rows = rows

    def test_preparar_isola_repositorios_e_reserva_teste(self):
        plano = preparar(entrada=self.csv, plano=self.plano, banco=self.banco)
        self.assertEqual(len(plano["repositorios"]), 4)
        self.assertEqual(plano["contagens"]["teste"], 1)
        self.assertEqual(plano["contagens"]["validacao"], 1)
        self.assertEqual(plano["contagens"]["treino"], 2)
        with self.assertRaises(FileExistsError):
            preparar(entrada=self.csv, plano=self.plano, banco=self.banco)

    def test_revisao_salva_e_retorna_status(self):
        plano = preparar(entrada=self.csv, plano=self.plano, banco=self.banco)
        entradas = iter(["1=3,3", "q"])
        salvos = revisar(entrada=self.csv, plano=self.plano, banco=self.banco,
                        tamanho=1, limite=2, input_fn=lambda prompt: next(entradas),
                        output_fn=lambda msg: None, raiz=self.repos)
        self.assertEqual(salvos, 1)
        dados = status(entrada=self.csv, plano=self.plano, banco=self.banco)
        self.assertEqual(dados["treino"], 1)
        self.assertEqual(dados["validacao"], 0)
        self.assertEqual(dados["teste_reservado"], 1)

    def test_diff_verifica_commit_local(self):
        r = self.rows[0]
        result = _diff(r, raiz=self.repos)
        self.assertEqual(result["commit"], r["id"])
        self.assertIn("README.md", [x["arquivo"] for x in result["arquivos"]])
        with self.assertRaises(ValueError):
            _diff(r, raiz=self.root / "outra")

    def test_testes_bloqueados_e_snapshot_protegido(self):
        preparar(entrada=self.csv, plano=self.plano, banco=self.banco)
        with self.assertRaises(ValueError):
            revisar(entrada=self.csv, plano=self.plano, banco=self.banco, particao="teste")
        self.csv.write_text(self.csv.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "mudou"):
            status(entrada=self.csv, plano=self.plano, banco=self.banco)


if __name__ == "__main__":
    unittest.main()
