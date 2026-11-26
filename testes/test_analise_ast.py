"""Evidências estruturais no formato de entrada do leitor de versões Git."""
import json
import unittest

from commitx.analise_ast import analisar_ast


def arquivo(antes, depois, caminho="codigo.py"):
    def lado(texto):
        return {"conteudo": texto, "tamanho_bytes": len(texto.encode()) if texto is not None else None,
                "motivo": "nao_aplicavel" if texto is None else None}
    status = "adicionado" if antes is None else "removido" if depois is None else "modificado"
    return dict(caminho=caminho, status=status, anterior=lado(antes), posterior=lado(depois),
                cobertura="completa")


def comparar(*arquivos, cobertura="completa", limitacoes=(), **limites):
    versoes = dict(commit="1" * 40, comparado_com=None, arquivos=list(arquivos),
                   cobertura=cobertura, limitacoes=list(limitacoes))
    resultado = analisar_ast(versoes, **limites)
    return json.loads(json.dumps(resultado))


def tipos(resultado):
    return [f["tipo"] for f in resultado["evidencias"]]


class TestAnaliseAST(unittest.TestCase):
    def test_sem_alteracoes_ou_diferencas_estruturais(self):
        for entrada in ([], [arquivo("a = 1", "a = 1")],
                        [arquivo("a = 1", "a = (1)   # descrição")],
                        [arquivo("# antes", "# depois")]):
            r = comparar(*entrada)
            self.assertEqual((r["cobertura"], tipos(r)), ("completa", []))

    def test_docstring(self):
        r = comparar(arquivo('def f():\n    "antiga"', 'def f():\n    "nova"'))
        self.assertEqual(tipos(r), ["docstring_alterada"])
        self.assertEqual(r["evidencias"][0]["posterior"]["linha"], 2)

    def test_classes_e_metodos_adicionados_e_removidos(self):
        codigo = "class A:\n    def ler(self): pass"
        for par, esperados, lado in [
            ((None, codigo), ["classe_adicionada", "funcao_adicionada"], "posterior"),
            ((codigo, None), ["classe_removida", "funcao_removida"], "anterior"),
        ]:
            r = comparar(arquivo(*par))
            self.assertEqual(tipos(r), esperados)
            self.assertEqual(r["evidencias"][1][lado], dict(arquivo="codigo.py", escopo="A.ler", linha=2))

    def test_assinatura_e_decoradores(self):
        r = comparar(arquivo("class A:\n @x\n def f(self, a): pass",
                             "class A:\n @y\n async def f(self, a: int = 1) -> int: pass"))
        self.assertEqual(tipos(r), ["assinatura_modificada", "decoradores_modificados"])

    def test_condicao_existente_e_nova(self):
        a = "if n > 2:\n    executar()"
        b = "if n >= 2:\n    executar()"
        self.assertEqual(tipos(comparar(arquivo(a, b))), ["condicao_modificada"])
        self.assertEqual(tipos(comparar(arquivo(a, "if zero: pass\n" + a))), ["condicao_adicionada"])

    def test_tratamento_de_excecao(self):
        a = "ler()"
        b = "try: ler()\nexcept OSError: pass"
        for antes, depois, tipo in ((a, b, "tratamento_excecao_adicionado"),
                                     (b, a, "tratamento_excecao_removido")):
            self.assertEqual(tipos(comparar(arquivo(antes, depois))), [tipo])

    def test_extracao_exige_bloco_e_chamada_correspondentes(self):
        a = "def calc(x):\n y = x * 2\n return y"
        helper = "def dobro(x):\n y = x * 2\n return y"
        chamada = "def calc(x):\n return dobro(x)\n"
        r = comparar(arquivo(a, chamada + helper))
        self.assertIn("funcao_adicionada", tipos(r))
        fato = next(f for f in r["evidencias"] if f["tipo"] == "possivel_extracao")
        self.assertIn("comportamento", fato["limitacao"])
        self.assertEqual(fato["anterior"]["linha"], 2)
        for novo in (chamada + helper.replace("* 2", "* 3"),
                     chamada.replace("dobro(x)", "dobro(1)") + helper, a + "\n" + helper):
            self.assertNotIn("possivel_extracao", tipos(comparar(arquivo(a, novo))))

    def test_movimentacao_exige_par_unico(self):
        codigo = "def ler(x):\n y = x + 1\n return y"
        origem = arquivo(codigo, None, "antigo.py")
        destino = arquivo(None, codigo, "novo.py")
        r = comparar(origem, destino)
        f = next(f for f in r["evidencias"] if f["tipo"] == "possivel_movimentacao")
        self.assertEqual((f["anterior"]["arquivo"], f["posterior"]["arquivo"]), ("antigo.py", "novo.py"))
        self.assertIn("limitacao", f)
        for outros in ([destino, arquivo(None, codigo, "outro.py")],
                       [arquivo(None, codigo.replace("+ 1", "+ 2"), "novo.py")]):
            self.assertNotIn("possivel_movimentacao", tipos(comparar(origem, *outros)))

    def test_renomeacao_mostra_remocao_e_adicao(self):
        a = "def antiga(x):\n return x"
        r = comparar(arquivo(a, a.replace("antiga", "nova")))
        self.assertCountEqual(tipos(r), ["funcao_removida", "funcao_adicionada"])

    def test_sintaxe_invalida_nao_esconde_arquivo_valido(self):
        invalido = arquivo("def f(): pass", "def f(:")
        r = comparar(invalido)
        self.assertEqual(r["cobertura"], "erro_sintaxe")
        self.assertEqual(tipos(r), [])
        r = comparar(invalido, arquivo(None, "def g(): pass", "outro.py"))
        self.assertEqual(r["cobertura"], "parcial")
        self.assertEqual(tipos(r), ["funcao_adicionada"])
        self.assertEqual(r["arquivos"][0]["limitacoes"][0]["lado"], "posterior")

    def test_cobertura_e_motivos_do_leitor(self):
        reg = arquivo("def antiga(): pass", "")
        reg.update(cobertura="parcial", posterior={"conteudo": None, "motivo": "binario", "tamanho_bytes": 7})
        r = comparar(reg, cobertura="parcial", limitacoes=["binario"])
        self.assertEqual((r["cobertura"], tipos(r), r["limitacoes"]), ("parcial", [], ["binario"]))
        self.assertEqual(r["arquivos"][0]["limitacoes"][0]["motivo"], "binario")
        self.assertEqual(comparar(cobertura="indisponivel")["cobertura"], "indisponivel")

    def test_limites(self):
        for texto, limites, motivo in [
            ("# ação", {"max_bytes": 6}, "limite_bytes"),
            ("x = f(f(f(1)))", {"max_profundidade": 4}, "limite_profundidade"),
            ("x = " + "1+" * 2048 + "2", {}, "limite_complexidade"),
        ]:
            r = comparar(arquivo(None, texto), **limites)
            self.assertEqual(tipos(r), [])
            self.assertEqual(r["arquivos"][0]["limitacoes"][0]["motivo"], motivo)

    def test_codigo_nao_e_importado_ou_executado(self):
        r = comparar(arquivo(None, "import modulo_inexistente\nraise AssertionError()\ndef nova(): pass"))
        self.assertEqual(tipos(r), ["funcao_adicionada"])
        self.assertEqual(r["cobertura"], "completa")

    def test_mudanca_no_corpo_localiza_metodo(self):
        antes = "class C:\n def calcular(self): return 1"
        r = comparar(arquivo(antes, antes.replace("return 1", "return 2")))
        self.assertEqual(tipos(r), ["corpo_modificado"])
        self.assertEqual(r["evidencias"][0]["posterior"]["escopo"], "C.calcular")

    def test_mudanca_generica_no_modulo(self):
        r = comparar(arquivo("x = 1", "x = 2"))
        self.assertEqual(tipos(r), ["estrutura_alterada"])
        self.assertEqual(r["evidencias"][0]["anterior"]["linha"], 1)

    def test_modificacao_de_handler(self):
        a = "try: ler()\nexcept ValueError: pass"
        r = comparar(arquivo(a, a.replace("ValueError", "TypeError")))
        self.assertEqual(tipos(r), ["tratamento_excecao_modificado"])

    def test_condicao_compreensao(self):
        a = "r = [x for x in dados if x > 0]"
        r = comparar(arquivo(a, a.replace(">", ">=")))
        self.assertEqual(tipos(r), ["condicao_modificada"])
