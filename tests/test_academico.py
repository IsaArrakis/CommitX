"""Testes offline do fluxo academico."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from commitx.academico import _coluna, _pseudo, analisar, executar, _modelo


class TestAcademico(TestCase):
    def test_colunas_alias(self):
        self.assertEqual(_coluna(["id", "message"]), "message")

    def test_nao_usa_csv_reservado_para_pseudo(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            original=root/"orig.csv"
            entrada=root/"dados.csv"
            with original.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["id","titulo","repositorio","particao"])
                writer.writeheader()
                writer.writerow({"id":"1","titulo":"fix: something","repositorio":"repoA","particao":"treino"})
                writer.writerow({"id":"2","titulo":"feat: something","repositorio":"repoB","particao":"validacao"})
            with entrada.open("w",encoding="utf-8",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["id","titulo","repositorio","particao"])
                writer.writeheader()
                writer.writerow({"id":"3","titulo":"Fix broken test","repositorio":"repoB","particao":"treino"})
            class Dummy:
                def __init__(self):
                    self.named_steps={}
            with patch("commitx.academico._batch_previsoes",return_value=[{
                "categoria_prevista":"fix","segunda_opcao":"feat","margem_svm":9.0,
                "tipo_declarado":"","revisar":0
            }]):
                samples,counts,discards=_pseudo(Dummy(),entrada,original,minimo=0.3)
            self.assertEqual(samples,[])
            self.assertEqual(discards["particao_reservada"],1)

    def test_titulo_vazio(self):
        with self.assertRaises(ValueError):
            analisar(None," ")
