"""Testes da criacao de base experimental sem tocar em teste reservado."""
import csv
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from commitx.fase2_base_local import construir


class TestFase2BaseLocal(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raiz = Path(temp.name)
        self.repo = self.raiz / "repo"
        self.repo.mkdir()
        def git(*args):
            return subprocess.run(
                ["git", "-C", str(self.repo), *args], check=True,
                capture_output=True, text=True,
            ).stdout.strip()
        git("init", "-q")
        git("config", "user.name", "Teste")
        git("config", "user.email", "teste@example.com")
        (self.repo / "demo.py").write_text("x = 1\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "feat: criar")
        (self.repo / "demo.py").write_text("x = 2\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "fix: alterar")
        self.sha = git("rev-parse", "HEAD")
        self.repo_id = "git:" + str(self.repo)
        self.uid = hashlib.sha256(
            (self.repo_id.casefold() + "\0" + self.sha.lower()).encode()
        ).hexdigest()
        self.entrada = self.raiz / "verificacao.csv"
        self.banco = self.raiz / "avaliacoes.sqlite3"
        self.saida = self.raiz / "base.csv"
        self.resumo = self.raiz / "resumo.json"
        with sqlite3.connect(self.banco) as con:
            con.execute(
                "CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)"
            )
            con.execute("INSERT INTO avaliacoes VALUES (?, ?, ?)", (self.uid, "fix", "claro"))

    def _csv(self, particao="treino", incluir_teste=False):
        with self.entrada.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "id", "repositorio", "sha_original", "particao",
                "fonte", "integridade_id", "verificacao_local", "situacao_origem",
            ])
            w.writeheader()
            w.writerow({
                "id": self.uid, "repositorio": self.repo_id,
                "sha_original": self.sha, "particao": particao,
                "fonte": "git:local", "integridade_id": "valido",
                "verificacao_local": "sha_verificado_local",
                "situacao_origem": "git_local_pendente_verificacao",
            })
            if incluir_teste:
                w.writerow({
                    "id": self.uid + "x", "repositorio": self.repo_id,
                    "sha_original": self.sha, "particao": "teste",
                    "fonte": "git:local", "integridade_id": "valido",
                    "verificacao_local": "sha_verificado_local",
                    "situacao_origem": "git_local_pendente_verificacao",
                })

    def test_treino_preserva_rotulo_sem_exportar_patch(self):
        self._csv(incluir_teste=True)
        r = construir(self.entrada, self.banco, self.saida, self.resumo)
        self.assertEqual(r["exportados"], 1)
        with self.saida.open(encoding="utf-8") as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row["categoria_humana"], "fix")
        self.assertEqual(row["clareza_humana"], "claro")
        self.assertEqual(row["diff_previa"], "")
        self.assertEqual(row["linhas_adicionadas"], "1")
        self.assertEqual(row["linhas_removidas"], "1")
        self.assertEqual(row["particao"], "treino")
        self.assertEqual(row["sha_original"], self.sha)

    def test_patch_opcional(self):
        self._csv()
        r = construir(self.entrada, self.banco, self.saida, self.resumo,
                      incluir_patch=True)
        self.assertTrue(r["patch_incluido"])
        with self.saida.open(encoding="utf-8") as f:
            row = next(csv.DictReader(f))
        self.assertIn("+x = 2", row["diff_previa"])

    def test_rejeita_teste_reservado(self):
        self._csv("teste")
        with self.assertRaises(ValueError):
            construir(self.entrada, self.banco, self.saida, self.resumo,
                      particoes=("teste",))

    def test_nao_sobrescreve_saida(self):
        self._csv()
        self.saida.write_text("preservar", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            construir(self.entrada, self.banco, self.saida, self.resumo)
        self.assertEqual(self.saida.read_text(), "preservar")

    def test_rejeita_id_incorreto(self):
        self._csv()
        conteudo = self.entrada.read_text()
        self.entrada.write_text(conteudo.replace(self.uid, "0" * 64))
        r = construir(self.entrada, self.banco, self.saida, self.resumo)
        self.assertEqual(r["exportados"], 0)


if __name__ == "__main__":
    unittest.main()
