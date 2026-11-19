"""Testes isolados da preparação: nenhum download ou modificação de dados reais."""
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.preparacao import preparar, particao_por_repositorio, cabecalho


class TestPreparacao(unittest.TestCase):
    def test_prefixos(self):
        self.assertEqual(cabecalho("feat(ui): adicionar paginação"), "feat")
        self.assertEqual(cabecalho("fix!: corrigir crash"), "fix")
        self.assertEqual(cabecalho("Corrigir paginação"), "")

    def test_mesmo_repositorio_mesma_particao(self):
        p = particao_por_repositorio("github.com/org/projeto")
        self.assertIn(p, {"treino", "validacao", "teste"})
        self.assertEqual(p, particao_por_repositorio("github.com/org/projeto"))

    def test_preparacao_sem_inventar_rotulos_e_sem_apagar_vagos(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            db = raiz / "commits.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE commits (id TEXT PRIMARY KEY, repositorio TEXT, sha TEXT, "
                            "titulo TEXT, descricao TEXT, fonte TEXT, linguagem TEXT, licenca TEXT)")
                con.executemany("INSERT INTO commits VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                    ("1", "org/a", "sha1", "fix: corrigir bug", "", "git:local", "", "MIT"),
                    ("2", "org/b", "sha2", "fix: corrigir bug", "", "git:local", "", "MIT"),
                    ("3", "org/a", "sha3", "feat: adicionar endpoint", "API de busca", "git:local", "Go", "MIT"),
                    ("4", "org/c", "sha4", "alterar API de login", "", "git:local", "", "MIT"),
                ])
            saida = raiz / "saida"
            resumo = preparar(db, saida, 10)
            self.assertEqual(resumo["totais"]["lidos"], 4)
            self.assertEqual(resumo["totais"]["preparados"], 3)
            self.assertEqual(resumo["totais"]["duplicados_texto"], 1)
            with (saida / "commits_preparados.csv").open(encoding="utf-8") as arq:
                linhas = list(csv.DictReader(arq))
            self.assertEqual(len(linhas), 3)
            self.assertEqual({x["categoria"] for x in linhas}, {""})
            self.assertEqual({x["categoria_candidata"] for x in linhas}, {"fix", "feat", ""})
            self.assertIn("fix: corrigir bug", {x["titulo"] for x in linhas})
            self.assertTrue((saida / "amostra_para_rotular.csv").is_file())
            with self.assertRaises(FileExistsError):
                preparar(db, saida, 10)

    def test_tamanho_amostra_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            db = raiz / "commits.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE commits (id TEXT PRIMARY KEY, repositorio TEXT, sha TEXT, "
                            "titulo TEXT, descricao TEXT, fonte TEXT, linguagem TEXT, licenca TEXT)")
                con.execute("INSERT INTO commits VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            ("1", "org/a", "sha1", "docs: adicionar guia", "", "git", "", ""))
            resumo = preparar(db, raiz / "saida", 0)
            self.assertEqual(resumo["amostra"], 0)
