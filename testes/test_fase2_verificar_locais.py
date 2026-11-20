"""Testes de disponibilidade local e preservacao das bases."""
import csv
import subprocess
from pathlib import Path
import tempfile
import unittest

from commitx.fase2_verificar_locais import verificar


class TestFase2VerificarLocais(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pasta = Path(temp.name)
        self.repo = self.pasta / "repo"
        self.repo.mkdir()

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(self.repo), *args],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
        self.git = git
        git("init", "-q")
        git("config", "user.name", "CommitX Testes")
        git("config", "user.email", "teste@example.com")
        (self.repo / "teste.txt").write_text("antes\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "feat: criar arquivo")
        (self.repo / "teste.txt").write_text("depois\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "fix: mudar linha")
        self.sha = git("rev-parse", "HEAD")
        self.entrada = self.pasta / "vinculos.csv"
        self.saida = self.pasta / "verificados.csv"
        self.resumo = self.pasta / "resumo.json"

    def _escrever(self, sha=None, repo=None, fonte="git:local"):
        with self.entrada.open("w", newline="", encoding="utf-8") as arq:
            escritor = csv.DictWriter(arq, fieldnames=[
                "id", "particao", "sha_original", "repositorio",
                "fonte", "integridade_id", "situacao_origem",
            ])
            escritor.writeheader()
            escritor.writerow({
                "id": "id1", "particao": "treino",
                "sha_original": sha or self.sha,
                "repositorio": repo or "git:" + str(self.repo),
                "fonte": fonte, "integridade_id": "valido",
                "situacao_origem": "git_local_pendente_verificacao",
            })

    def test_identifica_sha_local_e_estatisticas(self):
        self._escrever()
        rel = verificar(self.entrada, self.saida, self.resumo)
        self.assertEqual(rel["contagens"]["status_sha_verificado_local"], 1)
        self.assertEqual(rel["contagens"]["diff_estatisticas_disponiveis"], 1)
        with self.saida.open(encoding="utf-8") as arq:
            linha = next(csv.DictReader(arq))
        self.assertEqual(linha["arquivos_alterados"], "1")
        self.assertEqual(linha["linhas_adicionadas"], "1")
        self.assertEqual(linha["linhas_removidas"], "1")
        self.assertEqual(linha["particao"], "treino")

    def test_nao_confunde_commit_ausente_com_verificado(self):
        self._escrever(sha="b" * 40)
        rel = verificar(self.entrada, self.saida, self.resumo)
        self.assertEqual(rel["contagens"]["status_commit_indisponivel"], 1)
        with self.saida.open(encoding="utf-8") as arq:
            linha = next(csv.DictReader(arq))
        self.assertEqual(linha["arquivos_alterados"], "")

    def test_nao_busca_huggingface_na_rede(self):
        self._escrever(fonte="huggingface:bigcode/commitpackft")
        rel = verificar(self.entrada, self.saida, self.resumo)
        self.assertEqual(rel["contagens"]["status_nao_e_git_local"], 1)

    def test_nao_sobrescreve(self):
        self._escrever()
        self.saida.write_text("preserve", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            verificar(self.entrada, self.saida, self.resumo)
        self.assertEqual(self.saida.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
