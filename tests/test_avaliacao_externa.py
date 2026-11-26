"""Testes isolados da avaliacao externa; nao dependem de Git nem modelos reais."""
import csv
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commitx.avaliacao_externa import (
    _amostrar, _exclusoes, _norm, _repo_nome, _rotulos, _salvar,
    CLASSES, ROTULOS, avaliar, preparar_v12, rotular, validar_v12,
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


class TestProtocoloV12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pasta = TemporaryDirectory()
        cls.addClassCleanup(pasta.cleanup)
        cls.raiz = Path(pasta.name)
        cls.repos = []
        for i in range(5):
            repo = cls.raiz / f"projeto-{i}"
            repo.mkdir()
            cls.git(repo, "init", "-q")
            cls.git(repo, "remote", "add", "origin", f"https://example.org/externos/{repo.name}.git")
            for j in range(32):
                cls.git(repo, "commit", "-q", "--allow-empty",
                        "-m", f"fix: Alteração distinta {i}-{j}")
            cls.repos.append(repo)
        cls.id_historico = cls.git(cls.repos[0], "rev-parse", "HEAD")

    @staticmethod
    def git(repo, *args):
        return subprocess.check_output(
            ["git", "-C", str(repo), "-c", "user.name=Teste", "-c",
             "user.email=teste@example.com", *args], text=True,
            env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
        ).strip()

    def setUp(self):
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.saida = self.pasta / "avaliacao"
        self.inventario = self.pasta / "treino.csv"
        self.gravar(self.inventario, ("id", "repositorio", "titulo"), [
            (self.id_historico, "origem/treino", "título histórico"),
            ("a" * 40, "origem/paridade", "docs: Alteração distinta 1-31"),
        ])

    @staticmethod
    def gravar(path, colunas, linhas):
        with path.open("w", encoding="utf-8", newline="") as arq:
            writer = csv.writer(arq)
            writer.writerow(colunas)
            writer.writerows(linhas)

    def preparar(self, repos=None, **opcoes):
        return preparar_v12(repos or self.repos, historicos=[self.inventario],
                            saida=self.saida, quantidade=150, **opcoes)

    def revisao(self, grupos=True):
        with (self.saida / "amostra.csv").open(encoding="utf-8") as arq:
            ids = [r["id"] for r in csv.DictReader(arq)]
        linhas = []
        for i, uid in enumerate(ids):
            classe = CLASSES[(i // 5) % 5] if grupos else "fix"
            if i in (148, 149):
                classe = ROTULOS[-(i - 147)]
            linhas.append((uid, classe, "en" if (i // 25) % 2 else "pt", "Revisão simulada em teste"))
        return linhas

    def test_prepara_amostra_cega_e_deterministica_com_exclusoes(self):
        m = self.preparar()
        outra = preparar_v12(list(reversed(self.repos)), historicos=[self.inventario],
                             saida=self.pasta / "replica", quantidade=150)
        self.assertEqual(m, outra)
        amostra = (self.saida / "amostra.csv").read_text(encoding="utf-8")
        self.assertEqual(amostra.splitlines()[0], "id,repositorio,titulo")
        self.assertNotIn(self.id_historico, amostra)
        self.assertNotIn("Alteração distinta 1-31", amostra)
        exclusoes = (self.saida / "exclusoes.csv").read_text(encoding="utf-8")
        self.assertIn(self.id_historico + ",origem/treino,", exclusoes)
        self.assertNotIn("título histórico", exclusoes)
        r = validar_v12(self.saida)
        self.assertFalse(r["gabarito_validado"])
        self.assertEqual((r["faltam"], r["elegiveis"]), (150, 0))
        with self.assertRaisesRegex(ValueError, "histórico"):
            avaliar(saida=self.saida)
        with self.assertRaisesRegex(ValueError, "revisão cega"):
            rotular(saida=self.saida)

    def test_rejeita_origem_conhecida_e_inventario_ausente(self):
        self.gravar(self.inventario, ("id", "repositorio", "titulo"), [
            ("a" * 40, "git@example.org:outro/projeto-0.git", "mensagem antiga"),
        ])
        with self.assertRaisesRegex(ValueError, "possivelmente visto"):
            self.preparar()
        with self.assertRaisesRegex(ValueError, "inventário histórico"):
            preparar_v12(self.repos, historicos=[], saida=self.saida, quantidade=150)
        self.assertFalse(self.saida.exists())

    def test_validacao_exige_revisao_e_suporte_por_classe_e_idioma(self):
        self.preparar()
        colunas = ("id", "categoria", "idioma", "justificativa")
        caminho = self.saida / "rotulos.csv"
        self.gravar(caminho, colunas, self.revisao(grupos=False))
        r = validar_v12(self.saida)
        self.assertIn("suporte_insuficiente_nas_cinco_classes", r["bloqueios"])
        self.assertFalse(r["por_idioma"]["pt"]["suporte_para_metricas"])
        linhas = self.revisao()
        self.gravar(caminho, colunas, linhas)
        r = validar_v12(self.saida)
        self.assertTrue(r["gabarito_validado"])
        self.assertEqual((r["faltam"], r["elegiveis"]), (0, 148))
        self.assertEqual(r["categorias"]["indeterminado"], 1)
        self.assertEqual(r["categorias"]["fora_escopo"], 1)
        for idioma in ("pt", "en"):
            self.assertTrue(r["por_idioma"][idioma]["suporte_para_metricas"])
        self.assertEqual(len(r["gabarito_sha256"]), 64)

    def test_validacao_rejeita_adulteracao_e_coluna_de_previsao(self):
        self.preparar()
        caminho = self.saida / "rotulos.csv"
        colunas = ("id", "categoria", "idioma", "justificativa")
        self.gravar(caminho, (*colunas, "previsao"), [])
        with self.assertRaisesRegex(ValueError, "revisão cega"):
            validar_v12(self.saida)
        r = self.revisao()[0]
        self.gravar(caminho, colunas, [(*r[:3], "")])
        with self.assertRaisesRegex(ValueError, "justificativa"):
            validar_v12(self.saida)
        self.gravar(caminho, colunas, [r, r])
        with self.assertRaisesRegex(ValueError, "duplicado"):
            validar_v12(self.saida)
        (self.saida / "exclusoes.csv").write_text("alterado", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exclusões alterado"):
            validar_v12(self.saida)
        (self.saida / "amostra.csv").write_text("alterado", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Amostra mudou"):
            validar_v12(self.saida)


if __name__ == "__main__":
    unittest.main()
