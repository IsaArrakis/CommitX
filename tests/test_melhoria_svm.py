"""Testes offline para a comparacao controlada dos modelos SVM."""
import csv
import tempfile
import unittest
from pathlib import Path

from commitx.melhoria_svm import comparar, modelo_palavras_caracteres


CLASSES = ("fix", "feat", "docs", "refactor", "test")


def exemplo(repo, classe):
    return {
        "id": f"{repo}-{classe}",
        "titulo": f"{classe} operation in module {repo}",
        "categoria": classe,
        "repositorios": (f"org/projeto-{repo}",),
    }


class TestMelhoriaSVM(unittest.TestCase):
    def test_svm_misto_aprende_exemplos(self):
        modelo = modelo_palavras_caracteres()
        x = [f"action {classe} sample" for classe in CLASSES]
        modelo.fit(x, list(CLASSES))
        self.assertEqual(len(modelo.predict(x)), len(CLASSES))

    def test_mesmos_folds_e_sem_sobrescrita(self):
        registros = [exemplo(repo, classe)
                     for repo in range(10) for classe in CLASSES]
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "saida"
            resumo = comparar(registros, destino, folds=3)
            self.assertEqual(resumo["quantidade_treino"], 50)
            self.assertEqual(resumo["grupos_independentes"], 10)
            self.assertEqual(set(resumo["modelos"]),
                             {"original", "palavras_caracteres"})
            with (destino / "previsoes_oof.csv").open(
                    encoding="utf-8", newline="") as f:
                linhas = list(csv.DictReader(f))
            self.assertEqual(len(linhas), 50)
            self.assertEqual(len({r["id"] for r in linhas}), 50)
            self.assertTrue(all(r["original"] in CLASSES for r in linhas))
            self.assertTrue(all(r["palavras_caracteres"] in CLASSES for r in linhas))
            self.assertTrue((destino / "casos_para_revisao.csv").exists())
            self.assertTrue((destino / "relatorio.md").exists())
            with self.assertRaises(FileExistsError):
                comparar(registros, destino, folds=3)

    def test_bloqueia_ids_duplicados(self):
        registros = [exemplo(repo, classe)
                     for repo in range(10) for classe in CLASSES]
        registros.append(registros[0])
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "saida"
            with self.assertRaisesRegex(ValueError, "duplicados"):
                comparar(registros, destino, folds=3)
            self.assertFalse(destino.exists())

    def test_bloqueia_repositorio_unico(self):
        registros = [exemplo(repo, classe)
                     for repo in range(10) for classe in CLASSES]
        for r in registros:
            r["repositorios"] = ("org/mesmo-projeto",)
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "saida"
            with self.assertRaisesRegex(ValueError, "Grupos independentes"):
                comparar(registros, destino, folds=3)
            self.assertFalse(destino.exists())


if __name__ == "__main__":
    unittest.main()
