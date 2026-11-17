import unittest

from commitx.escrita import parse_cabecalho, revisar_escrita, texto_modelo


class TestEscrita(unittest.TestCase):
    def codigos(self, titulo, descricao=""):
        return {alerta["codigo"] for alerta in revisar_escrita(titulo, descricao)["alertas"]}

    def test_reconhece_escopo_opcional_e_quebra(self):
        self.assertEqual(parse_cabecalho("feat!: permitir novo formato"), {
            "tipo": "feat", "escopo": None,
            "resumo": "permitir novo formato", "quebra": True,
        })
        self.assertEqual(parse_cabecalho("fix(admin): corrigir paginação"), {
            "tipo": "fix", "escopo": "admin",
            "resumo": "corrigir paginação", "quebra": False,
        })

    def test_nao_confunde_texto_livre_com_cabecalho(self):
        self.assertIsNone(parse_cabecalho("Arrumar bug no painel do admin"))
        self.assertIsNone(parse_cabecalho("fix:sem espaço"))
        self.assertIsNone(parse_cabecalho("fix: título\nCorpo não faz parte do título"))

    def test_prefixo_removido_sem_perder_negacao_ou_corpo(self):
        self.assertEqual(
            texto_modelo("fix(auth)!: não encerrar sessão", "Não altera permissões.\nfix: exemplo no corpo"),
            "não encerrar sessão\nNão altera permissões.\nfix: exemplo no corpo",
        )
        self.assertEqual(texto_modelo("feat:não excluir arquivos"), "não excluir arquivos")
        self.assertEqual(texto_modelo("Não encerrar sessão"), "Não encerrar sessão")

    def test_encontra_os_dois_exemplos_vagos(self):
        self.assertIn("titulo_vago", self.codigos("fix(admin): bug no painel"))
        self.assertIn("titulo_vago", self.codigos("Arrumar bug no painel do admin"))
        self.assertIn("titulo_vago", self.codigos("refactor: melhorias no código"))

    def test_bug_com_contexto_concreto_nao_e_sinalizado_como_vago(self):
        self.assertNotIn(
            "titulo_vago",
            self.codigos("fix: corrigir bug na paginação ao abrir segunda página"),
        )
        self.assertNotIn("titulo_vago", self.codigos("fix: corrigir erro 500 ao salvar perfil"))
        self.assertNotIn("titulo_vago", self.codigos("fix: arrumar cálculo de frete"))

    def test_documentacao_especifica_sem_corpo_nao_e_penalizada(self):
        resultado = revisar_escrita("docs: corrigir link de instalação no README")
        self.assertEqual(resultado["alertas"], [])
        self.assertTrue(resultado["cabecalho_reconhecido"])

    def test_formato_e_clareza_sao_separados(self):
        self.assertEqual(
            self.codigos("Corrigir link de instalação no README"),
            {"formato_convencional"},
        )
        self.assertNotIn("formato_convencional", self.codigos("fix(admin): bug no painel"))

    def test_template_preserva_cabecalho_e_pede_informacoes(self):
        resultado = revisar_escrita("fix(admin)!: bug no painel")
        modelo = resultado["modelo_para_preencher"]
        self.assertTrue(modelo.startswith("fix(admin)!: [ação e mudança específica]"))
        self.assertIn("[Detalhe relevante da implementação, se houver.]", modelo)
        self.assertEqual(resultado["tipo_declarado"], "fix")
        self.assertEqual(resultado["escopo_declarado"], "admin")
        self.assertIn("Ausência de alertas não comprova clareza", resultado["limite"])

    def test_titulo_vazio_e_rejeitado(self):
        for funcao in (parse_cabecalho, texto_modelo, revisar_escrita):
            with self.subTest(funcao=funcao.__name__):
                with self.assertRaises(ValueError):
                    funcao(" \n ")
        with self.assertRaises(ValueError):
            revisar_escrita("fix: ")


if __name__ == "__main__":
    unittest.main()
