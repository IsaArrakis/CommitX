"""Testes do empacotamento V12; nao usam dados privados nem redes."""
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

from commitx.v12_final import (
    SinaisContextuaisV12, novo_modelo_v12, analisar_modelo, treinar_e_salvar,
    MODEL_COM, MANIFESTO,
)
from commitx.foco_docs_refactor_v10 import pesos_do_fold


class V12FinalTests(unittest.TestCase):
    def test_extra_sinais_mantem_ordem_e_quantidade(self):
        dados = ['Use OrderedDict for data', 'Remove unnecessary imports', 'Add new API']
        matriz = SinaisContextuaisV12().fit(dados).transform(dados)
        self.assertEqual(matriz.shape, (3, 9))
        self.assertEqual(float(matriz[0, 0]), 1.0)
        self.assertEqual(float(matriz[1, 2]), 1.0)
        self.assertEqual(float(matriz[2, 5]), 1.0)

    def test_modelo_persistente_e_com_sinais_iguais(self):
        textos = [
            'fix: correct bug in parser', 'fix: repair broken routing',
            'feat: add API resource', 'feat: implement filter',
            'docs: update README', 'docs: write documentation',
            'refactor: extract function', 'refactor: simplify class',
            'test: add tests for parser', 'test: improve assert coverage',
        ]
        y = np.array([c for c in ('fix','feat','docs','refactor','test') for _ in range(2)])
        pesos = pesos_do_fold(y, 1.75, 1.5)
        modelo = novo_modelo_v12(pesos)
        self.assertEqual(dict(modelo.named_steps['tfidf'].transformer_weights),
                         {'palavras': 1.0, 'sinais_v11': 0.5, 'sinais_extra_v12': 0.30})
        modelo.fit(textos, y)
        esperado = list(modelo.predict(textos))
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / 'teste.joblib'
            joblib.dump(modelo, destino)
            igual = joblib.load(destino)
            self.assertEqual(list(igual.predict(textos)), esperado)

    def test_treinamento_nao_sobrescreve_saida(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(FileExistsError):
                treinar_e_salvar(saida=pasta)

    def test_sem_artefato_nao_finge_classificacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(FileNotFoundError):
                analisar_modelo(pasta, 'Add resource')

    def test_tipo_fora_escopo_abstem_sem_abrir_artefato(self):
        with tempfile.TemporaryDirectory() as pasta:
            r = analisar_modelo(pasta, 'ci: Update build workflow')
        self.assertIsNone(r['categoria_sugerida'])
        self.assertEqual(r['tipo_declarado'], 'ci')


if __name__ == '__main__':
    unittest.main()
