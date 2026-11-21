"""Testes isolados da avaliacao externa; nao dependem de Git nem modelos reais."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commitx.avaliacao_externa import (
    _amostrar, _exclusoes, _norm, _repo_nome, _rotulos, _salvar,
    ROTULOS, avaliar, rotular,
)


class TestAvaliacaoExterna(unittest.TestCase):
    def test_normaliza_e_reconhece_repo(self):
        self.assertEqual(_norm("fix: Correct login"), "correct login")
        self.assertEqual(_repo_nome("https://github.com/pallets/flask.git"), "flask")
        self.assertEqual(_repo_nome("git@github.com:psf/requests.git"), "requests")

    def test_amostra_deterministica_sem_titulo_repetido(self):
        pools = {
            "a": [
                {"id": "1", "titulo": "fix: same title", "repositorio": "a"},
                {"id": "2", "titulo": "add tests", "repositorio": "a"},
            ],
            "b": [
                {"id": "3", "titulo": "feat: same title", "repositorio": "b"},
                {"id": "4", "titulo": "update docs", "repositorio": "b"},
            ],
        }
        a = _amostrar(pools, 4, 42)
        b = _amostrar(pools, 4, 42)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)
        self.assertEqual(len({_norm(r["titulo"]) for r in a}), 3)

    def test_exclusoes_ignoram_colunas_adicionais(self):
        with TemporaryDirectory() as td:
            p = Path(td)
            for name in ("base.csv", "preds.csv"):
                with (p / name).open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["id", "titulo", "particao"])
                    w.writeheader()
                    w.writerow({"id": name, "titulo": "fix: Correct login",
                                "particao": "treino"})
            ids, titulos = _exclusoes(p / "base.csv", p / "preds.csv")
            self.assertEqual(len(ids), 2)
            self.assertEqual(titulos, {"correct login"})

    def test_rotular_salva_e_retorna_com_q(self):
        with TemporaryDirectory() as td:
            p = Path(td)
            import json
            import hashlib
            rows = [
                {"id": f"{i:040x}", "repositorio": "novo", "titulo": f"Titulo {i}"}
                for i in range(2)
            ]
            with (p / "amostra.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id", "repositorio", "titulo"])
                w.writeheader()
                w.writerows(rows)
            digest = hashlib.sha256((p / "amostra.csv").read_bytes()).hexdigest()
            (p / "manifesto.json").write_text(
                json.dumps({"amostra_sha256": digest, "quantidade": 2}), encoding="utf-8"
            )
            respostas = iter(["1=1", "q"])
            count = rotular(saida=p, tamanho=2, limite=2,
                            input_fn=lambda _: next(respostas), output_fn=lambda _: None)
            self.assertEqual(count, 1)
            self.assertEqual(_rotulos(p, rows), {rows[0]["id"]: "fix"})
            with self.assertRaises(ValueError):
                avaliar(saida=p, modelos={})

    def test_nao_aceita_rotulos_invalidos(self):
        self.assertIn("fora_escopo", ROTULOS)
        with TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                _salvar(td, {"a": "fix"}, [{"id": "a"}])
            # _salvar writes only when a label is supplied; checking that it did not
            # silently assign labels to unreviewed examples is in the rotular test.


if __name__ == "__main__":
    unittest.main()
