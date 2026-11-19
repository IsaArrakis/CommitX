"""Testes offline do acompanhamento de marcos; sem dados de produção."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.plano_rotulagem import resumo


class TestPlanoRotulagem(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raiz = Path(temp.name)
        self.entrada = self.raiz / "commits.csv"
        self.banco = self.raiz / "humanos.sqlite3"
        campos = ["id", "titulo", "descricao", "repositorio", "particao"]
        with self.entrada.open("w", encoding="utf-8", newline="") as arq:
            w = csv.DictWriter(arq, fieldnames=campos)
            w.writeheader()
            for i, cat in enumerate(("fix", "feat", "docs", "refactor", "test"), 1):
                w.writerow({
                    "id": str(i), "titulo": f"{cat}: tarefa {i}",
                    "descricao": "detalhes", "repositorio": f"repo-{i}",
                    "particao": "treino",
                })
            w.writerow({
                "id": "6", "titulo": "Atualizar dependências",
                "descricao": "", "repositorio": "repo-val",
                "particao": "validacao",
            })
            w.writerow({
                "id": "7", "titulo": "teste final reservado",
                "descricao": "", "repositorio": "repo-teste",
                "particao": "teste",
            })
        with sqlite3.connect(self.banco) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)")
            for i, cat in enumerate(("fix", "feat", "docs", "refactor", "test"), 1):
                con.execute("INSERT INTO avaliacoes VALUES (?, ?, ?)", (str(i), cat, "claro"))
            con.execute("INSERT INTO avaliacoes VALUES ('6', 'fora_escopo', 'vago')")
            con.execute("INSERT INTO avaliacoes VALUES ('7', 'fix', 'parcial')")

    def test_metas_e_particoes(self):
        status = resumo(self.entrada, self.banco)
        self.assertEqual(status["total_rotulado"], 7)
        self.assertEqual(status["proximo_marco"], 150)
        self.assertEqual(status["faltam_ate_500"], 493)
        self.assertEqual(status["faltam_proximo_marco"], 143)
        self.assertEqual(status["revisoes_por_particao"], {
            "treino": 5, "validacao": 1, "teste": 1,
        })
        self.assertEqual(status["tarefas"]["categoria"]["treino"], 5)
        self.assertEqual(status["tarefas"]["categoria"]["validacao"], 0)
        self.assertEqual(status["tarefas"]["categoria"]["teste_reservado"], 1)
        self.assertEqual(status["tarefas"]["clareza"]["validacao"], 1)
        self.assertEqual(status["tarefas"]["categoria"]["situacao"], "bloqueada")
        self.assertFalse(status["repositorios_sobrepostos"])

    def test_nao_cria_arquivo_ou_modifica_banco(self):
        antes = self.banco.read_bytes()
        resumo(self.entrada, self.banco)
        self.assertEqual(self.banco.read_bytes(), antes)
        self.assertFalse((self.raiz / "relatorio.json").exists())

    def test_falha_repositorios_sobrepostos(self):
        linhas = list(csv.DictReader(self.entrada.open(encoding="utf-8")))
        linhas[5]["repositorio"] = "repo-1"
        with self.entrada.open("w", encoding="utf-8", newline="") as arq:
            w = csv.DictWriter(arq, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)
        status = resumo(self.entrada, self.banco)
        self.assertEqual(status["repositorios_sobrepostos"], ["repo-1"])
        self.assertEqual(status["tarefas"]["categoria"]["situacao"], "bloqueada")


if __name__ == "__main__":
    unittest.main()
