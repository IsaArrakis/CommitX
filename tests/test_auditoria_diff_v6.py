"""Testes da auditoria local em lote."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from commitx.auditoria_diff_v6 import analisar, procurar


class TestAuditoriaDiffV6(TestCase):
    def test_sha_invalido_nao_executa_git(self):
        with patch("commitx.auditoria_diff_v6.git") as fn:
            repo, status = procurar("--exec=evil", [Path("repos/x")])
            self.assertIsNone(repo)
            self.assertEqual(status, "id_nao_e_sha40")
            fn.assert_not_called()

    def test_relatorio_nao_cria_rotulos(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            entrada = root / "amostra.csv"
            with entrada.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["id","titulo","categoria_svm","categoria_ollama"])
                w.writeheader()
                w.writerow({"id":"a"*40,"titulo":"Fix something",
                            "categoria_svm":"fix","categoria_ollama":"refactor"})
            with patch("commitx.auditoria_diff_v6.repos_disponiveis",return_value=[]):
                result=analisar(entrada,root/"saida",root/"repos")
            self.assertEqual(result["total"],1)
            self.assertEqual(result["status"]["nao_encontrado_nos_clones"],1)
            with (root/"saida"/"auditoria.csv").open(encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]["revisao_humana"],"")
            self.assertEqual(rows[0]["categoria_svm"],"fix")
