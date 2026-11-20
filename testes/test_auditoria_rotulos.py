"""Testa a fila de auditoria cega e a preservacao dos rotulos originais."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.auditoria_rotulos import preparar, conferir


class TestAuditoriaRotulos(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.preparados = self.root / "preparados.csv"
        self.previsoes = self.root / "previsoes.csv"
        self.original = self.root / "original.sqlite3"
        self.segunda = self.root / "segunda.sqlite3"
        self.fila = self.root / "fila.csv"
        self.resumo = self.root / "resumo.json"
        self.conf = self.root / "conferencia"
        rows = []
        labels = []
        predictions = []
        classes = ("fix", "feat", "docs", "refactor", "test")
        for n in range(5):
            for i in range(5):
                uid = f"{n}-{i}"
                classe = classes[n]
                rows.append({
                    "id": uid, "titulo": f"{classe}: Mudanca {uid}",
                    "descricao": "", "particao": "treino",
                    "grupo": uid, "origem": "git", "repositorio": f"repo{n}",
                })
                labels.append((uid, classe, "claro"))
                predictions.append({
                    "id": uid, "real": classe,
                    "previsto": "fix" if i < 3 and classe != "fix" else classe,
                })
        # Previsto fora do treino: deve ser recusado se entrar nas previsoes
        rows.append({
            "id": "validacao", "titulo": "fix: nao usar", "descricao": "",
            "particao": "validacao", "grupo": "validacao", "origem": "git",
            "repositorio": "repo-validacao",
        })
        labels.append(("validacao", "fix", "claro"))

        with self.preparados.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        with self.previsoes.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(predictions[0]))
            w.writeheader()
            w.writerows(predictions)
        for banco in (self.original, self.segunda):
            with sqlite3.connect(banco) as con:
                con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, "
                            "categoria TEXT, clareza TEXT)")
                con.executemany("INSERT INTO avaliacoes VALUES (?, ?, ?)", labels)

    def test_fila_sem_rotulo_e_sem_previsao(self):
        rel = preparar(self.preparados, self.previsoes, self.original,
                       self.fila, self.resumo, 10)
        self.assertEqual(rel["quantidade"], 10)
        with self.fila.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(r["particao"] == "treino" for r in rows))
        self.assertTrue(all("categoria" not in r and "previsto" not in r for r in rows))
        self.assertTrue(all(not r["titulo"].startswith("fix:") for r in rows))
        with self.assertRaises(FileExistsError):
            preparar(self.preparados, self.previsoes, self.original,
                     self.fila, self.resumo, 10)

    def test_conferencia_nao_escreve_no_banco_original(self):
        preparar(self.preparados, self.previsoes, self.original,
                 self.fila, self.resumo, 10)
        with self.fila.open(encoding="utf-8") as f:
            ids = [r["id"] for r in csv.DictReader(f)]
        with sqlite3.connect(self.segunda) as con:
            con.execute("UPDATE avaliacoes SET categoria='feat' WHERE id=?", (ids[0],))
        report = conferir(self.fila, self.original, self.segunda, self.conf)
        self.assertEqual(report["total_reavaliado"], 10)
        self.assertGreaterEqual(report["divergencias_categoria"], 1)
        with sqlite3.connect(self.original) as con:
            self.assertEqual(con.execute(
                "SELECT categoria FROM avaliacoes WHERE id=?", (ids[0],)
            ).fetchone()[0], next(
                c for uid, c in con.execute("SELECT id, categoria FROM avaliacoes")
                if uid == ids[0]
            ))

    def test_impede_inclusao_reservada(self):
        with self.previsoes.open("a", encoding="utf-8") as f:
            f.write("validacao,fix,fix\n")
        with self.assertRaisesRegex(ValueError, "particao reservada"):
            preparar(self.preparados, self.previsoes, self.original,
                     self.fila, self.resumo, 10)


if __name__ == "__main__":
    unittest.main()
