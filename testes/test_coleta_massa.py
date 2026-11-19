"""Testes locais sem rede para o coletor em massa."""
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from commitx.coleta_massa import (
    abrir_banco, dividir_mensagem, exportar_csv, importar_git, importar_hf, ler_hf_jsonl, registrar,
)


class TestarColetaMassa(unittest.TestCase):
    def test_dividir_mensagem(self):
        self.assertEqual(
            dividir_mensagem("fix: corrigir tela\n\nCorrige a paginação\n"),
            ("fix: corrigir tela", "Corrige a paginação"),
        )
        self.assertEqual(dividir_mensagem("", "Título"), ("Título", ""))

    def test_leitor_jsonl_sem_script(self):
        linhas = [
            {"repos": "org/repo", "commit": "abc", "message": "fix: corrigir"},
            {"repos": "org/outro", "commit": "def", "message": "docs: documentar"},
        ]
        class Resposta(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        def abrir(requisicao, timeout):
            self.assertEqual(timeout, 90)
            self.assertIn("/data/python/data.jsonl", requisicao.full_url)
            return Resposta(
                b"\\n" + b"\\n".join(
                    json.dumps(item).encode("utf-8") for item in linhas
                ) + b"\\n"
            )

        self.assertEqual(list(ler_hf_jsonl("python", abridor=abrir)), linhas)

    def test_hf_deduplicacao_exportacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            with abrir_banco(pasta / "commits.sqlite3") as db:
                linhas = [
                    {"repos": "org/repo", "commit": "a1", "subject": "fix: corrigir login",
                     "message": "fix: corrigir login\n\nSessão expirava", "lang": "python"},
                    {"repos": "org/repo", "commit": "a1", "subject": "fix: corrigir login",
                     "message": "fix: corrigir login", "lang": "java"},
                    {"repos": "org/outro", "commit": "a1", "subject": "docs: criar guia",
                     "message": "docs: criar guia", "lang": "python"},
                ]

                def carregar(linguagem):
                    self.assertEqual(linguagem, "python")
                    return iter(linhas)

                self.assertEqual(
                    importar_hf(db, limite=10, splits=["python"], carregador=carregar),
                    (2, 3),
                )
                self.assertEqual(
                    importar_hf(db, limite=10, splits=["python"], carregador=carregar)[0],
                    0,
                )
                destino = pasta / "dados.csv"
                self.assertEqual(exportar_csv(db, destino), 2)
                with destino.open(encoding="utf-8") as arq:
                    registros = list(csv.DictReader(arq))
                self.assertEqual({r["categoria"] for r in registros}, {""})
                self.assertEqual({r["tipo_declarado"] for r in registros}, {"fix", "docs"})
                with self.assertRaises(FileExistsError):
                    exportar_csv(db, destino)

    def test_varios_repositorios_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            repositorios = []
            for nome in ("repo1", "repo2"):
                repo = raiz / nome
                repo.mkdir()
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                subprocess.run(
                    ["git", "-C", str(repo), "config", "user.email", "teste@local"],
                    check=True,
                )
                subprocess.run(
                    ["git", "-C", str(repo), "config", "user.name", "Teste"],
                    check=True,
                )
                (repo / "a.txt").write_text("conteúdo", encoding="utf-8")
                subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
                subprocess.run(
                    ["git", "-C", str(repo), "commit", "-qm", "fix: corrigir login"],
                    check=True,
                )
                repositorios.append(repo)
            with abrir_banco(raiz / "commits.sqlite3") as db:
                self.assertEqual(
                    importar_git(db, repositorios=repositorios, limite=10), (2, 2)
                )
                self.assertEqual(
                    importar_git(db, repositorios=repositorios, limite=10), (0, 2)
                )

    def test_descartar_registros_invalidos(self):
        with tempfile.TemporaryDirectory() as tmp:
            with abrir_banco(Path(tmp) / "commits.sqlite3") as db:
                self.assertFalse(registrar(
                    db, repositorio="", sha="abc", mensagem="fix: corrigir", fonte="git",
                ))
                self.assertFalse(registrar(
                    db, repositorio="org/repo", sha="abc", mensagem="", fonte="git",
                ))
                self.assertTrue(registrar(
                    db, repositorio="org/repo", sha="abc", mensagem="fix: corrigir", fonte="git",
                ))
                self.assertFalse(registrar(
                    db, repositorio="org/repo", sha="abc", mensagem="fix: corrigir", fonte="git",
                ))


if __name__ == "__main__":
    unittest.main()
