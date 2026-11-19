"""Testes offline da triagem em lote, sem usar a rede."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from commitx.rotulagem_automatica import gerar, processar_lote, rotulos_humanos


class TestRotulagemAutomatica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.entrada = self.raiz / "amostra.csv"
        with self.entrada.open("w", encoding="utf-8", newline="") as arq:
            w = csv.DictWriter(arq, fieldnames=[
                "id", "titulo", "descricao", "origem", "repositorio", "grupo", "particao"
            ])
            w.writeheader()
            w.writerows([
                {"id": "1", "titulo": "fix: corrigir bug", "descricao": "",
                 "origem": "git", "repositorio": "repo-a"},
                {"id": "2", "titulo": "docs: atualizar guia", "descricao": "Revisão da instalação",
                 "origem": "git", "repositorio": "repo-b"},
                {"id": "3", "titulo": "runtime: atualizar gerenciador", "descricao": "",
                 "origem": "git", "repositorio": "repo-c"},
            ])
        self.banco = self.raiz / "avaliacoes.sqlite3"
        with sqlite3.connect(self.banco) as con:
            con.execute("CREATE TABLE avaliacoes "
                        "(id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)")
            con.execute("INSERT INTO avaliacoes VALUES ('2', 'docs', 'claro')")

    def modelo(self):
        return Mock(predict=Mock(side_effect=lambda textos: ["feat"] * len(textos)))

    def test_preserva_rótulo_humano_e_separa_sugestao(self):
        resumo = gerar(
            self.entrada, self.raiz / "sugestoes.csv", self.raiz / "resumo.json",
            banco_humano=self.banco, lote=2, modelo=self.modelo()
        )
        with (self.raiz / "sugestoes.csv").open(encoding="utf-8") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertEqual(len(linhas), 3)
        self.assertEqual(linhas[1]["categoria_humana"], "docs")
        self.assertEqual(linhas[1]["clareza_humana"], "claro")
        self.assertEqual(linhas[1]["categoria_prevista_modelo"], "feat")
        self.assertEqual(linhas[1]["status"], "revisado_humano")
        self.assertEqual(linhas[2]["categoria_sugerida"], "")
        self.assertEqual(linhas[2]["status"], "pendente_revisao")
        self.assertEqual(resumo["estatisticas"]["processados"], 3)

    def test_nao_sobrescreve_csv_ou_relatorio(self):
        caminho = self.raiz / "sugestoes.csv"
        resumo = self.raiz / "resumo.json"
        gerar(self.entrada, caminho, resumo, banco_humano=self.banco,
              modelo=self.modelo())
        with self.assertRaises(FileExistsError):
            gerar(self.entrada, caminho, resumo, banco_humano=self.banco,
                  modelo=self.modelo())

    def test_lotes_respeitam_limite(self):
        gerar(self.entrada, self.raiz / "s.csv", self.raiz / "r.json",
              banco_humano=self.banco, lote=2, limite=2, modelo=self.modelo())
        with (self.raiz / "s.csv").open(encoding="utf-8") as arq:
            self.assertEqual(len(list(csv.DictReader(arq))), 2)

    def test_sem_banco_humano_nao_cria_banco(self):
        inexistente = self.raiz / "nenhum.sqlite3"
        self.assertEqual(rotulos_humanos(inexistente), {})
        self.assertFalse(inexistente.exists())


if __name__ == "__main__":
    unittest.main()
