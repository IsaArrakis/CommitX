"""Testa a comparação com o contrato da V12 e a saída real do analisador."""

from copy import deepcopy
import unittest

from commitx.analise_diff import analisar_diff
from commitx.comparador_commit import comparar_commit


def diff_de_arquivos(arquivos):
    """Monta a saída do leitor para arquivos adicionados no mesmo commit."""
    metadados = []
    secoes = []
    for nome, conteudo in arquivos.items():
        linhas = conteudo.splitlines()
        metadados.append({"arquivo": nome, "adicionadas": len(linhas), "removidas": 0})
        secoes.extend([
            f"diff --git a/{nome} b/{nome}",
            "new file mode 100644",
            "--- /dev/null",
            f"+++ b/{nome}",
            f"@@ -0,0 +1,{len(linhas)} @@",
            *[f"+{linha}" for linha in linhas],
        ])
    return analisar_diff({
        "diff_truncado": False,
        "arquivos": metadados,
        "diff_previa": "\n".join(secoes) + "\n" if secoes else "",
        "linhas_adicionadas": sum(item["adicionadas"] for item in metadados),
        "linhas_removidas": 0,
    })


class TestComparadorCommit(unittest.TestCase):
    def comparar(self, categoria, diff):
        return comparar_commit({
            "categoria_sugerida": categoria,
            "tipo_declarado": "docs",
            "modo": "com_prefixo",
            "margem_svm": 0.6,
            "avisos": ["Aviso da V12."],
        }, diff)

    def test_docs_e_documentacao(self):
        resultado = self.comparar("docs", diff_de_arquivos({"README.md": "# Guia"}))
        self.assertEqual(resultado["status"], "compativel")
        self.assertEqual(resultado["categoria_textual"], "docs")
        self.assertEqual(resultado["categorias_codigo"], ["docs"])
        self.assertEqual(resultado["evidencias"][0]["arquivo"], "README.md")
        self.assertIn("Aviso da V12.", resultado["avisos"])

    def test_docs_e_codigo(self):
        resultado = self.comparar("docs", diff_de_arquivos({"modulo.py": "def somar(a, b):\n    return a + b"}))
        self.assertEqual(resultado["status"], "possivel_divergencia")
        self.assertEqual(resultado["categorias_codigo"], ["feat"])

    def test_test_e_arquivos_de_testes(self):
        resultado = self.comparar("test", diff_de_arquivos({"testes/test_modulo.py": "assert True"}))
        self.assertEqual(resultado["status"], "compativel")
        self.assertEqual(resultado["categorias_codigo"], ["test"])

    def test_fix_e_tratamento_de_erro(self):
        diff = analisar_diff({
            "diff_truncado": False,
            "arquivos": [{"arquivo": "modulo.py", "adicionadas": 5, "removidas": 1}],
            "linhas_adicionadas": 5,
            "linhas_removidas": 1,
            "diff_previa": (
                "diff --git a/modulo.py b/modulo.py\n"
                "--- a/modulo.py\n+++ b/modulo.py\n@@ -1 +1,5 @@\n"
                "-ler()\n+try:\n+    ler()\n+except ValueError:\n+    pass\n+\n"
            ),
        })
        resultado = self.comparar("fix", diff)
        self.assertEqual(resultado["status"], "compativel")
        self.assertEqual(resultado["evidencias"][0]["tipo"], "tratamento_excecao")

    def test_feat_e_funcionalidade_nova(self):
        resultado = self.comparar("feat", diff_de_arquivos({"modulo.py": "class Relatorio:\n    pass"}))
        self.assertEqual(resultado["status"], "compativel")
        self.assertEqual(resultado["categorias_codigo"], ["feat"])

    def test_refactor_e_alteracoes_ambiguas(self):
        codigo = diff_de_arquivos({"modulo.py": "def validar(x):\n    assert x > 0"})
        resultado = self.comparar("refactor", codigo)
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], ["feat", "fix"])

    def test_categorias_mistas(self):
        diff = diff_de_arquivos({"README.md": "# Guia", "modulo.py": "valor = 1"})
        resultado = self.comparar("docs", diff)
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], ["docs", "feat"])

    def test_mistura_com_arquivo_sem_indicios(self):
        diff = diff_de_arquivos({"README.md": "# Guia", "dados.csv": "valor"})
        resultado = self.comparar("docs", diff)
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], ["docs"])

    def test_ausencia_de_evidencias(self):
        resultado = self.comparar("docs", diff_de_arquivos({}))
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], [])
        self.assertEqual(resultado["evidencias"], [])

    def test_diff_truncado_com_indicios_de_documentacao(self):
        diff = diff_de_arquivos({"README.md": "# Guia"})
        diff["diff_truncado"] = True
        resultado = self.comparar("docs", diff)
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], ["docs"])
        self.assertTrue(any("truncada" in aviso for aviso in resultado["avisos"]))

    def test_indicios_de_codigo_com_previa_insuficiente(self):
        diff = diff_de_arquivos({"modulo.py": "valor = 1"})
        diff["indicios_codigo"]["previa_insuficiente"] = True
        resultado = self.comparar("feat", diff)
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], ["feat"])

    def test_leitura_parcial_com_indicios_de_testes(self):
        diff = diff_de_arquivos({"testes/test_modulo.py": "assert True"})
        diff["estado"] = "parcial"
        resultado = self.comparar("test", diff)
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertEqual(resultado["categorias_codigo"], ["test"])
        self.assertTrue(any("cobertura parcial" in aviso for aviso in resultado["avisos"]))

    def test_abstencao_da_v12_ignora_prefixo(self):
        resultado = self.comparar(None, diff_de_arquivos({"README.md": "# Guia"}))
        self.assertEqual(resultado["status"], "inconclusivo")
        self.assertIsNone(resultado["categoria_textual"])
        self.assertEqual(resultado["categorias_codigo"], ["docs"])

    def test_determinismo_e_preservacao_das_entradas(self):
        diff = diff_de_arquivos({"README.md": "# Guia"})
        v12 = {"categoria_sugerida": "docs", "margem_svm": 0.4, "avisos": ["Aviso."]}
        originais = deepcopy((v12, diff))
        resultado = comparar_commit(v12, diff)
        self.assertEqual(resultado, comparar_commit(v12, diff))
        resultado["evidencias"][0]["categorias"].clear()
        resultado["avisos"].clear()
        self.assertEqual((v12, diff), originais)
