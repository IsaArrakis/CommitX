"""Testes offline do modo de revisão rápida: confirmação, edição, pausa e privacidade."""
import csv
from pathlib import Path
import tempfile
import unittest

from commitx.revisao_lote import interpretar_respostas, revisar_em_lote
from commitx.rotulagem import abrir_banco, registrar, status


class StubSugestor:
    def analisar(self, titulo, descricao=""):
        if "fix" in titulo:
            return {"categoria": "fix", "clareza": None}
        return {"categoria": "docs", "clareza": "claro"}


class TestRevisaoLote(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = abrir_banco(Path(self.temp.name) / "avaliacoes.sqlite3")
        self.addCleanup(self.db.close)
        self.amostra = [
            {"id": "1", "titulo": "fix: corrigir login", "descricao": "",
             "origem": "git", "grupo": "r1", "particao": "treino"},
            {"id": "2", "titulo": "docs: atualizar tutorial", "descricao": "Detalhes",
             "origem": "git", "grupo": "r2", "particao": "treino"},
            {"id": "3", "titulo": "fix: corrigir logout", "descricao": "",
             "origem": "git", "grupo": "r3", "particao": "validacao"},
        ]

    def _revisar(self, respostas, limite=20, tamanho=3):
        it = iter(respostas)
        return revisar_em_lote(
            self.amostra, self.db, tamanho=tamanho, limite=limite,
            sugestor=StubSugestor(), entrada=lambda _: next(it),
            imprimir=lambda *_: None,
        )

    def test_aceita_categoria_sugerida_com_clareza_humana_e_corrige_outra(self):
        n = self._revisar(["1=,3;2=4,2", "q"])
        self.assertEqual(n, 2)
        resultado = status(self.amostra, self.db)
        self.assertEqual(resultado["avaliados"], 2)
        registros = dict(
            (uid, (categoria, clareza))
            for uid, categoria, clareza in self.db.execute(
                "SELECT id,categoria,clareza FROM avaliacoes"
            )
        )
        self.assertEqual(registros["1"], ("fix", "claro"))
        self.assertEqual(registros["2"], ("refactor", "parcial"))

    def test_rejeita_linha_inteira_antes_de_salvar(self):
        sugestoes = {1: {"categoria": "fix"}, 2: {"categoria": "docs"}}
        with self.assertRaises(ValueError):
            interpretar_respostas("1=,3;2=99,2", self.amostra[:2], sugestoes)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 0)

    def test_sem_clareza_nao_permite_ok(self):
        with self.assertRaises(ValueError):
            interpretar_respostas(
                "1=ok", self.amostra[:1],
                {1: {"categoria": "fix", "clareza": None}}
            )

    def test_validacao_nao_recebe_sugestao(self):
        # Não permite "ok" na mensagem reservada, mesmo com sugestor presente.
        n = self._revisar(["1=,3;2=ok", "3=ok", "q"])
        self.assertEqual(n, 2)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 2)

    def test_retomada_pula_anteriores(self):
        registrar(self.db, "1", "fix", "claro")
        n = self._revisar(["1=3,2", "q"])
        self.assertEqual(n, 1)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 2)

    def test_controle_de_limite(self):
        n = self._revisar(["1=1,3;2=3,3", "1=1,3", "q"], limite=1)
        self.assertEqual(n, 1)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 1)

    def test_pagina_unica_com_30_e_resposta_unica(self):
        amostra = [
            {"id": str(i), "titulo": f"fix: corrigir caso {i}",
             "descricao": "", "origem": "git", "grupo": f"r{i}",
             "particao": "treino"}
            for i in range(1, 31)
        ]
        resposta = ";".join(f"{i}=1,3" for i in range(1, 31))
        entradas = iter([resposta])
        exibicoes = []
        total = revisar_em_lote(
            amostra, self.db, tamanho=30, limite=30, sugestor=None,
            entrada=lambda _: next(entradas), imprimir=exibicoes.append,
        )
        self.assertEqual(total, 30)
        self.assertEqual(status(amostra, self.db)["avaliados"], 30)
        self.assertTrue(any("30 mensagens / 30" in linha for linha in exibicoes))
        self.assertTrue(any("[30]" in linha for linha in exibicoes))

    def test_pagina_30_retomada_preserva_rótulos(self):
        amostra = [
            {"id": str(i), "titulo": f"feat: atividade {i}",
             "descricao": "", "origem": "git", "grupo": f"r{i}",
             "particao": "treino"}
            for i in range(1, 31)
        ]
        registrar(self.db, "1", "fix", "parcial")
        entradas = iter(["1=2,3", "q"])
        total = revisar_em_lote(
            amostra, self.db, tamanho=30, limite=30, sugestor=None,
            entrada=lambda _: next(entradas), imprimir=lambda *_: None,
        )
        self.assertEqual(total, 1)
        self.assertEqual(status(amostra, self.db)["avaliados"], 2)
        atual = self.db.execute(
            "SELECT categoria,clareza FROM avaliacoes WHERE id='1'"
        ).fetchone()
        self.assertEqual(atual, ("fix", "parcial"))

    def test_rejeita_tamanho_acima_de_50(self):
        with self.assertRaisesRegex(ValueError, "entre 1 e 50"):
            revisar_em_lote(
                self.amostra, self.db, tamanho=51, limite=51,
                entrada=lambda _: "q", imprimir=lambda *_: None,
            )

    def test_pagina_unica_43_commits_uma_resposta(self):
        amostra = [
            {"id": f"amostra43-{i}", "titulo": f"fix: caso {i}",
             "descricao": "", "origem": "git", "grupo": f"r{i}",
             "particao": "treino"} for i in range(1, 44)
        ]
        resposta = ";".join(f"{i}=1,3" for i in range(1, 44))
        saidas = []
        salvos = revisar_em_lote(
            amostra, self.db, tamanho=43, limite=43,
            sugestor=None, entrada=lambda _: resposta, imprimir=saidas.append
        )
        self.assertEqual(salvos, 43)
        self.assertEqual(status(amostra, self.db)["avaliados"], 43)
        self.assertTrue(any("43 mensagens / 43" in s for s in saidas))
        self.assertTrue(any("[43]" in s for s in saidas))

    def test_interrupcao_retorna_sem_perder(self):
        n = self._revisar(["1=1,3", "q"])
        self.assertEqual(n, 1)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 1)


if __name__ == "__main__":
    unittest.main()
