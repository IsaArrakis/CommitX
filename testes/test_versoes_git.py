"""Testes de leitura de objetos em repositórios Git temporários."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from commitx.versoes_git import OrcamentoLeitura, ler_versoes_git


class TestVersoesGit(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        self.git("init", "-q", "-b", "principal")
        self.git("config", "user.name", "Teste CommitX")
        self.git("config", "user.email", "teste@example.com")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.raiz), *args], check=True, capture_output=True,
            text=True, env={"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1",
                            "GIT_CONFIG_GLOBAL": os.devnull},
        ).stdout.strip()

    def escrever(self, nome, conteudo):
        (self.raiz / nome).write_bytes(conteudo)

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "Alteração de teste")
        return self.git("rev-parse", "HEAD")

    def ler(self, **limites):
        return ler_versoes_git(self.raiz, self.git("rev-parse", "HEAD"), OrcamentoLeitura(**limites))

    def test_funcao_modificada(self):
        antes, depois = b"def dobro(n):\n    return n\n", b"def dobro(n):\n    return 2 * n\n"
        self.escrever("calculo.py", antes)
        pai = self.commit()
        self.escrever("calculo.py", depois)
        sha = self.commit()
        resultado = self.ler()
        self.assertEqual((resultado["commit"], resultado["comparado_com"]), (sha, pai))
        self.assertEqual(resultado["cobertura"], "completa")
        self.assertEqual(resultado["arquivos"], [{
            "caminho": "calculo.py", "status": "modificado", "cobertura": "completa",
            "anterior": {"conteudo": antes.decode(), "tamanho_bytes": len(antes), "motivo": None},
            "posterior": {"conteudo": depois.decode(), "tamanho_bytes": len(depois), "motivo": None},
        }])

    def test_adicao_e_remocao_sem_inferir_renome(self):
        self.escrever("antigo.py", b"valor = 1\n")
        self.commit()
        self.git("config", "diff.renames", "true")
        self.git("mv", "antigo.py", "novo.pyi")
        self.commit()
        arquivos = {a["caminho"]: a for a in self.ler()["arquivos"]}
        self.assertEqual(set(arquivos), {"antigo.py", "novo.pyi"})
        removido, adicionado = arquivos["antigo.py"], arquivos["novo.pyi"]
        self.assertEqual(removido["status"], "removido")
        self.assertEqual(removido["anterior"]["conteudo"], "valor = 1\n")
        self.assertEqual(removido["posterior"]["motivo"], "nao_aplicavel")
        self.assertEqual(adicionado["status"], "adicionado")
        self.assertEqual(adicionado["anterior"]["motivo"], "nao_aplicavel")
        self.assertEqual(adicionado["posterior"]["conteudo"], "valor = 1\n")
        self.assertEqual({a["cobertura"] for a in arquivos.values()}, {"completa"})

    def test_raiz_e_nomes_incomuns(self):
        nomes = ["com espaço.py", "edição.pyi", "com\ttab.py", "com\nlinha.py"]
        for nome in nomes:
            self.escrever(nome, b"# arquivo\n")
        self.escrever("IGNORAR.md", b"# texto\n")
        self.commit()
        resultado = self.ler()
        self.assertIsNone(resultado["comparado_com"])
        self.assertEqual(resultado["cobertura"], "completa")
        self.assertCountEqual([a["caminho"] for a in resultado["arquivos"]], nomes)
        for arquivo in resultado["arquivos"]:
            self.assertEqual(arquivo["status"], "adicionado")
            self.assertEqual(arquivo["anterior"]["motivo"], "nao_aplicavel")
            self.assertEqual(arquivo["posterior"]["conteudo"], "# arquivo\n")

    def test_merge_usa_primeiro_pai(self):
        self.escrever("raiz.py", b"pass\n")
        self.commit()
        self.git("switch", "-qc", "secundario")
        self.escrever("secundario.py", b"secundario = True\n")
        self.commit()
        self.git("switch", "-q", "principal")
        self.escrever("principal.py", b"principal = True\n")
        pai = self.commit()
        self.git("merge", "--no-ff", "-qm", "Merge de teste", "secundario")
        resultado = self.ler()
        self.assertEqual(resultado["comparado_com"], pai)
        self.assertEqual([a["caminho"] for a in resultado["arquivos"]], ["secundario.py"])

    def test_clone_raso_com_pai_ausente_nao_parece_commit_raiz(self):
        self.escrever("a.py", b"a=1\n")
        pai = self.commit()
        self.escrever("a.py", b"a=2\n")
        sha = self.commit()
        # Simula a fronteira de um clone raso e remove seu objeto de pai.
        (self.raiz / ".git" / "shallow").write_text(sha + "\n", encoding="ascii")
        (self.raiz / ".git" / "objects" / pai[:2] / pai[2:]).unlink()
        resultado = self.ler()
        self.assertEqual(resultado["comparado_com"], pai)
        self.assertEqual(resultado["cobertura"], "indisponivel")
        self.assertEqual(resultado["limitacoes"], ["inventario_indisponivel"])

    def test_link_simbolico_python_nao_e_seguido(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo = Path(pasta) / "externo.py"
            alvo.write_text("segredo = True\n", encoding="utf-8")
            (self.raiz / "link.py").symlink_to(alvo)
            self.commit()
            posterior = self.ler()["arquivos"][0]["posterior"]
            self.assertEqual(posterior["motivo"], "tipo_nao_suportado")
            self.assertIsNone(posterior["conteudo"])

    def test_binario_utf8_invalido_e_objeto_ausente_preservam_outros_arquivos(self):
        for nome, dados in {
            "a.py": b"\x00bytes", "b.py": b"\xff", "c.py": b"objeto ausente", "d.py": b"pass\n",
        }.items():
            self.escrever(nome, dados)
        self.commit()
        blob = self.git("rev-parse", "HEAD:c.py")
        (self.raiz / ".git" / "objects" / blob[:2] / blob[2:]).unlink()

        resultado = self.ler()
        arquivos = {a["caminho"]: a["posterior"] for a in resultado["arquivos"]}
        self.assertEqual(resultado["cobertura"], "parcial")
        self.assertEqual(arquivos["a.py"]["motivo"], "binario")
        self.assertEqual(arquivos["b.py"]["motivo"], "utf8_invalido")
        self.assertEqual(arquivos["c.py"]["motivo"], "objeto_indisponivel")
        self.assertEqual(arquivos["d.py"]["conteudo"], "pass\n")

    def test_limite_por_arquivo_soma_versoes_e_mantem_os_demais(self):
        self.escrever("a.py", b"a=1\n")
        self.commit()
        self.escrever("a.py", b"a=2\n")
        self.escrever("b.py", b"b=1\n")
        self.commit()
        resultado = self.ler(max_bytes_arquivo=5)
        a, b = resultado["arquivos"]
        self.assertEqual(a["anterior"]["conteudo"], "a=1\n")
        self.assertEqual(a["posterior"], {
            "conteudo": None, "tamanho_bytes": 4, "motivo": "limite_bytes_arquivo",
        })
        self.assertEqual(b["posterior"]["conteudo"], "b=1\n")
        self.assertEqual(resultado["cobertura"], "parcial")

    def test_limites_de_quantidade_total_e_tempo(self):
        self.escrever("a.py", b"a=1\n")
        self.escrever("b.py", b"b=1\n")
        self.commit()
        por_quantidade = self.ler(max_arquivos=1)
        self.assertEqual(len(por_quantidade["arquivos"]), 1)
        self.assertEqual(por_quantidade["limitacoes"], ["limite_arquivos"])
        por_total = self.ler(max_bytes_totais=4)
        self.assertEqual(por_total["arquivos"][1]["posterior"]["motivo"], "limite_bytes_totais")
        por_tempo = self.ler(segundos=0)
        self.assertEqual(por_tempo["cobertura"], "indisponivel")
        self.assertEqual(por_tempo["limitacoes"], ["limite_tempo"])

    def test_sha_invalido_inexistente_ou_de_blob(self):
        self.escrever("a.py", b"pass\n")
        self.commit()
        for sha in ("HEAD", "--help", "0" * 40, self.git("rev-parse", "HEAD:a.py")):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                ler_versoes_git(self.raiz, sha)

    def test_le_do_objeto_sem_executar_codigo_ou_modificar_repositorio(self):
        codigo = b"from pathlib import Path\nPath('sentinela').touch()\n"
        self.escrever("a.py", codigo)
        self.commit()
        self.escrever("a.py", "# conteúdo no índice\n".encode())
        self.git("add", "a.py")
        self.escrever("a.py", "# conteúdo no worktree\n".encode())
        self.escrever("nao_rastreado.txt", b"local\n")

        def snapshot():
            return {p.relative_to(self.raiz): p.read_bytes()
                    for p in self.raiz.rglob("*") if p.is_file()}

        antes = snapshot()
        self.assertEqual(self.ler()["arquivos"][0]["posterior"]["conteudo"], codigo.decode())
        self.assertEqual(snapshot(), antes)
