"""Testes do experimento hibrido, sem tocar nas particoes reservadas."""
import csv
from pathlib import Path
import tempfile
import unittest

from commitx.experimento_hibrido import executar, _carregar


class TestExperimentoHibrido(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.entrada = self.root / "base.csv"
        self.saida = self.root / "saida"
        campos = [
            "id", "repositorio", "particao", "titulo", "descricao",
            "categoria_humana", "arquivos_alterados", "linhas_adicionadas",
            "linhas_removidas", "proveniencia_diff", "diff_truncado",
        ]
        self.dados = []
        classes = ["fix", "feat", "docs", "refactor", "test"]
        for repo in range(5):
            for j in range(5):
                self.dados.append({
                    "id": f"{repo}-{j}",
                    "repositorio": f"git:/tmp/repo{repo}",
                    "particao": "treino",
                    "titulo": f"{classes[j]}: alterar modulo {j} repo {repo}",
                    "descricao": "",
                    "categoria_humana": classes[j],
                    "arquivos_alterados": "src/demo.py;tests/test_demo.py",
                    "linhas_adicionadas": str(j + 1),
                    "linhas_removidas": str(j),
                    "proveniencia_diff": "git_local_sha_confirmado",
                    "diff_truncado": "nao",
                })
        self.dados.append({
            **self.dados[0],
            "id": "reservado",
            "particao": "teste",
            "titulo": "fix: segredo reservado",
        })
        with self.entrada.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(self.dados)

    def test_compara_somente_treino_em_cinco_repositorios(self):
        rel = executar(self.entrada, self.saida)
        self.assertEqual(rel["total_entrada_elegivel"], 25)
        self.assertEqual(rel["total_avaliado"], 25)
        self.assertEqual(rel["repositorios"], 5)
        self.assertTrue((self.saida / "previsoes.csv").is_file())
        with (self.saida / "previsoes.csv").open(encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 25)
        self.assertFalse(any(r["id"] == "reservado" for r in linhas))
        for nome in ("modelo_a", "modelo_b", "baseline"):
            self.assertIn("macro_f1", rel["metricas"][nome])

    def test_nao_sobrescreve(self):
        self.saida.mkdir()
        with self.assertRaises(FileExistsError):
            executar(self.entrada, self.saida)

    def test_recusa_menos_de_tres_repositorios(self):
        dados = _carregar(self.entrada)
        self.assertEqual(len(dados), 25)
        linhas = [r for r in self.dados if r["repositorio"] in
                  ("git:/tmp/repo0", "git:/tmp/repo1")]
        with self.entrada.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(self.dados[0]))
            w.writeheader()
            w.writerows(linhas)
        with self.assertRaisesRegex(ValueError, "tres repositorios"):
            executar(self.entrada, self.saida)


if __name__ == "__main__":
    unittest.main()
