"""Testes offline do fluxo de rotulagem."""
import csv
from pathlib import Path
import tempfile
import unittest

from commitx.rotulagem import (
    abrir_banco, ler_amostra, registrar, rotular, status, exportar
)


class TestRotulagem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.arquivo = self.pasta / "amostra.csv"
        with self.arquivo.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "id", "titulo", "descricao", "grupo", "origem", "categoria"
            ])
            w.writeheader()
            w.writerow({"id": "1", "titulo": "Corrigir paginação",
                        "descricao": "segunda página duplicada",
                        "grupo": "repo/a", "origem": "git", "categoria": ""})
            w.writerow({"id": "2", "titulo": "docs: atualizar manual",
                        "descricao": "", "grupo": "repo/b",
                        "origem": "hf", "categoria": ""})
        self.amostra = ler_amostra(self.arquivo)
        self.db = abrir_banco(self.pasta / "avaliacoes.sqlite3")
        self.addCleanup(self.db.close)

    def test_salvar_e_retornar_status(self):
        registrar(self.db, "1", "fix", "claro")
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 1)
        self.assertEqual(status(self.amostra, self.db)["restantes"], 1)
        self.assertEqual(status(self.amostra, self.db)["categorias"]["fix"], 1)

    def test_nao_rotular_automaticamente(self):
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 0)
        iterador = iter(["1", "3"])
        self.assertEqual(rotular(self.amostra, self.db,
                                entrada=lambda _: next(iterador),
                                saida=lambda *_: None, limite=1), 1)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 1)
        self.assertEqual(status(self.amostra, self.db)["clareza"]["vago"], 1)

    def test_retomada_sem_sobrescrever(self):
        registrar(self.db, "1", "fix", "vago")
        iterador = iter(["3", "1"])
        self.assertEqual(rotular(self.amostra, self.db,
                                entrada=lambda _: next(iterador),
                                saida=lambda *_: None, limite=1), 1)
        self.assertEqual(status(self.amostra, self.db)["avaliados"], 2)
        self.assertEqual(status(self.amostra, self.db)["categorias"]["fix"], 1)

    def test_exportacao_e_nao_sobrescrita(self):
        registrar(self.db, "1", "fix", "claro")
        arq = self.pasta / "revisados.csv"
        self.assertEqual(exportar(self.amostra, self.db, arq), 1)
        with arq.open(encoding="utf-8") as f:
            r = list(csv.DictReader(f))
        self.assertEqual(r[0]["categoria"], "fix")
        self.assertEqual(r[0]["clareza"], "claro")
        with self.assertRaises(FileExistsError):
            exportar(self.amostra, self.db, arq)

    def test_recusa_rotulos_invalidos(self):
        with self.assertRaises(ValueError):
            registrar(self.db, "1", "bug", "claro")
        with self.assertRaises(ValueError):
            registrar(self.db, "1", "fix", "perfeito")


if __name__ == "__main__":
    unittest.main()
