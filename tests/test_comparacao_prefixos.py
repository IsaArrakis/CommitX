"""Testes da comparacao controlada de prefixos do CommitX."""
import csv
import tempfile
import unittest
from pathlib import Path

from commitx.comparacao_prefixos import prefixo, raw_titles, comparar


class TestPrefixos(unittest.TestCase):
    def test_identifica_apenas_cabecalhos_validos(self):
        self.assertEqual(prefixo("docs: Switch RFC links"), "docs")
        self.assertEqual(prefixo("refactor(verification): Improve query"), "refactor")
        self.assertEqual(prefixo("FIX!: Repair issue"), "fix")
        self.assertEqual(prefixo("Fix error"), "")
        self.assertEqual(prefixo("unknown: Something"), "")
        self.assertEqual(prefixo("docs: "), "")

    def test_titulos_apenas_treino(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dados.csv"
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["id", "titulo", "particao"])
                writer.writeheader()
                writer.writerow({"id": "a", "titulo": "docs: A", "particao": "treino"})
                writer.writerow({"id": "b", "titulo": "secret", "particao": "validacao"})
            self.assertEqual(raw_titles(path, {"a"}), {"a": "docs: A"})
            with self.assertRaises(ValueError):
                raw_titles(path, {"b"})

    def test_nao_sobrescreve_pasta(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileExistsError):
                comparar([], {}, td)


if __name__ == "__main__":
    unittest.main()
