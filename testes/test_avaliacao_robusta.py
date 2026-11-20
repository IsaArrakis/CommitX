"""Garantias de avaliacao cruzada por projetos, sem usar validacao/teste."""
import csv
from pathlib import Path
import tempfile
import unittest

from commitx.avaliacao_robusta import avaliar_registros, grupos_conectados


class TestAvaliacaoRobusta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.saida = self.root / "avaliacao"
        classes = ("fix", "feat", "docs", "refactor", "test")
        self.registros = []
        for repo in range(6):
            for classe in classes:
                self.registros.append({
                    "id": f"{repo}-{classe}",
                    "repositorio": f"organizacao/repo-{repo}",
                    "particao": "treino",
                    "texto": f"{classe} change useful distinct example for repo{repo}",
                    "categoria": classe,
                })
        self.registros.append({
            "id": "nao-pode-usar-validacao",
            "repositorio": "organizacao/validacao",
            "particao": "validacao",
            "texto": "texto reservado da validacao",
            "categoria": "fix",
        })
        self.registros.append({
            "id": "nao-pode-usar-teste",
            "repositorio": "organizacao/teste",
            "particao": "teste",
            "texto": "texto reservado de teste",
            "categoria": "feat",
        })

    def test_isola_particoes_e_avalia_os_mesmos_exemplos(self):
        rel = avaliar_registros(self.registros, self.saida, folds=3)
        self.assertEqual(rel["treino_elegivel"], 30)
        self.assertEqual(rel["grupos_independentes"], 6)
        self.assertEqual(len(rel["folds"]), 3)
        for nome in rel["modelos"]:
            arq = self.saida / f"previsoes_{nome}.csv"
            with arq.open(encoding="utf-8") as f:
                linhas = list(csv.DictReader(f))
            ids = {r["id"] for r in linhas}
            self.assertEqual(len(ids), 30)
            self.assertNotIn("nao-pode-usar-validacao", ids)
            self.assertNotIn("nao-pode-usar-teste", ids)
        self.assertEqual(len({
            r["id"] for r in csv.DictReader(
                (self.saida / "previsoes_svm_palavras.csv").open(encoding="utf-8")
            )
        }), 30)

    def test_multiplas_origens_conectadas_ficam_juntas(self):
        registros = [
            {"repositorio": "org/a,org/b"},
            {"repositorio": "org/b,org/c"},
            {"repositorio": "org/d"},
        ]
        grupos = grupos_conectados(registros)
        self.assertEqual(grupos[0], grupos[1])
        self.assertNotEqual(grupos[0], grupos[2])

    def test_saida_existente_e_preservada(self):
        self.saida.mkdir()
        with self.assertRaises(FileExistsError):
            avaliar_registros(self.registros, self.saida, folds=3)

    def test_repositorios_insuficientes_falham(self):
        menos = [r for r in self.registros if r["repositorio"] in {
            "organizacao/repo-0", "organizacao/repo-1",
        }]
        with self.assertRaisesRegex(ValueError, "insuficientes"):
            avaliar_registros(menos, self.saida, folds=3)


if __name__ == "__main__":
    unittest.main()
