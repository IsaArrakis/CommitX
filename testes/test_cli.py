"""Verifica o uso pelo terminal, inclusive fora da pasta do projeto."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROGRAMA = Path(__file__).resolve().parents[1] / "commits.py"


class TestCLI(unittest.TestCase):
    def executar(self, *argumentos, cwd=None, entrada=None):
        return subprocess.run(
            [sys.executable, str(PROGRAMA), *argumentos],
            cwd=cwd, input=entrada, capture_output=True, text=True, timeout=30,
        )

    def test_json_com_recomendacao_para_mensagem_vaga(self):
        with tempfile.TemporaryDirectory() as pasta:
            resultado = self.executar("analisar", "fix(admin): bug no painel", "--json", cwd=pasta)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        analise = json.loads(resultado.stdout)
        self.assertEqual(analise["escrita"]["tipo_declarado"], "fix")
        self.assertIn("titulo_vago", [a["codigo"] for a in analise["escrita"]["alertas"]])

    def test_categoria_fora_do_escopo_exige_revisao(self):
        resultado = self.executar("analisar", "ci: executar testes", "--json")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIsNone(json.loads(resultado.stdout)["classificacao"]["categoria_sugerida"])

    def test_interativo_sem_argumentos_e_sem_alerta_para_docs_especifica(self):
        resultado = self.executar(entrada="docs: corrigir link de instalação no README\n\n\n")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Nenhum alerta destas regras", resultado.stdout)

    def test_base_invalida_mostra_erro_acionavel_sem_traceback(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "invalido.csv"
            arquivo.write_text("titulo\nMensagem sem categoria\n", encoding="utf-8")
            resultado = self.executar("avaliar", "--dados", str(arquivo))
        self.assertEqual(resultado.returncode, 2)
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertIn("error:", resultado.stderr)


if __name__ == "__main__":
    unittest.main()
