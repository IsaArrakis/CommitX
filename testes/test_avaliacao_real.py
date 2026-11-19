"""Testes isolados da avaliação supervisionada, sem Ollama e sem dados reais."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.avaliacao_real import executar, validar_particoes


class TestAvaliacaoReal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.entrada = self.raiz / "commits.csv"
        self.banco = self.raiz / "humanos.sqlite3"
        self.saida = self.raiz / "relatorio"
        categorias = ("fix", "feat", "docs", "refactor", "test")
        clarezas = ("vago", "parcial", "claro")
        self.linhas = []
        self.rotulos = []
        numero = 0
        for indice, categoria in enumerate(categorias):
            for particao, quantidade in (("treino", 6), ("validacao", 3)):
                for j in range(quantidade):
                    numero += 1
                    uid = str(numero)
                    clareza = clarezas[(indice + j) % 3]
                    self.linhas.append({
                        "id": uid,
                        "titulo": f"{categoria}: realizar tarefa {numero} no modulo {indice}",
                        "descricao": f"Descricao especifica do caso {numero}",
                        "repositorio": f"projeto-{numero}",
                        "particao": particao,
                        "categoria_sugerida": "fix" if categoria != "fix" else "docs",
                        "clareza_sugerida": "vago",
                    })
                    self.rotulos.append((uid, categoria, clareza))
        # Partição de teste existe, mas não pode entrar no relatório de previsões.
        numero += 1
        self.linhas.append({
            "id": str(numero), "titulo": "fix: teste reservado",
            "descricao": "", "repositorio": "repo-teste",
            "particao": "teste", "categoria_sugerida": "docs",
            "clareza_sugerida": "claro",
        })
        self.rotulos.append((str(numero), "fix", "claro"))
        self._escrever()

    def _escrever(self):
        with self.entrada.open("w", encoding="utf-8", newline="") as arq:
            campos = list(self.linhas[0])
            escritor = csv.DictWriter(arq, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(self.linhas)
        with sqlite3.connect(self.banco) as con:
            con.execute(
                "CREATE TABLE avaliacoes "
                "(id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)"
            )
            con.executemany(
                "INSERT INTO avaliacoes VALUES (?, ?, ?)", self.rotulos
            )

    def test_status_somente_leitura(self):
        resumo = executar(
            self.entrada, self.banco, self.saida, apenas_status=True
        )
        self.assertFalse(self.saida.exists())
        self.assertEqual(resumo["tarefas"]["categoria"]["situacao"], "pronta")
        self.assertEqual(resumo["tarefas"]["clareza"]["situacao"], "pronta")

    def test_relatorios_duas_tarefas_e_teste_reservado(self):
        resumo = executar(self.entrada, self.banco, self.saida)
        for tarefa, numero_classes in (("categoria", 5), ("clareza", 3)):
            dados = resumo["tarefas"][tarefa]
            self.assertEqual(dados["situacao"], "avaliada")
            metricas = dados["metricas"]
            self.assertEqual(len(metricas["regressao_logistica"][
                "matriz_confusao"]), numero_classes)
            self.assertIn("baseline_maioria", metricas)
            with (self.saida / f"previsoes_{tarefa}.csv").open(
                encoding="utf-8", newline=""
            ) as arq:
                previsoes = list(csv.DictReader(arq))
            self.assertEqual(len(previsoes), 15)
            self.assertTrue(all(p["particao"] == "validacao" for p in previsoes))
            self.assertNotIn("46", {p["id"] for p in previsoes})
            self.assertTrue((self.saida / f"erros_{tarefa}.csv").is_file())
            self.assertTrue((self.saida / f"matriz_{tarefa}.csv").is_file())
        self.assertTrue((self.saida / "resumo.md").is_file())
        self.assertTrue((self.saida / "relatorio.json").is_file())
        with self.assertRaises(FileExistsError):
            executar(self.entrada, self.banco, self.saida)

    def test_falta_de_rotulos_impede_metricas_inventadas(self):
        with sqlite3.connect(self.banco) as con:
            con.execute("DELETE FROM avaliacoes WHERE categoria='test'")
        resumo = executar(self.entrada, self.banco, self.saida)
        self.assertEqual(
            resumo["tarefas"]["categoria"]["situacao"], "bloqueada"
        )
        self.assertNotIn("metricas", resumo["tarefas"]["categoria"])
        self.assertFalse((self.saida / "matriz_categoria.csv").exists())

    def test_sobreposicao_repositorios_impede_avaliacao(self):
        self.linhas[6]["repositorio"] = self.linhas[0]["repositorio"]
        self.entrada.unlink()
        with self.entrada.open("w", encoding="utf-8", newline="") as arq:
            w = csv.DictWriter(arq, fieldnames=list(self.linhas[0]))
            w.writeheader()
            w.writerows(self.linhas)
        resumo = executar(self.entrada, self.banco, self.saida)
        self.assertTrue(resumo["repositorios_sobrepostos"])
        self.assertEqual(
            resumo["tarefas"]["categoria"]["situacao"], "bloqueada"
        )
        self.assertEqual(
            resumo["tarefas"]["clareza"]["situacao"], "bloqueada"
        )

    def test_particao_invalida_gera_erro(self):
        registros = [{
            "id": "1", "repositorio": "repo",
            "particao": "desconhecida",
        }]
        with self.assertRaisesRegex(ValueError, "Partições inválidas"):
            validar_particoes(registros)


if __name__ == "__main__":
    unittest.main()
