"""Testes de treino com rótulos humanos sem utilizar previsões para supervisionar."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.treino_real import carregar_revisados, executar, treinar_tarefa


class TestTreinoReal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / "dados.csv"
        self.banco = self.root / "avaliacoes.sqlite3"
        self.destino = self.root / "modelos"
        with self.csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "id", "titulo", "descricao", "repositorio", "particao",
                "categoria_sugerida", "clareza_sugerida"
            ])
            w.writeheader()
            for i in range(1, 11):
                w.writerow({
                    "id": str(i), "titulo": f"fix: corrigir caso {i}",
                    "descricao": "", "repositorio": f"repo{i}",
                    "particao": "treino" if i <= 7 else "validacao",
                    "categoria_sugerida": "docs",
                    "clareza_sugerida": "claro",
                })
        with sqlite3.connect(self.banco) as conn:
            conn.execute(
                "CREATE TABLE avaliacoes "
                "(id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)"
            )
            conn.executemany("INSERT INTO avaliacoes VALUES (?, ?, ?)", [
                ("1", "fix", "vago"),
                ("2", "feat", "parcial"),
                ("3", "docs", "claro"),
                ("4", "refactor", "claro"),
                ("5", "test", "vago"),
            ])

    def test_ignora_previsoes_e_le_somente_humanos(self):
        registros = carregar_revisados(self.csv, self.banco)
        self.assertEqual(len(registros), 5)
        self.assertEqual(registros[0]["categoria"], "fix")
        self.assertEqual(registros[0]["clareza"], "vago")
        self.assertTrue(all(r["particao"] == "treino" for r in registros))

    def test_status_com_poucos_rotulos_nao_treina(self):
        resumo = executar(self.csv, self.banco, self.destino, apenas_status=True)
        self.assertEqual(resumo["rotulos_humanos_encontrados"], 5)
        self.assertTrue(resumo["tarefas"]["categoria"]["faltam_treino"])
        self.assertFalse(self.destino.exists())

    def test_treinamento_impedido_quando_dados_insuficientes(self):
        resumo = executar(self.csv, self.banco, self.destino)
        self.assertFalse(resumo["tarefas"]["categoria"]["modelo_treinado"])
        self.assertFalse(resumo["tarefas"]["clareza"]["modelo_treinado"])
        self.assertFalse((self.destino / "categoria.joblib").exists())
        self.assertTrue((self.destino / "relatorio_treinamento.json").is_file())

    def test_verificacao_modelo_nao_acessa_particao_teste(self):
        from commitx.treino_real import verificar
        amostras = [
            {"id": "1", "repositorio": "a", "particao": "treino",
             "texto": "um", "categoria": "fix", "clareza": "vago"},
            {"id": "2", "repositorio": "b", "particao": "validacao",
             "texto": "dois", "categoria": "fix", "clareza": "vago"},
            {"id": "3", "repositorio": "c", "particao": "teste",
             "texto": "tres", "categoria": "fix", "clareza": "vago"},
        ]
        v = verificar(amostras, "categoria", ("fix",))
        self.assertEqual(len(v["treino"]), 1)
        self.assertEqual(len(v["validacao"]), 1)
        self.assertEqual(len(v["teste"]), 1)
        self.assertFalse(v["sobreposicoes_repositorio"])


if __name__ == "__main__":
    unittest.main()
