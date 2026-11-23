"""Testes da associacao entre hash derivado e SHA original no SQLite."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.fase2_vinculos import gerar, _identificador


class TestFase2Vinculos(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.coleta = self.root / "coleta.sqlite3"
        self.rotulos = self.root / "rotulos.sqlite3"
        self.entrada = self.root / "dados.csv"
        self.saida = self.root / "vinculos.csv"
        self.resumo = self.root / "resumo.json"
        self.repo = "git:/tmp/exemplo"
        self.sha = "a" * 40
        self.id = hashlib.sha256((self.repo.casefold() + "\0" + self.sha).encode()).hexdigest()
        with sqlite3.connect(self.coleta) as con:
            con.execute(
                "CREATE TABLE commits (id TEXT PRIMARY KEY, repositorio TEXT, sha TEXT, fonte TEXT)"
            )
            con.execute("INSERT INTO commits VALUES (?, ?, ?, ?)",
                        (self.id, self.repo, self.sha, "git:local"))
        with sqlite3.connect(self.rotulos) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY)")
            con.execute("INSERT INTO avaliacoes VALUES (?)", (self.id,))
        with self.entrada.open("w", newline="", encoding="utf-8") as arq:
            w = csv.DictWriter(arq, fieldnames=["id", "titulo", "repositorio", "particao"])
            w.writeheader()
            w.writerow({"id": self.id, "titulo": "fix: testar", "repositorio": self.repo,
                        "particao": "treino"})

    def test_hash_corresponde_a_coleta(self):
        self.assertEqual(_identificador(self.repo, self.sha), self.id)

    def test_recupera_sha_sem_alterar_bancos(self):
        rel = gerar(self.entrada, self.coleta, self.rotulos, self.saida, self.resumo)
        self.assertEqual(rel["contagens"]["integridade_valido"], 1)
        with self.saida.open(encoding="utf-8") as arq:
            rows = list(csv.DictReader(arq))
        self.assertEqual(rows[0]["sha_original"], self.sha)
        self.assertEqual(rows[0]["situacao_origem"], "git_local_pendente_verificacao")
        self.assertEqual(json.loads(self.resumo.read_text())["rotulos_existentes"], 1)
        with sqlite3.connect(self.rotulos) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM avaliacoes").fetchone()[0], 1)

    def test_nao_sobrescreve_csv(self):
        self.saida.write_text("nao alterar")
        with self.assertRaises(FileExistsError):
            gerar(self.entrada, self.coleta, self.rotulos, self.saida, self.resumo)
        self.assertEqual(self.saida.read_text(), "nao alterar")

    def test_detecta_hash_divergente(self):
        with sqlite3.connect(self.coleta) as con:
            con.execute("UPDATE commits SET sha = ?", ("b" * 40,))
        rel = gerar(self.entrada, self.coleta, self.rotulos, self.saida, self.resumo)
        self.assertEqual(rel["contagens"]["situacao_hash_divergente"], 1)
        with self.saida.open(encoding="utf-8") as arq:
            row = next(csv.DictReader(arq))
        self.assertEqual(row["sha_original"], "")


if __name__ == "__main__":
    unittest.main()
