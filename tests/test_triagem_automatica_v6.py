"""Testes offline de protecao de particoes, procedencia e retomada da triagem V6."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from commitx.revisao_git_v5 import preparar
from commitx.triagem_automatica_v6 import executar, _prompt, _selecionar_diversos


class TestTriagemV6(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.csv = self.root / "coleta.csv"
        self.plano = self.root / "plano.json"
        self.banco = self.root / "rotulos.sqlite3"
        self.saida = self.root / "saida"
        linhas = []
        for n in range(5):
            for k in range(12):
                # 40 hex e repositorios disjuntos. Testes nao dependem de rede ou Git real.
                linhas.append({
                    "id": f"{n * 100 + k:040x}",
                    "titulo": f"{'Fix bug' if k % 2 else 'Introduce capability'} {n} {k}",
                    "descricao": "changes code",
                    "repositorio": f"git:{self.root}/repos/r{n}",
                    "particao": "nao_atribuida",
                    "arquivos": "src/app.py | tests/test_app.py",
                    "arquivos_modificados": "2",
                    "linhas_adicionadas": "10",
                    "linhas_removidas": "2",
                })
        self.linhas = linhas
        with self.csv.open("w", encoding="utf-8", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(linhas[0]))
            wr.writeheader()
            wr.writerows(linhas)
        self.plan = preparar(entrada=self.csv, plano=self.plano, banco=self.banco)
        treino = [r for r in linhas if self.plan["repositorios"][r["repositorio"]] == "treino"]
        self.treino = treino
        with sqlite3.connect(self.banco) as db:
            db.executemany(
                "INSERT INTO avaliacoes(id,categoria,clareza) VALUES(?,?,?)",
                [(r["id"], "fix" if i % 2 else "feat", "claro")
                 for i, r in enumerate(treino[:24])]
            )

    def executar(self, **kwargs):
        return executar(
            entrada=self.csv, plano=self.plano, banco_v5=self.banco,
            saida=self.saida, **kwargs
        )

    def test_so_treino_sem_ollama(self):
        resultado = self.executar(sem_ollama=True)
        self.assertEqual(resultado["treino_v5_assistido_reutilizado"], 24)
        self.assertEqual(resultado["ollama_palpite_armazenado"], 0)
        with (self.saida / "triagem.csv").open(encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), len(self.treino) - 24)
        ids_treino = {r["id"] for r in self.treino}
        self.assertTrue(all(r["id"] in ids_treino for r in linhas))
        self.assertTrue(all(r["rotulo_humano"] == "" for r in linhas))
        self.assertTrue(all(r["proveniencia"] == "PALPITE_AUTOMATICO_NAO_VERIFICADO" for r in linhas))
        with sqlite3.connect(self.banco) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM avaliacoes").fetchone()[0], 24)

    def test_ollama_mock_retomada_e_divergencia(self):
        calls = []
        def cliente(row, modelo):
            calls.append(row["id"])
            return "docs", "parcial", True, "precisa inspecionar diff"
        primeiro = self.executar(quantidade_ollama=5, cliente=cliente)
        self.assertEqual(primeiro["ollama_palpite_armazenado"], 5)
        self.assertEqual(primeiro["ollama_novos_nesta_execucao"], 5)
        segundo = self.executar(quantidade_ollama=5, cliente=cliente)
        self.assertEqual(segundo["ollama_palpite_armazenado"], 10)
        self.assertEqual(len(set(calls)), 10)
        with (self.saida / "triagem.csv").open(encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(sum(bool(r["categoria_ollama"]) for r in linhas), 10)

    def test_erro_de_formato_nao_interrompe_lote_e_preserva_cache(self):
        chamadas = []
        def cliente(r, modelo):
            chamadas.append(r["id"])
            if len(chamadas) in (2, 4):
                raise ValueError("Resposta fora do vocabulario")
            return "fix", "claro", False, "sugestao automatica"
        resumo = self.executar(quantidade_ollama=6, cliente=cliente)
        self.assertEqual(resumo["ollama_novos_nesta_execucao"], 4)
        self.assertEqual(resumo["ollama_respostas_invalidas_puladas_nesta_execucao"], 2)
        self.assertEqual(resumo["ollama_respostas_invalidas_total"], 2)
        self.assertEqual(resumo["ollama_palpite_armazenado"], 4)
        self.assertEqual(len(chamadas), 6)
        with sqlite3.connect(self.saida / "palpites_v6.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM falhas").fetchone()[0], 2)
        def cliente_novo(r, modelo):
            chamadas.append(r["id"])
            return "docs", "parcial", False, "sugestao automatica"
        proxima = self.executar(quantidade_ollama=5, cliente=cliente_novo)
        self.assertEqual(proxima["ollama_palpite_armazenado"], 9)
        self.assertEqual(len(set(chamadas)), 11)

    def test_bloqueia_treino_com_rotulo_de_validacao(self):
        r = next(r for r in self.linhas if self.plan["repositorios"][r["repositorio"]] == "validacao")
        with sqlite3.connect(self.banco) as db:
            db.execute("INSERT INTO avaliacoes(id,categoria,clareza) VALUES(?,?,?)",
                       (r["id"], "fix", "claro"))
        with self.assertRaisesRegex(ValueError, "fora do treino"):
            self.executar(sem_ollama=True)

    def test_prompt_nao_assume_gabarito_de_prefixo(self):
        p = _prompt(self.treino[0])
        self.assertIn("Nao assuma", p)
        self.assertIn("indeterminado", p)
        self.assertIn("arquivos", p)


if __name__ == "__main__":
    unittest.main()
