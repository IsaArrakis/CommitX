"""Testes V4 sem exigir Ollama; verificam protocolo e cache."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from commitx.semantica_v4 import carregar_embeddings, executar


class TestSemanticaV4(unittest.TestCase):
    def test_cache_reutilizado_sem_chamada_http(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cache.json"
            texts = ["um titulo", "outro titulo", "um titulo"]
            with patch("commitx.semantica_v4._request_embeddings") as request:
                request.return_value = iter([[1., 0., 0., 0., 0., 0., 0., 0.],
                                             [0., 1., 0., 0., 0., 0., 0., 0.]])
                a = carregar_embeddings(texts, modelo="embeddinggemma", cache=path)
                self.assertEqual(request.call_count, 1)
            with patch("commitx.semantica_v4._request_embeddings") as request:
                b = carregar_embeddings(texts, modelo="embeddinggemma", cache=path)
                request.assert_not_called()
            self.assertEqual(a.shape, (3, 8))
            np.testing.assert_array_equal(a, b)
            self.assertEqual(len(json.loads(path.read_text())["vetores"]), 2)
            with self.assertRaises(ValueError):
                carregar_embeddings(texts, modelo="outro-modelo", cache=path)

    def test_tres_modelos_mesma_base_sem_sobrescrita(self):
        classes = ("fix", "feat", "docs", "refactor", "test")
        registros = [
            {
                "id": f"{r}-{cat}", "titulo": f"{cat} mudanca {r} modulo",
                "categoria": cat, "repositorios": (f"org/projeto-{r}",)
            }
            for r in range(12) for cat in classes
        ]
        vetores = np.asarray([
            [float(i % 5 == c) for c in range(5)] + [float(i // 5) / 100]
            for i in range(len(registros))
        ], dtype=np.float32)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "v4"
            r = executar(registros, vetores, out, folds=3)
            self.assertEqual(r["treino"], 60)
            self.assertEqual(set(r["modelos"]), {
                "svm_titulo", "svm_embeddings", "svm_hibrido"
            })
            with (out / "previsoes.csv").open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 180)
            for name in r["modelos"]:
                sub = [row for row in rows if row["modelo"] == name]
                self.assertEqual(len(set(row["id"] for row in sub)), 60)
            with self.assertRaises(FileExistsError):
                executar(registros, vetores, out, folds=3)


if __name__ == "__main__":
    unittest.main()
