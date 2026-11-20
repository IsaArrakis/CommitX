"""Testes da Fase 2: auditagem e amostra local sem tocar nos rotulos."""
import csv
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from commitx.fase2_dados import auditar, piloto


class TestFase2Dados(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raiz = Path(temp.name)
        self.repo = self.raiz / "repo"
        self.repo.mkdir()

        def git(*args):
            return subprocess.run(["git", "-C", str(self.repo), *args],
                                  check=True, capture_output=True, text=True).stdout.strip()

        self.git = git
        git("init", "-q")
        git("config", "user.name", "CommitX Teste")
        git("config", "user.email", "teste@example.com")
        (self.repo / "teste.py").write_text("a = 1\n", encoding="utf-8")
        git("add", "teste.py")
        git("commit", "-qm", "feat: criar arquivo")
        (self.repo / "teste.py").write_text("a = 2\n", encoding="utf-8")
        git("add", "teste.py")
        git("commit", "-qm", "fix: trocar valor")

    def test_piloto_diff_proveniencia_sem_rotulos(self):
        csv_path = self.raiz / "saida.csv"
        json_path = self.raiz / "saida.json"
        resultado = piloto(self.repo, csv_path, json_path, quantidade=2)
        self.assertEqual(resultado["quantidade"], 2)
        with csv_path.open(encoding="utf-8") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertEqual(linhas[0]["titulo"], "fix: trocar valor")
        self.assertIn("+a = 2", linhas[0]["diff_previa"])
        self.assertEqual(linhas[0]["proveniencia"], "git_local_sha_verificado")
        self.assertEqual(linhas[0]["categoria"], "")
        self.assertEqual(linhas[0]["particao"], "nao_atribuida")
        self.assertEqual(len(linhas[0]["id"]), 40)
        self.assertEqual(json.loads(json_path.read_text())["quantidade"], 2)

    def test_auditoria_nao_altera_banco(self):
        banco = self.raiz / "rotulos.sqlite3"
        with sqlite3.connect(banco) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY, categoria TEXT, clareza TEXT)")
            con.execute("INSERT INTO avaliacoes VALUES ('id-externo', 'fix', 'claro')")
        entrada = self.raiz / "preparado.csv"
        with entrada.open("w", newline="", encoding="utf-8") as arq:
            w = csv.DictWriter(arq, fieldnames=["id", "titulo", "descricao", "repositorio", "particao"])
            w.writeheader()
            w.writerow({"id": "id-externo", "titulo": "fix", "descricao": "",
                        "repositorio": "repo/x", "particao": "treino"})
            w.writerow({"id": "a" * 40, "titulo": "feat", "descricao": "",
                        "repositorio": "repo/y", "particao": "validacao"})
        resumo = auditar(entrada, banco, self.raiz / "auditoria.json")
        self.assertEqual(resumo["resultado"]["total_preparado"], 2)
        self.assertEqual(resumo["resultado"]["rotulos_encontrados"], 1)
        self.assertEqual(resumo["resultado"]["ids_sha40_aparentes"], 1)
        with sqlite3.connect(banco) as con:
            self.assertEqual(con.execute("SELECT count(*) FROM avaliacoes").fetchone()[0], 1)

    def test_nao_sobrescreve_saida(self):
        saida = self.raiz / "piloto.csv"
        saida.write_text("preservar")
        with self.assertRaises(FileExistsError):
            piloto(self.repo, saida, self.raiz / "resumo.json")
        self.assertEqual(saida.read_text(), "preservar")

    def test_nao_aceita_subpasta_como_repo(self):
        pasta = self.repo / "subpasta"
        pasta.mkdir()
        with self.assertRaisesRegex(ValueError, "pasta raiz"):
            piloto(pasta, self.raiz / "dados.csv", self.raiz / "dados.json")


if __name__ == "__main__":
    unittest.main()
