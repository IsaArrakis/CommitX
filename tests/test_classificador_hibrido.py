"""Testes offline do classificador hibrido: nao exigem servidor Ollama."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from commitx.classificador_hibrido import (
    analisar_csv, carregar_modelo, prever, prever_lote, treinar, vetorizar,
)


class TestClassificadorHibrido(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / "prepared.csv"
        self.banco = self.root / "labels.sqlite3"
        self.destino = self.root / "modelo"
        classes = ("fix", "feat", "docs", "refactor", "test")
        messages = {
            "fix": "Correct broken authentication error",
            "feat": "Add export functionality to dashboard",
            "docs": "Update detailed developer documentation",
            "refactor": "Restructure internal helper functions",
            "test": "Add integration tests for parser",
        }
        linhas, rotulos = [], []
        for cls in classes:
            for i in range(6):
                uid = f"{cls}-{i}"
                linhas.append({
                    "id": uid, "titulo": f"{cls}: {messages[cls]} module {i}",
                    "descricao": "Text not used by classifier",
                    "repositorio": f"org/{cls}-{i}",
                    "particao": "treino",
                })
                rotulos.append((uid, cls))
        for particao in ("validacao", "teste"):
            linhas.append({
                "id": particao, "titulo": f"feat: secret {particao}",
                "descricao": "SECRET", "repositorio": particao, "particao": particao
            })
            rotulos.append((particao, "feat"))
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(linhas[0]))
            writer.writeheader()
            writer.writerows(linhas)
        with sqlite3.connect(self.banco) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT)")
            con.executemany("INSERT INTO avaliacoes VALUES (?,?)", rotulos)

    def fake_emb(self, texts, **kwargs):
        # Vetores deterministas distintos por classe; nunca enviam dados a rede.
        words = ("error", "dashboard", "documentation", "helper", "tests")
        data = np.array([[float(word in txt) for word in words] + [1., .1, .2]
                         for txt in texts], dtype=np.float32)
        return data / np.linalg.norm(data, axis=1, keepdims=True)

    def test_treino_somente_particao_treino_e_modelo_persistente(self):
        before = self.banco.read_bytes()
        with patch("commitx.classificador_hibrido.carregar_embeddings", side_effect=self.fake_emb):
            manifesto = treinar(entrada=self.csv, banco=self.banco, saida=self.destino)
        self.assertEqual(manifesto["registros_treino"], 30)
        self.assertEqual(before, self.banco.read_bytes())
        model = carregar_modelo(self.destino)
        self.assertEqual(model["dim_emb"], 8)
        self.assertEqual(len(model["svm"].classes_), 5)
        with self.assertRaises(FileExistsError):
            treinar(entrada=self.csv, banco=self.banco, saida=self.destino)

    def test_inferencia_por_titulo_e_lote(self):
        with patch("commitx.classificador_hibrido.carregar_embeddings", side_effect=self.fake_emb):
            treinar(entrada=self.csv, banco=self.banco, saida=self.destino)
            model = carregar_modelo(self.destino)
            p = prever(model, "docs: Update detailed developer documentation module 1")
            self.assertEqual(p["categoria_prevista"], "docs")
            self.assertEqual(p["tipo_declarado"], "docs")
            self.assertIsInstance(p["margem_top2"], float)
            out = self.root / "predicoes.csv"
            entrada = self.root / "novos.csv"
            entrada.write_text(
                "id,titulo\n1,fix: Correct broken authentication error module 2\n"
                "2,feat: Add export functionality to dashboard module 1\n",
                encoding="utf-8")
            resultado = analisar_csv(model, entrada, out)
            self.assertEqual(resultado["previsoes"], 2)
            with out.open(encoding="utf-8") as f:
                linhas = list(csv.DictReader(f))
            self.assertEqual(len(linhas), 2)
            with self.assertRaises(FileExistsError):
                analisar_csv(model, entrada, out)

    def test_emb_incompatível_nao_e_aceito(self):
        with patch("commitx.classificador_hibrido.carregar_embeddings", side_effect=self.fake_emb):
            treinar(entrada=self.csv, banco=self.banco, saida=self.destino)
        model = carregar_modelo(self.destino)
        with patch("commitx.classificador_hibrido.carregar_embeddings", return_value=np.ones((1, 9))):
            with self.assertRaises(ValueError):
                prever(model, "Add new feature")


if __name__ == "__main__":
    unittest.main()
