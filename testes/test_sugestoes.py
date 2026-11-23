"""Testes offline das sugestões: nunca persistir predições sem revisão."""
import csv
from pathlib import Path
import tempfile
import unittest

from commitx.rotulagem import (
    abrir_banco, ler_amostra, perguntar, registrar, rotular, status,
)
from commitx.sugestoes import Sugestor


class TestSugestoes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        pasta = Path(self.temp.name)
        caminho = pasta / "amostra.csv"
        with caminho.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id", "titulo", "descricao", "grupo", "origem"]
            )
            writer.writeheader()
            writer.writerow({
                "id": "a", "titulo": "feat: adicionar filtro por data",
                "descricao": "", "grupo": "repo:a", "origem": "git",
            })
            writer.writerow({
                "id": "b", "titulo": "fix: corrigir bug",
                "descricao": "", "grupo": "repo:b", "origem": "git",
            })
        self.amostra = ler_amostra(caminho)
        self.db = abrir_banco(pasta / "avaliacoes.sqlite3")
        self.addCleanup(self.db.close)

    def test_sugestao_nao_salva_rotulo(self):
        sugestor = Sugestor(self.amostra, self.db)
        proposta = sugestor.analisar("feat: adicionar filtro por data")
        self.assertEqual(proposta["categoria"], "feat")
        self.assertIsNone(proposta["clareza"])
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 0)

    def test_regra_de_clareza_nao_e_treinamento(self):
        sugestor = Sugestor(self.amostra, self.db)
        proposta = sugestor.analisar("fix: corrigir bug")
        self.assertEqual(proposta["clareza"], "vago")
        self.assertIn("regra", proposta["origem_clareza"])
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 0)

    def test_confirmar_enter_com_sugestao(self):
        saida = []
        resposta = perguntar({"1": "fix", "2": "feat"}, "Categoria",
                             entrada=lambda _: "", saida=saida.append,
                             sugestao="feat")
        self.assertEqual(resposta, "feat")

    def test_sem_sugestao_enter_nao_confirma(self):
        respostas = iter(["", "2"])
        resposta = perguntar({"1": "fix", "2": "feat"}, "Categoria",
                             entrada=lambda _: next(respostas),
                             saida=lambda _: None, sugestao=None)
        self.assertEqual(resposta, "feat")

    def test_revisor_pode_corrigir_previsao(self):
        sugestor = Sugestor(self.amostra, self.db)
        respostas = iter(["1", "2"])
        self.assertEqual(rotular(
            self.amostra, self.db, sugestor=sugestor,
            entrada=lambda _: next(respostas), saida=lambda _: None, limite=1,
        ), 1)
        self.assertEqual(status(self.amostra, self.db)["categorias"]["fix"], 1)
        self.assertEqual(status(self.amostra, self.db)["clareza"]["parcial"], 1)


if __name__ == "__main__":
    unittest.main()
