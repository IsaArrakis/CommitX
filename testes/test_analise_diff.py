"""Testa a extração com diffs Git locais e casos de formato controlado."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from commitx.analise_diff import analisar_diff
from commitx.leitor_diff import analisar_commit


class TestAnaliseDiff(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        configuracao = patch.dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        configuracao.start()
        self.addCleanup(configuracao.stop)
        self.git("init", "-q")
        self.git("config", "user.name", "Teste CommitX")
        self.git("config", "user.email", "teste@example.com")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "diff.noprefix", "false")
        self.git("config", "diff.mnemonicPrefix", "false")

    def git(self, *args):
        subprocess.run(
            ["git", "-C", str(self.raiz), *args], check=True, capture_output=True,
        )

    def gravar(self, arquivo, conteudo):
        caminho = self.raiz / arquivo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(conteudo, bytes):
            caminho.write_bytes(conteudo)
        else:
            caminho.write_text(conteudo, encoding="utf-8")

    def commit(self, mensagem="Exemplo"):
        self.git("add", "--all")
        self.git("commit", "-qm", mensagem, "--allow-empty")

    def extrair(self, **opcoes):
        return analisar_diff(analisar_commit(self.raiz, **opcoes))

    def test_diff_vazio(self):
        self.commit()
        resultado = self.extrair()
        self.assertEqual(resultado["estado"], "completo")
        for chave in ("arquivos", "evidencias", "limitacoes"):
            self.assertEqual(resultado[chave], [])
        for chave in ("linhas_adicionadas", "linhas_removidas",
                      "linhas_adicionadas_na_previa", "linhas_removidas_na_previa"):
            self.assertEqual(resultado[chave], 0)

    def test_arquivo_python(self):
        self.gravar(
            "exemplo.py",
            'import os, sys as sistema\n'
            'from .util import ler\n'
            'class Exemplo:\n'
            '    async def executar(self):\n'
            '        if os.name:  # comentário real\n'
            '            return "# dentro de string"\n'
            '        return """\n'
            'def dentro_de_string():\n'
            '# ainda dentro de string\n'
            '"""\n',
        )
        self.commit()
        resultado = self.extrair()
        self.assertEqual(resultado["linhas_adicionadas"], 10)
        self.assertEqual(resultado["linhas_adicionadas_na_previa"], 10)
        self.assertEqual(
            {(e["tipo"], e["linha"], e.get("nome")) for e in resultado["evidencias"]},
            {
                ("import", 1, "os"), ("import", 1, "sys"), ("import", 2, ".util"),
                ("classe", 3, "Exemplo"), ("funcao", 4, "executar"),
                ("condicao", 5, "if"), ("comentario", 5, None),
            },
        )

    def test_multiplos_arquivos(self):
        self.gravar("modulo com espaco.py", "def calcular():\n    return 1\n")
        self.gravar("testes/test_modulo.py", "def test_calcular():\n    assert True\n")
        self.gravar("README.md", "# Título\n")
        self.commit()
        resultado = self.extrair()
        self.assertEqual(resultado["estado"], "completo")
        arquivos = {a["arquivo"]: a for a in resultado["arquivos"]}
        self.assertEqual(set(arquivos), {"modulo com espaco.py", "testes/test_modulo.py", "README.md"})
        self.assertTrue(arquivos["testes/test_modulo.py"]["arquivo_teste"])
        self.assertEqual(
            [(e["arquivo"], e["linha"]) for e in resultado["evidencias"] if e["tipo"] == "teste"],
            [("testes/test_modulo.py", 1), ("testes/test_modulo.py", 2)],
        )
        self.assertIn(
            {"tipo": "funcao", "nome": "calcular", "lado": "adicionada",
             "arquivo": "modulo com espaco.py", "linha": 1},
            resultado["evidencias"],
        )

    def test_funcao_adicionada_e_contexto_ignorado(self):
        self.gravar("modulo.py", "def existente():\n    pass\n")
        self.commit()
        self.gravar("modulo.py", "def existente():\n    pass\n\ndef nova():\n    pass\n")
        self.commit()
        resultado = self.extrair()
        self.assertEqual(resultado["evidencias"], [
            {"tipo": "funcao", "nome": "nova", "arquivo": "modulo.py",
             "lado": "adicionada", "linha": 4},
        ])
        self.assertEqual(resultado["linhas_adicionadas_na_previa"], 3)

    def test_funcao_removida(self):
        self.gravar("modulo.py", "def antiga():\n    pass")
        self.commit()
        (self.raiz / "modulo.py").unlink()
        self.commit()
        resultado = self.extrair()
        self.assertEqual(resultado["estado"], "completo")
        self.assertEqual(resultado["linhas_removidas_na_previa"], 2)
        self.assertEqual(resultado["evidencias"], [
            {"tipo": "funcao", "nome": "antiga", "arquivo": "modulo.py",
             "lado": "removida", "linha": 1},
        ])

    def test_tratamento_de_erro_sem_executar_codigo(self):
        self.gravar(
            "erros.py",
            "try:\n"
            "    raise RuntimeError('não executar')\n"
            "except RuntimeError:\n"
            "    raise SystemExit(1)\n"
            "finally:\n"
            "    pass\n",
        )
        self.commit()
        self.assertEqual(
            [(e["linha"], e["nome"]) for e in self.extrair()["evidencias"] if e["tipo"] == "excecao"],
            [(1, "try"), (2, "raise"), (3, "except"), (4, "raise"), (5, "finally")],
        )

    def test_diff_truncado_descarta_linha_cortada(self):
        self.gravar("modulo.py", "def visivel():\n    pass\n\ndef cortada():\n    pass\n")
        self.commit()
        previa = analisar_commit(self.raiz)["diff_previa"]
        limite = previa.index("+def cortada") + len("+def cor")
        resultado = self.extrair(max_chars=limite)
        self.assertTrue(resultado["diff_truncado"])
        self.assertEqual(resultado["estado"], "parcial")
        self.assertEqual(resultado["limitacoes"], [{"tipo": "diff_truncado"}])
        self.assertEqual(resultado["linhas_adicionadas"], 5)
        self.assertEqual(resultado["linhas_adicionadas_na_previa"], 3)
        self.assertEqual([e["nome"] for e in resultado["evidencias"]], ["visivel"])

    def test_arquivo_binario_identificado_fora_da_previa(self):
        self.gravar("a_modulo.py", "def executar():\n    pass\n" * 20)
        self.gravar("z_imagem.bin", b"\x00\x01\x02")
        self.commit()
        entrada = analisar_commit(self.raiz, max_chars=100)
        self.assertNotIn("z_imagem.bin", entrada["diff_previa"])
        resultado = analisar_diff(entrada)
        binario = next(a for a in resultado["arquivos"] if a["arquivo"] == "z_imagem.bin")
        self.assertTrue(binario["binario"])
        self.assertIsNone(binario["adicionadas"])
        self.assertIsNone(binario["removidas"])
        self.assertFalse(any(e["arquivo"] == "z_imagem.bin" for e in resultado["evidencias"]))

    def test_hunk_malformado_mantem_outros_hunks(self):
        self.gravar("a.py", "def ignorar():\n    pass\n")
        self.gravar("b.py", "def manter():\n    pass\n")
        self.commit()
        entrada = analisar_commit(self.raiz)
        entrada["diff_previa"] = entrada["diff_previa"].replace(
            "@@ -0,0 +1,2 @@", "@@ -0,0 +1,3 @@", 1,
        )
        resultado = analisar_diff(entrada)
        self.assertEqual(resultado["estado"], "parcial")
        self.assertEqual(resultado["limitacoes"], [{"tipo": "hunk_malformado", "arquivo": "a.py"}])
        self.assertEqual(resultado["linhas_adicionadas_na_previa"], 2)
        self.assertEqual([e["nome"] for e in resultado["evidencias"]], ["manter"])

    def test_marcadores_dos_cabecalhos_e_das_linhas_do_hunk(self):
        self.gravar("dados.txt", "-- antes\n")
        self.commit()
        self.gravar("dados.txt", "++ depois\n")
        self.commit()
        entrada = analisar_commit(self.raiz)
        self.assertIn("\n--- antes\n+++ depois\n", entrada["diff_previa"])
        resultado = analisar_diff(entrada)
        self.assertEqual(resultado["estado"], "completo")
        self.assertEqual(resultado["linhas_adicionadas_na_previa"], 1)
        self.assertEqual(resultado["linhas_removidas_na_previa"], 1)
        self.assertEqual(resultado["evidencias"], [])

    def test_somente_readme(self):
        self.gravar("README", "Instruções\n")
        self.commit("fix: atualizar instruções")
        indicios = self.extrair()["indicios"]
        self.assertEqual(indicios["categoria"], "docs")
        self.assertEqual(indicios["estado"], "com_indicios")
        self.assertFalse(indicios["misto"])
        self.assertEqual(indicios["arquivos_relacionados"], ["README"])
        self.assertEqual(indicios["evidencias"], [
            {"tipo": "caminho", "arquivo": "README", "categorias": ["docs"]},
        ])
        self.assertIn("intenção", indicios["limites"][0])

    def test_somente_documentacao(self):
        self.gravar("docs/guia.txt", "Guia\n")
        self.gravar("referencia.rst", "Referência\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertEqual(indicios["categoria"], "docs")
        self.assertEqual(indicios["arquivos_relacionados"], ["docs/guia.txt", "referencia.rst"])

    def test_somente_testes_python(self):
        self.gravar("test_exemplo.py", "assert True\n")
        self.gravar("simples_test.py", "assert 1 == 1\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertEqual(indicios["categoria"], "test")
        self.assertEqual(indicios["arquivos_relacionados"], ["simples_test.py", "test_exemplo.py"])

    def test_somente_testes_javascript(self):
        self.gravar("src/exemplo.test.js", "test('exemplo', () => {});\n")
        self.gravar("src/outro.spec.js", "test('outro', () => {});\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertEqual(indicios["categoria"], "test")
        self.assertEqual(indicios["arquivos_relacionados"], ["src/exemplo.test.js", "src/outro.spec.js"])

    def test_documentacao_e_codigo_misturados(self):
        self.gravar("docs/guia.md", "# Guia\n")
        self.gravar("docs/exemplo.py", "print('Exemplo')\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertEqual(indicios["estado"], "inconclusivo")
        self.assertTrue(indicios["misto"])
        self.assertEqual(indicios["arquivos_relacionados"], ["docs/guia.md"])

    def test_testes_e_codigo_misturados(self):
        self.gravar("src/calculo.py", "def calcular():\n    return 1\n")
        self.gravar("testes/test_calculo.py", "assert True\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertEqual(indicios["estado"], "inconclusivo")
        self.assertTrue(indicios["misto"])
        self.assertEqual(indicios["arquivos_relacionados"], ["testes/test_calculo.py"])

    def test_arquivos_nao_reconhecidos_ignoram_prefixo_do_titulo(self):
        self.gravar("src/calculo.py", "def calcular():\n    return 1\n")
        self.gravar("dados.csv", "valor\n1\n")
        self.commit("docs: título sem prova")
        indicios = self.extrair()["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertEqual(indicios["estado"], "inconclusivo")
        self.assertFalse(indicios["misto"])
        self.assertEqual(indicios["evidencias"], [])
        self.assertEqual(indicios["arquivos_relacionados"], [])

    def test_documentacao_e_testes_no_mesmo_commit(self):
        self.gravar("README.md", "# Exemplo\n")
        self.gravar("src/exemplo.test.js", "test('exemplo', () => {});\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertEqual(indicios["estado"], "inconclusivo")
        self.assertTrue(indicios["misto"])
        self.assertEqual([e["categorias"] for e in indicios["evidencias"]], [["docs"], ["test"]])

    def test_caminho_com_sinais_sobrepostos(self):
        self.gravar("tests/README.md", "# Como testar\n")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertEqual(indicios["estado"], "inconclusivo")
        self.assertEqual(indicios["evidencias"][0]["categorias"], ["docs", "test"])

    def test_binario_com_nome_de_documentacao_nao_da_indicio(self):
        self.gravar("README.md", b"\x00\x01\x02")
        self.commit()
        indicios = self.extrair()["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertEqual(indicios["evidencias"], [])

    def test_indicios_consideram_arquivos_fora_da_previa_truncada(self):
        self.gravar("README.md", "# Exemplo\n" * 20)
        self.gravar("z_codigo.py", "print('Exemplo')\n")
        self.commit()
        entrada = analisar_commit(self.raiz, max_chars=100)
        self.assertTrue(entrada["diff_truncado"])
        self.assertNotIn("z_codigo.py", entrada["diff_previa"])
        indicios = analisar_diff(entrada)["indicios"]
        self.assertIsNone(indicios["categoria"])
        self.assertTrue(indicios["misto"])


    def alterar_codigo(self, antes, depois, **opcoes):
        self.gravar("modulo.py", antes)
        self.commit()
        self.gravar("modulo.py", depois)
        self.commit("docs: exemplo")
        return self.extrair(**opcoes)["indicios_codigo"]

    def test_codigo_tratamento_excecao(self):
        r = self.alterar_codigo("ler()\n", "try:\n    ler()\nexcept ValueError:\n    pass\n")
        self.assertEqual(r["candidatas"], ["fix"])
        self.assertEqual(r["evidencias"][0]["linha"], 3)

    def test_codigo_funcao_endpoint_e_arquivo(self):
        self.gravar("api.py", '@app.get("/itens")\ndef itens():\n    return []\n')
        self.commit()
        r = self.extrair()["indicios_codigo"]
        self.assertEqual(r["candidatas"], ["feat"])
        self.assertEqual({e["tipo"] for e in r["evidencias"]}, {"endpoint", "declaracao", "arquivo_novo"})

    def test_codigo_condicao_alterada(self):
        r = self.alterar_codigo("if valor:\n    ler()\n", "if valor is not None:\n    ler()\n")
        self.assertEqual(r["candidatas"], ["fix"])
        self.assertEqual({e["tipo"] for e in r["evidencias"]}, {"condicao_alterada", "verificacao_nulo"})

    def test_codigo_extracao(self):
        r = self.alterar_codigo("def custo(x):\n    return x * 2\n",
                                "def custo(x):\n    return dobro(x)\n\ndef dobro(x):\n    return x * 2\n")
        self.assertIn("extracao_funcao", [e["tipo"] for e in r["evidencias"]])
        self.assertEqual(r["candidatas"], ["feat", "refactor"])

    def test_codigo_cosmetico(self):
        r = self.alterar_codigo("if valor > 0:\n    ler()\n", "if valor>0:  # comentário\n    ler()\n")
        self.assertEqual(r["candidatas"], [])
        self.assertEqual(r["estado"], "inconclusivo")

    def test_codigo_ambiguo(self):
        r = self.alterar_codigo("x = 1\n", "def validar(x):\n    assert x > 0\n")
        self.assertEqual(r["candidatas"], ["feat", "fix"])
        self.assertEqual(r["estado"], "inconclusivo")

    def test_codigo_truncado(self):
        r = self.alterar_codigo("x = 1\n", "def nova():\n    return 1\n" * 30, max_chars=120)
        self.assertTrue(r["diff_truncado"])
        self.assertTrue(r["previa_insuficiente"])
        self.assertEqual(r["estado"], "inconclusivo")


if __name__ == "__main__":
    unittest.main()
