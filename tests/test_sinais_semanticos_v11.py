"""Unit tests V11 semantic signals, kept independent of external evaluation."""
import tempfile
import unittest

import numpy as np
from commitx.sinais_semanticos_v11 import (
    PATTERNS, SinaisSemanticos, VARIANTES, executar, modelo,
)


class TestV11(unittest.TestCase):
    def test_sinais_separados(self):
        x = ["Update README documentation", "Rename and cleanup methods", "Fix race condition"]
        m = SinaisSemanticos().fit(x).transform(x).toarray()
        self.assertEqual(m.shape, (3, 2))
        self.assertEqual(m.tolist(), [[1., 0.], [0., 1.], [0., 0.]])

    def test_nao_confunde_docs_com_code(self):
        self.assertFalse(bool(PATTERNS["docs"].search("code refactoring")))
        self.assertTrue(bool(PATTERNS["refactor"].search("Migrate framework")))

    def test_pipelines_validos(self):
        weights = {"fix": 1., "feat": 1., "docs": 1.5, "refactor": 1.5, "test": 1.}
        for weight in VARIANTES.values():
            x = modelo(weights, weight)
            self.assertEqual(list(x.named_steps), ["tfidf", "model"])

    def test_protecao_saida(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileExistsError):
                executar([], {}, td)


if __name__ == "__main__":
    unittest.main()
