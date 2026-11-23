"""Testes offline da fila inteligente, sem Ollama e sem rótulos artificiais."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.fila_inteligente import gerar
from commitx.rotulagem import ler_amostra


class TestFilaInteligente(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name)
        self.entrada = self.raiz / "commits.csv"
        self.banco = self.raiz / "humanos.sqlite3"
        self.saida = self.raiz / "fila.csv"
        self.resumo = self.raiz / "fila.json"
        self.linhas = []
        categorias = ("fix", "feat", "docs", "refactor", "test")
        for n in range(1, 151):
            categoria = categorias[(n - 1) % 5]
            p = "teste" if n % 12 == 0 else "validacao" if n % 8 == 0 else "treino"
            self.linhas.append({
                "id": str(n), "titulo": f"{categoria}: alterar componente {n}",
                "descricao": f"Detalhe sobre a tarefa {n}",
                "categoria": "", "grupo": f"repo{n}:sha{n}",
                "origem": "git" if n % 2 else "huggingface:commitpackft",
                "repositorio": f"repo{n // 4}",
                "particao": p, "tipo_declarado": categoria,
                "categoria_candidata": categoria,
            })
        self._salvar_entrada()
        with sqlite3.connect(self.banco) as con:
            con.execute(
                "CREATE TABLE avaliacoes "
                "(id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)"
            )
            con.execute("INSERT INTO avaliacoes VALUES ('1', 'fix', 'claro')")

    def _salvar_entrada(self):
        with self.entrada.open("w", newline="", encoding="utf-8") as arq:
            escritor = csv.DictWriter(arq, fieldnames=list(self.linhas[0]))
            escritor.writeheader()
            escritor.writerows(self.linhas)

    def _gerar(self, **kwargs):
        return gerar(
            self.entrada, self.banco, self.saida, self.resumo,
            quantidade=10, tamanho_pool=120, por_repo=2, **kwargs
        )

    def test_treino_nao_usa_teste_validacao_nem_humanos(self):
        resumo = self._gerar()
        with self.saida.open(encoding="utf-8", newline="") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertEqual(resumo["selecionados"], len(linhas))
        self.assertEqual(len(linhas), 10)
        self.assertNotIn("1", [r["id"] for r in linhas])
        self.assertTrue(all(r["particao"] == "treino" for r in linhas))
        self.assertTrue(all(r["categoria"] == "" for r in linhas))
        self.assertTrue(all(r["clareza"] == "" for r in linhas))
        self.assertFalse(resumo["modelo_categoria_usado"])
        self.assertEqual(len(ler_amostra(self.saida)), 10)

    def test_validacao_cega_nao_usa_modelo(self):
        resumo = self._gerar(particao="validacao")
        with self.saida.open(encoding="utf-8", newline="") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertFalse(resumo["modelo_categoria_usado"])
        self.assertTrue(all(r["particao"] == "validacao" for r in linhas))
        self.assertTrue(all(r["hipotese_categoria"] == "" for r in linhas))
        self.assertTrue(all(r["motivo_selecao"] == "validacao_aleatoria" for r in linhas))
        self.assertTrue(all(r["incerteza_estimativa"] == "" for r in linhas))

    def test_exclusao_e_nao_sobrescrita(self):
        exclusao = self.raiz / "exclusao.csv"
        with exclusao.open("w", newline="", encoding="utf-8") as arq:
            w = csv.DictWriter(arq, fieldnames=["id"])
            w.writeheader()
            w.writerows({"id": str(i)} for i in range(1, 100))
        r = self._gerar(excluir=[exclusao])
        with self.saida.open(encoding="utf-8", newline="") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertEqual(r["selecionados"], len(linhas))
        self.assertTrue(all(int(r["id"]) >= 100 for r in linhas))
        with self.assertRaises(FileExistsError):
            self._gerar(excluir=[exclusao])

    def test_detecta_repositorio_misto_entre_particoes(self):
        self.linhas[1]["repositorio"] = "repo-extra,repo-secreto"
        self.linhas[7]["repositorio"] = "repo-secreto,repo-outra"
        self._salvar_entrada()
        self._gerar()
        with self.saida.open(encoding="utf-8", newline="") as arq:
            selecionadas = list(csv.DictReader(arq))
        self.assertNotIn("2", {r["id"] for r in selecionadas})

    def test_nao_aceita_teste_e_recusa_saida_existente(self):
        with self.assertRaises(ValueError):
            self._gerar(particao="teste")
        self.assertFalse(self.saida.exists())
        self.assertFalse(self.resumo.exists())


if __name__ == "__main__":
    unittest.main()
