"""Testes offline da rotulagem automática, sem precisar instalar Ollama."""
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from commitx.rotulagem_ia import classificar, status, exportar, validar_resposta


class TestRotulagemIA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.entrada = self.raiz / "commits.csv"
        self.banco = self.raiz / "ia.sqlite3"
        self.humanos = self.raiz / "humanos.sqlite3"
        with self.entrada.open("w", newline="", encoding="utf-8") as arq:
            w = csv.DictWriter(arq, fieldnames=["id", "titulo", "descricao", "particao"])
            w.writeheader()
            w.writerows([
                {"id": "a", "titulo": "docs: guia", "descricao": "", "particao": "treino"},
                {"id": "b", "titulo": "feat: busca", "descricao": "", "particao": "validacao"},
                {"id": "c", "titulo": "fix: login", "descricao": "", "particao": "teste"},
                {"id": "d", "titulo": "fix: paginação", "descricao": "", "particao": "treino"},
                {"id": "e", "titulo": "test: criar testes", "descricao": "", "particao": "treino"},
            ])
        with sqlite3.connect(self.humanos) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY)")
            con.execute("INSERT INTO avaliacoes VALUES ('d')")
        self.chamadas = []
        def pred(titulo, descricao, modelo):
            self.chamadas.append(titulo)
            return ("docs", "parcial", "media", "hipótese")
        self.pred = pred

    def test_so_treino_nao_humanos_e_sem_contaminar(self):
        resumo = classificar(self.entrada, self.banco, self.humanos,
                             limite=0, preditor=self.pred,
                             imprimir=lambda *_: None)
        self.assertEqual(resumo["sugeridos"], 2)
        self.assertEqual(len(self.chamadas), 2)
        with sqlite3.connect(self.banco) as con:
            ids = {r[0] for r in con.execute("SELECT id FROM rotulos_ia")}
            self.assertEqual(ids, {"a", "e"})
            self.assertEqual(con.execute("SELECT categoria_ia FROM rotulos_ia WHERE id='a'").fetchone()[0], "docs")
        with sqlite3.connect(self.humanos) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM avaliacoes").fetchone()[0], 1)

    def test_retomada_e_limite(self):
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        self.assertEqual(len(self.chamadas), 2)
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        self.assertEqual(len(self.chamadas), 2)

    def test_exportacao_nao_sobrescreve(self):
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        destino = self.raiz / "s.csv"
        exportar(self.banco, destino)
        with destino.open(encoding="utf-8") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertEqual(linhas[0]["categoria_ia"], "docs")
        self.assertNotIn("categoria_humana", linhas[0])
        with self.assertRaises(FileExistsError):
            exportar(self.banco, destino)

    def test_falha_salva_erro_e_pode_retentar(self):
        def falha(*args):
            raise RuntimeError("Ollama indisponível")
        classificar(self.entrada, self.banco, self.humanos, limite=1,
                    preditor=falha, imprimir=lambda *_: None)
        self.assertEqual(status(self.banco)["status"]["erro"], 1)
        classificar(self.entrada, self.banco, self.humanos, limite=1,
                    retentar_erros=True, preditor=self.pred,
                    imprimir=lambda *_: None)
        self.assertEqual(status(self.banco)["status"]["prata"], 1)

    def test_rejeita_rotulos_invalidos(self):
        with self.assertRaises(ValueError):
            validar_resposta({"categoria":"inventado", "clareza":"vago", "confianca":"alta"})
        with self.assertRaises(ValueError):
            validar_resposta({"categoria":"fix", "clareza":"ótimo", "confianca":"alta"})

if __name__ == "__main__":
    unittest.main()
