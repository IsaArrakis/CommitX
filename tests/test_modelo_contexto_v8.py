"""Testes offline de features Git e separacao treino/validacao V8."""
import csv
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from commitx.modelo_contexto_v8 import (
    _carregar_rotulados, _construir, _matriz, analisar, contexto_arquivos, executar
)
from commitx.revisao_git_v5 import preparar


class TestModeloContextoV8(unittest.TestCase):
    def test_contexto_readme_e_java(self):
        docs = contexto_arquivos({"arquivos": "starter/README.adoc", "linhas_adicionadas": "3"})
        self.assertIn("apenasdocumentacao", docs)
        self.assertIn("extensao_adoc", docs)
        java = contexto_arquivos({"arquivos": "src/main/A.java | src/test/A_test.java",
                                   "linhas_adicionadas": "10"})
        self.assertIn("extensao_java", java)
        self.assertIn("comtestes", java)

    def test_sem_arquivos_nao_inventa_sinais(self):
        self.assertEqual(contexto_arquivos({"titulo": "docs: Update guide"}), "")

    def test_pipeline_aceita_titulo_e_arquivos(self):
        linhas = [
            {"titulo": "docs: update guide", "arquivos": "README.md"},
            {"titulo": "fix: resolve exception", "arquivos": "src/main/File.java"},
            {"titulo": "feat: add endpoint", "arquivos": "src/server/API.java"},
            {"titulo": "test: add assertions", "arquivos": "tests/test_api.py"},
            {"titulo": "refactor: split method", "arquivos": "src/core/engine.py"},
        ]
        x = _matriz(linhas)
        self.assertEqual(x.shape, (5, 2))
        model = _construir(com_arquivos=True)
        model.fit(x, ["docs", "fix", "feat", "test", "refactor"])
        self.assertEqual(len(model.predict(x)), 5)

    def test_isolamento_das_particoes_e_sem_sobrescrita(self):
        with TemporaryDirectory() as td:
            raiz = Path(td)
            repos = [raiz / f"repo{i}" for i in range(4)]
            rows = []
            for i, repo in enumerate(repos):
                rows.append({
                    "id": f"{i + 1:040x}", "titulo": f"Change sample {i}",
                    "repositorio": "git:" + str(repo), "particao": "nao_atribuida",
                    "arquivos": "README.md", "linhas_adicionadas": "1",
                    "linhas_removidas": "0",
                })
            entrada, plano, banco = raiz / "entrada.csv", raiz / "plano.json", raiz / "base.sqlite3"
            with entrada.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            dados = preparar(entrada=entrada, plano=plano, banco=banco)
            with sqlite3.connect(banco) as con:
                for r in rows:
                    particao = dados["repositorios"][r["repositorio"]]
                    if particao == "treino":
                        con.execute(
                            "INSERT INTO avaliacoes(id,categoria,clareza) VALUES(?,?,?)",
                            (r["id"], "docs", "claro"))
                    if particao == "validacao":
                        con.execute(
                            "INSERT INTO avaliacoes(id,categoria,clareza) VALUES(?,?,?)",
                            (r["id"], "docs", "claro"))
            # A base sintetica possui somente docs. O treinamento deve
            # recusar classes ausentes antes de criar arquivos de saida.
            with self.assertRaisesRegex(ValueError, "cinco categorias"):
                _carregar_rotulados(entrada, plano, banco)
            with self.assertRaisesRegex(ValueError, "cinco categorias"):
                executar(saida=raiz / "v8", entrada=entrada, plano=plano, banco=banco)
            self.assertFalse((raiz / "v8").exists())


if __name__ == "__main__":
    unittest.main()
