"""Testes do classificador real e das restricoes contra vazamento."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.classificador_real import (
    analisar_lote, carregar_modelo, prever, treinar,
)


class TestClassificadorReal(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.entrada = self.base / "commits.csv"
        self.banco = self.base / "labels.sqlite3"
        self.saida = self.base / "modelo"
        self.csv_saida = self.base / "predicoes.csv"
        classes = ("fix", "feat", "docs", "refactor", "test")
        linhas = []
        rotulos = []
        frases = {
            "fix": "Correct broken crash in runtime",
            "feat": "Add new feature to user interface",
            "docs": "Update installation guide documentation",
            "refactor": "Restructure internal helper code",
            "test": "Add unit tests for parser",
        }
        for categoria in classes:
            for i in range(6):
                uid = f"{categoria}-{i}"
                linhas.append({
                    "id": uid,
                    "titulo": f"{categoria}: {frases[categoria]} {i}",
                    "descricao": "corpo opcional",
                    "repositorio": f"org/{categoria}-{i}",
                    "particao": "treino",
                })
                rotulos.append((uid, categoria))
        linhas.extend([
            {"id": "validacao", "titulo": "feat: segredo validacao",
             "descricao": "nao treinar", "repositorio": "v", "particao": "validacao"},
            {"id": "teste", "titulo": "docs: segredo teste",
             "descricao": "nao treinar", "repositorio": "t", "particao": "teste"},
        ])
        rotulos.extend([("validacao", "feat"), ("teste", "docs")])
        with self.entrada.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)
        with sqlite3.connect(self.banco) as db:
            db.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT)")
            db.executemany("INSERT INTO avaliacoes VALUES (?, ?)", rotulos)

    def test_treina_so_treino_e_preserva_base(self):
        antes = self.banco.read_bytes()
        manifesto = treinar(entrada=self.entrada, banco=self.banco, saida=self.saida)
        self.assertEqual(manifesto["treino_registros"], 30)
        self.assertEqual(self.banco.read_bytes(), antes)
        self.assertTrue((self.saida / "modelo.joblib").is_file())
        self.assertTrue((self.saida / "manifesto.json").is_file())
        with self.assertRaises(FileExistsError):
            treinar(entrada=self.entrada, banco=self.banco, saida=self.saida)

    def test_predicao_nao_confunde_tipo_declarado_com_gabarito(self):
        treinar(entrada=self.entrada, banco=self.banco, saida=self.saida)
        modelo = carregar_modelo(self.saida)
        p = prever(modelo, "feat: Correct broken crash in runtime 0")
        self.assertEqual(p["tipo_declarado"], "feat")
        self.assertEqual(p["categoria_prevista"], "fix")
        self.assertTrue(p["divergencia_com_tipo_declarado"])
        self.assertTrue(p["revisar_manualmente"])
        self.assertIsInstance(p["margem_top2"], float)

    def test_lote_e_protecao_sobrescrita(self):
        treinar(entrada=self.entrada, banco=self.banco, saida=self.saida)
        modelo = carregar_modelo(self.saida)
        entrada = self.base / "novos.csv"
        entrada.write_text("id,titulo,descricao\nnovo,Add new feature to user interface,\n", encoding="utf-8")
        rel = analisar_lote(modelo, entrada, self.csv_saida)
        self.assertEqual(rel["quantidade"], 1)
        with self.csv_saida.open(encoding="utf-8") as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)
        with self.assertRaises(FileExistsError):
            analisar_lote(modelo, entrada, self.csv_saida)


if __name__ == "__main__":
    unittest.main()
