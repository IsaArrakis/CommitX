"""Testes V10 de pesos por classe."""
import tempfile
import unittest

import numpy as np
from commitx.foco_docs_refactor_v10 import CONFIGS, medir, pesos_do_fold, pipeline


class TestFocoDocsRefactorV10(unittest.TestCase):
    def test_pesos_aumentam_somente_docs_e_refactor(self):
        y=np.asarray(["fix"]*10+["feat"]*7+["docs"]*4+["refactor"]*3+["test"]*5)
        base=pesos_do_fold(y,1,1)
        novo=pesos_do_fold(y,1.5,1.75)
        self.assertAlmostEqual(novo["docs"],base["docs"]*1.5)
        self.assertAlmostEqual(novo["refactor"],base["refactor"]*1.75)
        for c in ("fix","feat","test"):
            self.assertAlmostEqual(novo[c],base[c])

    def test_treino_sem_classe_rejeitado(self):
        with self.assertRaises(ValueError):
            pesos_do_fold(np.array(["fix","docs"]),1.0,1.0)

    def test_modelos_validos(self):
        for a,b in CONFIGS.values():
            y=np.asarray(["fix"]*3+["feat"]*3+["docs"]*3+["refactor"]*3+["test"]*3)
            m=pipeline(pesos_do_fold(y,a,b))
            self.assertEqual(list(m.named_steps),["tfidf","model"])

    def test_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                medir([],{},tmp)


if __name__=="__main__":
    unittest.main()
