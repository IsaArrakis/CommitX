"""Testes da demonstracao local sem abrir navegador ou carregar modelos reais."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commitx.demo_local import obter_resumos, prever, criar_handler, HTML


class FakeModel:
    pass


class TestDemoLocal(unittest.TestCase):
    def test_html_tem_elementos_de_demonstracao(self):
        self.assertIn("CommitX", HTML)
        self.assertIn('id="grafico"', HTML)
        self.assertIn("/api/classificar", HTML)
        self.assertIn("/api/resumo", HTML)

    def test_resumo_comparativo(self):
        with TemporaryDirectory() as temp:
            a = Path(temp) / "a.json"
            b = Path(temp) / "b.json"
            a.write_text(json.dumps({
                "total_classificado": 97001, "treino_humano_assistido": 397,
                "categorias_previstas": {"fix": 123}
            }), encoding="utf-8")
            b.write_text(json.dumps({
                "total_classificado": 97001, "pseudo_rotulos_adicionados": 3797,
                "categorias_previstas": {"feat": 500}
            }), encoding="utf-8")
            r = obter_resumos({"original": a, "pseudo": b})
            self.assertEqual(r["original"]["categorias_previstas"]["fix"], 123)
            self.assertEqual(r["original"]["categorias_previstas"]["docs"], 0)
            self.assertEqual(r["pseudo"]["pseudo_rotulos_adicionados"], 3797)

    def test_entrada_invalida_nao_chama_modelo(self):
        modelos = {"original": FakeModel()}
        for row in (
            {"modelo": "outro", "titulo": "abc"},
            {"modelo": "original", "titulo": ""},
            {"modelo": "original", "titulo": "x" * 1001},
            {"modelo": "original", "titulo": None},
            [],
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                prever(row, modelos)

    def test_handler_e_criavel_sem_servidor(self):
        handler = criar_handler({}, {})
        self.assertTrue(hasattr(handler, "do_GET"))
        self.assertTrue(hasattr(handler, "do_POST"))


if __name__ == "__main__":
    unittest.main()
