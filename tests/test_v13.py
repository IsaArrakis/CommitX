"""Regressões da V13 sem depender dos dados locais de treinamento."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from commitx.dados_v13 import _componentes
from commitx.experimento_v13 import metricas
from commitx.modelo_v13 import analisar_modelo, sugestao, texto_classificador
from commitx_site_git_v13 import LIMITE_ANALISE, LIMITE_PREVIA, analisar_git, listar_commits


class ModeloV13Test(unittest.TestCase):
    def test_normalizacao_e_escopo(self):
        titulo = "FEAT(API): Integração opcional em PORTUGUÊS"
        self.assertEqual(texto_classificador(titulo, "sem_prefixo"), "integracao opcional em portugues")
        self.assertEqual(texto_classificador(titulo, "com_prefixo"),
                         "feat(api): integracao opcional em portugues")
        resposta = analisar_modelo(Path("ausente"), "chore:Atualizar dependências")
        self.assertIsNone(resposta["categoria_sugerida"])
        self.assertIn("fora do escopo", resposta["motivo"])

    def test_abstencao_conta_na_acuracia_e_matriz(self):
        self.assertIsNone(sugestao("fix", None))
        self.assertIsNone(sugestao("fix", 0.149))
        self.assertEqual(sugestao("fix", 0.15), "fix")
        res = metricas(["feat", "feat"], ["feat", None])
        self.assertEqual((res["acuracia"], res["cobertura"], res["abstencoes"]), (0.5, 0.5, 1))
        self.assertEqual(res["acuracia_nas_sugestoes"], 1)
        self.assertEqual(res["matriz_confusao"][1][-1], 1)

    def test_link_transitivo_entre_original_traducao_e_repositorio(self):
        grupos = _componentes({
            "humano": {("repo", "org/projeto")},
            "original": {("repo", "org/projeto"), ("id", "orig")},
            "traducao": {("id", "orig"), ("titulo", "repetido")},
            "duplicata": {("titulo", "repetido")},
            "sintetico": {("titulo", "outro")},
        })
        self.assertEqual(len({grupos[r] for r in ("humano", "original", "traducao", "duplicata")}), 1)
        self.assertNotEqual(grupos["sintetico"], grupos["original"])


class GitV13Test(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.repo = Path(pasta.name).resolve()
        self.artefatos = self.repo / "sem-modelo"
        self.git("init", "-q")
        self.git("config", "user.name", "CommitX")
        self.git("config", "user.email", "commitx@example.test")
        self.git("config", "commit.gpgSign", "false")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, titulo):
        self.git("add", ".")
        self.git("commit", "-qm", titulo, "--allow-empty")

    def test_seletor_limite_e_ordem(self):
        self.assertEqual(listar_commits(self.repo), [])
        for i in range(31):
            self.commit(f"Alteração {i}")
        commits = listar_commits(self.repo)
        self.assertEqual(len(commits), 30)
        self.assertEqual(commits[0], {"sha": self.git("rev-parse", "HEAD"), "titulo": "Alteração 30"})
        self.assertEqual(commits[-1]["titulo"], "Alteração 1")

    def test_git_manual_exige_referencia(self):
        with self.assertRaisesRegex(ValueError, "Selecione um commit"):
            analisar_git({}, self.repo, self.artefatos)

    def test_evidencia_depois_da_previa_e_ast(self):
        (self.repo / "a.txt").write_text(("z" * 75 + "\n") * 110, encoding="utf-8")
        (self.repo / "z.py").write_text("def new_feature():\n    return True\n", encoding="utf-8")
        self.commit("feat: Add an example")
        res = analisar_git({"commit": "HEAD", "analise_estrutural": True}, self.repo, self.artefatos)
        self.assertEqual(len(res["git"]["diff_previa"]), LIMITE_PREVIA)
        self.assertNotIn("new_feature", res["git"]["diff_previa"])
        self.assertTrue(res["git"]["diff_truncado"])
        diff = res["analise_codigo"]["diff"]
        self.assertFalse(diff["diff_truncado"])
        self.assertEqual(diff["linhas_adicionadas"], diff["linhas_adicionadas_na_previa"])
        self.assertTrue(any(r["arquivo"] == "z.py" for r in diff["indicios_codigo"]["evidencias"]))
        self.assertTrue(res["analise_estrutural"]["evidencias"])

    def test_limite_de_analise_mantem_resultado_inconclusivo(self):
        (self.repo / "a.txt").write_text(("z" * 80 + "\n") * (LIMITE_ANALISE // 80), encoding="utf-8")
        self.commit("feat: Add a large example")
        res = analisar_git({"commit": "HEAD"}, self.repo, self.artefatos)
        self.assertTrue(res["analise_codigo"]["diff"]["diff_truncado"])
        self.assertEqual(res["analise_codigo"]["comparacao"]["status"], "inconclusivo")


if __name__ == "__main__":
    unittest.main()
