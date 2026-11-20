"""Testes offline do fluxo academico."""
import csv
import sqlite3
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
            banco=root/"rotulos.sqlite3"
            with sqlite3.connect(banco) as con:
                con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY)")
                con.execute("INSERT INTO avaliacoes VALUES (?)", ("1",))
            class Dummy:
                def __init__(self):
                    self.named_steps={}
            with patch("commitx.academico._batch_previsoes",return_value=[{
                "categoria_prevista":"fix","segunda_opcao":"feat","margem_svm":9.0,
                "tipo_declarado":"","revisar":0
            }]):
                samples,counts,discards=_pseudo(Dummy(),entrada,original,banco=banco,minimo=0.3)
            self.assertEqual(samples,[])
            self.assertEqual(discards["particao_reservada"],1)

    def test_pseudo_usa_apenas_nao_rotulados_do_treino(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            preparado=root/"preparado.csv"
            banco=root/"rotulos.sqlite3"
            campos=["id","titulo","repositorio","particao"]
            with sqlite3.connect(banco) as con:
                con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY)")
                con.execute("INSERT INTO avaliacoes VALUES (?)",("1",))
            rows=[
                {"id":"1","titulo":"fix: problema antigo","repositorio":"a","particao":"treino"},
                {"id":"2","titulo":"feat: recurso novo","repositorio":"b","particao":"treino"},
                {"id":"3","titulo":"docs: reservado","repositorio":"c","particao":"validacao"},
                {"id":"4","titulo":"test: reservado","repositorio":"d","particao":"teste"},
            ]
            with preparado.open("w",encoding="utf-8",newline="") as f:
                w=csv.DictWriter(f,fieldnames=campos)
                w.writeheader()
                w.writerows(rows)
            class Dummy:
                pass
            with patch("commitx.academico._batch_previsoes") as previsao:
                previsao.side_effect=lambda model,batch:[
                    {"categoria_prevista":"feat","segunda_opcao":"fix",
                     "margem_svm":2.0,"tipo_declarado":"","revisar":0}
                    for _ in batch]
                pseudo,counts,descartes=_pseudo(
                    Dummy(),preparado,preparado,banco=banco,minimo=1.5)
            self.assertEqual(pseudo,[("feat: recurso novo","feat")])
            self.assertEqual(counts["feat"],1)
            self.assertEqual(descartes["particao_reservada"],2)

    def test_titulo_vazio(self):
        with self.assertRaises(ValueError):
            analisar(None," ")
