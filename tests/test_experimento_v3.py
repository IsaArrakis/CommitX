"""Testes do experimento V3, incluindo protecao do conjunto de teste."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.experimento_v3 import avaliar, carregar_treino, componentes


class TestExperimentoV3(unittest.TestCase):
    def test_carrega_somente_particao_treino(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entrada, banco = base / "base.csv", base / "labels.sqlite3"
            with entrada.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "id", "titulo", "descricao", "repositorio", "particao"
                ])
                w.writeheader()
                w.writerows([
                    {"id": "a", "titulo": "fix: Corrigir erro", "descricao": "teste",
                     "repositorio": "org/r1", "particao": "treino"},
                    {"id": "b", "titulo": "feat: Segredo", "descricao": "nao consultar",
                     "repositorio": "org/r2", "particao": "teste"},
                    {"id": "c", "titulo": "docs: Segredo", "descricao": "nao consultar",
                     "repositorio": "org/r3", "particao": "validacao"},
                ])
            with sqlite3.connect(banco) as con:
                con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT)")
                con.executemany("INSERT INTO avaliacoes VALUES (?, ?)", [
                    ("a", "fix"), ("b", "feat"), ("c", "docs")
                ])
            registros = carregar_treino(entrada, banco)
            self.assertEqual([r["id"] for r in registros], ["a"])
            self.assertEqual(registros[0]["titulo"], "Corrigir erro")

    def test_grupos_conectam_repositorios_e_titulos(self):
        rows = [
            {"repositorios": ("org/a", "org/b"), "titulo": "a"},
            {"repositorios": ("org/b",), "titulo": "b"},
            {"repositorios": ("org/c",), "titulo": "a"},
            {"repositorios": ("org/d",), "titulo": "c"},
        ]
        grupos = componentes(rows)
        self.assertEqual(grupos[0], grupos[1])
        self.assertEqual(grupos[0], grupos[2])
        self.assertNotEqual(grupos[0], grupos[3])

    def test_nested_cv_sem_vazamento_e_sem_sobrescrever(self):
        classes = ("fix", "feat", "docs", "refactor", "test")
        rows = [
            {"id": f"{r}-{c}", "titulo": f"{c} tarefa modulo {r}",
             "texto_completo": f"{c} tarefa modulo {r} texto {r}",
             "categoria": c, "repositorios": (f"org/repo-{r}",)}
            for r in range(10) for c in classes
        ]
        with tempfile.TemporaryDirectory() as tmp:
            saida = Path(tmp) / "resultado"
            rel = avaliar(rows, saida, externos=3, internos=2)
            self.assertEqual(rel["quantidade_treino"], 50)
            self.assertEqual(len(rel["selecoes"]), 3)
            with (saida / "previsoes_oof.csv").open(encoding="utf-8") as f:
                prev = list(csv.DictReader(f))
            for nome in rel["metricas"]:
                ids = [x["id"] for x in prev if x["modelo"] == nome]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(len(ids), 50)
            with self.assertRaises(FileExistsError):
                avaliar(rows, saida, externos=3, internos=2)


if __name__ == "__main__":
    unittest.main()
