"""Testes do experimento V9 sem acesso ao teste externo."""
import csv
import tempfile
import unittest
from pathlib import Path

from commitx.experimento_prefixos_v9 import modelo, avaliar, NOMES


class TestExperimentoPrefixosV9(unittest.TestCase):
    def test_todos_modelos_sao_pipelines(self):
        for nome in NOMES:
            pipe = modelo(nome)
            self.assertEqual(list(pipe.named_steps), ["tfidf", "model"])

    def test_nomes_rejeitados(self):
        with self.assertRaises(ValueError):
            modelo("modelo_nao_existente")

    def test_nao_sobrescreve_resultados_existentes(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(FileExistsError):
                avaliar([], {}, pasta, 5)

    def test_fold_agrupado_com_titulos_fake(self):
        # Cada classe esta presente em diversos grupos independentes.
        categorias = ("fix", "feat", "docs", "refactor", "test")
        registros = []
        titulos = {}
        for i in range(8):
            for j, cat in enumerate(categorias):
                uid = f"{i}-{j}"
                titulo = f"{cat}: example {cat} change alpha {i}"
                registros.append({
                    "id": uid,
                    "titulo": f"example {cat} change alpha {i}",
                    "categoria": cat,
                    "repositorios": (f"repo-{i}",),
                })
                titulos[uid] = titulo
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "resultado"
            res = avaliar(registros, titulos, destino, n_folds=4)
            self.assertEqual(res["total_treino"], 40)
            self.assertEqual(set(res["metricas"]), set(NOMES))
            self.assertTrue((destino / "relatorio.md").exists())
            with (destino / "previsoes_oof.csv").open(
                    encoding="utf-8", newline="") as f:
                linhas = list(csv.DictReader(f))
            self.assertEqual(len(linhas), 40)


if __name__ == "__main__":
    unittest.main()
