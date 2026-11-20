"""Testes de validacao dos modelos congelados, sem Ollama real."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from commitx.avaliacao_hibrido_validacao import ler_validacao, _metricas, avaliar


class TestValidacaoCongelada(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.csv = root / "preparados.csv"
        self.db = root / "rotulos.sqlite3"
        self.out = root / "resultado"
        linhas = [
            {"id": "1", "titulo": "fix: Correct crash", "repositorio": "abc/proj-a", "particao": "treino"},
            {"id": "2", "titulo": "docs: Add guide", "repositorio": "xyz/proj-b", "particao": "validacao"},
            {"id": "3", "titulo": "test: Add tests", "repositorio": "def/proj-c", "particao": "teste"},
        ]
        with self.csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(linhas[0]))
            writer.writeheader()
            writer.writerows(linhas)
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT)")
            con.executemany("INSERT INTO avaliacoes VALUES (?,?)",
                            [("1", "fix"), ("2", "docs"), ("3", "test")])

    def test_ler_validacao_nao_le_teste(self):
        rows = ler_validacao(self.csv, self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "2")
        self.assertEqual(rows[0]["real"], "docs")

    def test_bloquear_repositorio_repetido(self):
        texto = self.csv.read_text(encoding="utf-8").replace("xyz/proj-b", "abc/proj-a")
        self.csv.write_text(texto, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Vazamento"):
            ler_validacao(self.csv, self.db)

    def test_bloquear_titulo_repetido_sem_prefixo(self):
        texto = self.csv.read_text(encoding="utf-8").replace(
            "docs: Add guide", "docs: Correct crash")
        self.csv.write_text(texto, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Vazamento"):
            ler_validacao(self.csv, self.db)

    def test_metricas_com_intervalo(self):
        m = _metricas(["fix", "docs"], ["fix", "feat"])
        self.assertEqual(m["acertos"], 1)
        self.assertAlmostEqual(m["acuracia"], .5)
        self.assertEqual(len(m["intervalo_95_wilson_aproximado"]), 2)

    def test_avaliacao_pareada_nao_altera_banco(self):
        before = self.db.read_bytes()
        # Os hashes reais sao testados separadamente em implementacao; mock aqui
        # permite garantir que os resultados sao exatamente da validacao.
        with patch("commitx.avaliacao_hibrido_validacao._conferir_manifestos",
                   return_value={"csv_sha256": "a", "banco_sha256": "b"}), \
             patch("commitx.avaliacao_hibrido_validacao.carregar_hibrido",
                   return_value={"dummy": "h"}), \
             patch("commitx.avaliacao_hibrido_validacao.carregar_simples",
                   return_value={"dummy": "s"}), \
             patch("commitx.avaliacao_hibrido_validacao.prever_hibrido",
                   return_value=[{"categoria_prevista": "docs"}]) as pre_h, \
             patch("commitx.avaliacao_hibrido_validacao.prever_simples",
                   return_value={"categoria_prevista": "feat"}) as pre_s:
            result = avaliar(
                entrada=self.csv, banco=self.db, pasta_hibrido=self.out,
                pasta_simples=self.out, saida=self.out)
            self.assertEqual(result["validacao_quantidade"], 1)
            self.assertEqual(result["hibrido_v4"]["acertos"], 1)
            self.assertEqual(result["svm_titulo"]["acertos"], 0)
            self.assertEqual(pre_h.call_args.args[1], ["docs: Add guide"])
            self.assertEqual(pre_s.call_args.args[1], "docs: Add guide")
        self.assertEqual(self.db.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            avaliar(entrada=self.csv, banco=self.db, saida=self.out)

if __name__ == "__main__":
    unittest.main()
