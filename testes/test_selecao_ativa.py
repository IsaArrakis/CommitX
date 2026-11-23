"""Testes offline para seleção com diversidade e isolamento de partições."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.selecao_ativa import selecionar


class TestSelecaoAtiva(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        self.csv = raiz / "triagem.csv"
        self.out = raiz / "selecionados.csv"
        self.report = raiz / "relatorio.json"
        self.banco = raiz / "humanos.sqlite3"
        with sqlite3.connect(self.banco) as conn:
            conn.execute(
                "CREATE TABLE avaliacoes "
                "(id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)"
            )
            conn.execute(
                "INSERT INTO avaliacoes VALUES ('1', 'fix', 'claro')"
            )
        with self.csv.open("w", newline="", encoding="utf-8") as arq:
            campos = [
                "id", "titulo", "descricao", "grupo", "origem", "repositorio",
                "particao", "categoria_sugerida", "prioridade_revisao", "status"
            ]
            writer = csv.DictWriter(arq, fieldnames=campos)
            writer.writeheader()
            for i in range(1, 61):
                writer.writerow({
                    "id": str(i), "titulo": f"fix: corrigir erro {i}",
                    "descricao": "", "grupo": f"r{i//5}:{i}",
                    "origem": "git:local" if i % 2 else "huggingface:commitpackft",
                    "repositorio": f"repo{i//5}",
                    "particao": "teste" if i % 10 == 0 else "treino",
                    "categoria_sugerida": ("fix", "feat", "docs", "test", "refactor")[i%5],
                    "prioridade_revisao": "alta" if i % 3 == 0 else "normal",
                    "status": "pendente_revisao",
                })

    def test_exclui_humanos_teste_e_respeita_repo(self):
        r = selecionar(self.csv, self.out, self.report, self.banco,
                      quantidade=20, por_repo=3)
        self.assertEqual(r["selecionados"], 20)
        with self.out.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(set(row["id"] for row in rows)), 20)
        self.assertNotIn("1", {row["id"] for row in rows})
        self.assertTrue(all(row["particao"] == "treino" for row in rows))
        self.assertTrue(all(row["categoria"] == "" for row in rows))
        from collections import Counter
        contagem = Counter(row["repositorio"] for row in rows)
        self.assertLessEqual(max(contagem.values()), 3)

    def test_nao_sobrescreve_e_e_deterministico(self):
        selecionar(self.csv, self.out, self.report, self.banco, quantidade=10)
        with self.out.open(encoding="utf-8") as f:
            first = f.read()
        with self.assertRaises(FileExistsError):
            selecionar(self.csv, self.out, self.report, self.banco, quantidade=10)
        other_csv = self.out.with_name("outra.csv")
        other_report = self.report.with_name("outro.json")
        selecionar(self.csv, other_csv, other_report, self.banco, quantidade=10)
        self.assertEqual(first, other_csv.read_text(encoding="utf-8"))

    def test_nao_converte_previsao_em_rotulo_humano(self):
        selecionar(self.csv, self.out, self.report, self.banco, quantidade=8)
        with self.out.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertTrue(any(row["categoria_candidata"] for row in rows))
        self.assertTrue(all(not row["categoria"] for row in rows))


if __name__ == "__main__":
    unittest.main()
