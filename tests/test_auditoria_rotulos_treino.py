"""Testes sem rede para auditoria direcionada do conjunto de treino."""
import csv
import subprocess
import tempfile
import unittest
from pathlib import Path

from commitx.auditoria_rotulos_treino import (
    auditar, escolher, ler_candidatos, sinal_caminhos,
)


class TestAuditoriaRotulosTreino(unittest.TestCase):
    def test_sinais_sao_indicativos(self):
        self.assertEqual(sinal_caminhos(["docs/intro.rst"]),
                         "somente_arquivos_documentacao")
        self.assertEqual(sinal_caminhos(["docs/intro.md", "src/app.py"]),
                         "documentacao_e_outros_arquivos")
        self.assertEqual(sinal_caminhos(["src/app.py"]),
                         "sem_caminhos_tipicos_documentacao")
        self.assertEqual(sinal_caminhos([]),
                         "sem_evidencia_de_arquivos")

    def test_selecao_balanceada_com_diversidade(self):
        registros = []
        for categoria in ("docs", "refactor"):
            for i in range(6):
                registros.append({
                    "id": f"{categoria}-{i}",
                    "titulo": f"{categoria} modificacao {i}",
                    "repositorios": f"org/repo-{i}",
                    "rotulo_registrado": categoria,
                    "erros_modelos": "2",
                })
        selecionados = escolher(registros, {}, 8)
        self.assertEqual(len(selecionados), 8)
        self.assertEqual(sum(x["rotulo_registrado"] == "docs"
                             for x in selecionados), 4)
        self.assertEqual(sum(x["rotulo_registrado"] == "refactor"
                             for x in selecionados), 4)

    def test_sem_clones_nao_inventa_evidencia_nem_rotulo(self):
        campos = ("id", "titulo", "repositorios", "rotulo_registrado",
                  "original", "palavras_caracteres", "erros_modelos")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            amostra = root / "candidatos.csv"
            rows = []
            for categoria in ("docs", "refactor"):
                for i in range(3):
                    rows.append({
                        "id": f"exemplo-{categoria}-{i}",
                        "titulo": f"{categoria} titulo {i}",
                        "repositorios": "org/repo",
                        "rotulo_registrado": categoria,
                        "original": "fix",
                        "palavras_caracteres": "feat",
                        "erros_modelos": "2",
                    })
            with amostra.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=campos)
                w.writeheader()
                w.writerows(rows)
            destino = root / "auditoria"
            resumo = auditar(amostra, root / "repos", destino, 4)
            self.assertEqual(resumo["total"], 4)
            self.assertEqual(resumo["com_contexto_git_local"], 0)
            with (destino / "casos_para_auditoria.csv").open(
                    encoding="utf-8", newline="") as f:
                saida = list(csv.DictReader(f))
            self.assertTrue(all(not r["decisao_humana"] for r in saida))
            self.assertTrue(all(r["contexto_git"] == "nao_disponivel" for r in saida))
            self.assertTrue((destino / "evidencias_git.md").exists())
            with self.assertRaises(FileExistsError):
                auditar(amostra, root / "repos", destino, 4)

    def test_repo_git_local_real_fornece_arquivos(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repos" / "projeto"
            repo.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "docs").mkdir()
            (repo / "docs" / "intro.md").write_text("texto\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Teste",
                            "-c", "user.email=teste@example.invalid",
                            "commit", "-qm", "docs intro"], check=True)
            sha = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            campos = ("id", "titulo", "repositorios", "rotulo_registrado",
                      "original", "palavras_caracteres", "erros_modelos")
            amostra = root / "amostra.csv"
            with amostra.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=campos)
                writer.writeheader()
                writer.writerow(dict(zip(campos, (
                    sha, "docs intro", "org/projeto", "docs", "fix", "feat", "2"))))
                writer.writerow(dict(zip(campos, (
                    "segundo", "refactor intro", "org/outro", "refactor",
                    "fix", "feat", "2"))))
            destino = root / "auditoria"
            resumo = auditar(amostra, root / "repos", destino, quantidade=2)
            self.assertEqual(resumo["com_contexto_git_local"], 1)
            self.assertIn("docs/intro.md",
                          (destino / "evidencias_git.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
