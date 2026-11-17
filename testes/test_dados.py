"""Verifica validação do CSV e coleta real em um repositório temporário."""

import csv
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from commitx.dados import CAMPOS, CLASSES, carregar_dados, coletar_git


class TestDadosCSV(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.pasta = Path(self.temporario.name)

    def escrever(self, linhas, campos=CAMPOS, encoding="utf-8"):
        caminho = self.pasta / "dados.csv"
        with caminho.open("w", encoding=encoding, newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(linhas)
        return caminho

    def exemplos(self):
        titulos = [
            "fix(login): corrigir sessão expirada",
            "feat(busca): permitir filtro por preço",
            "docs: explicar instalação no manual",
            "refactor: extrair validação sem mudar comportamento",
            "test: verificar cadastro com email inválido",
        ]
        return [dict(id=str(i), titulo=titulo, descricao="", categoria=categoria,
                     grupo=str(i), origem="sintetico_didatico")
                for i, (titulo, categoria) in enumerate(zip(titulos, CLASSES))]

    def test_aceita_bom_e_prepara_texto_sem_prefixo(self):
        dados = carregar_dados(self.escrever(self.exemplos(), encoding="utf-8-sig"))
        self.assertEqual(len(dados), 5)
        self.assertNotIn("fix(login):", dados[0]["texto"])
        self.assertIn("sessão expirada", dados[0]["texto"])

    def test_informa_coluna_ausente(self):
        with self.assertRaisesRegex(ValueError, "colunas obrigatórias.*categoria"):
            carregar_dados(self.escrever([], [c for c in CAMPOS if c != "categoria"]))

    def test_rejeita_base_vazia(self):
        with self.assertRaisesRegex(ValueError, "base está vazia"):
            carregar_dados(self.escrever([]))

    def test_nao_deduz_rotulo_do_prefixo(self):
        linhas = self.exemplos()
        linhas[0]["categoria"] = ""
        with self.assertRaisesRegex(ValueError, "Rotule.*manualmente.*não copie automaticamente"):
            carregar_dados(self.escrever(linhas))

    def test_rejeita_id_repetido(self):
        linhas = self.exemplos()
        linhas[1]["id"] = linhas[0]["id"]
        with self.assertRaisesRegex(ValueError, "id repetido"):
            carregar_dados(self.escrever(linhas))

    def test_rejeita_duplicata_com_prefixo_acento_e_espacos_diferentes(self):
        linhas = self.exemplos()
        linhas.append(dict(id="novo", titulo="  CORRIGIR   sessao expirada ",
                           descricao="", categoria="fix", grupo="novo", origem="manual"))
        with self.assertRaisesRegex(ValueError, "mensagem duplicada"):
            carregar_dados(self.escrever(linhas))

    def test_exige_cinco_classes(self):
        with self.assertRaisesRegex(ValueError, "Faltam exemplos de: test"):
            carregar_dados(self.escrever(self.exemplos()[:-1]))

    def test_rejeita_campos_obrigatorios_vazios(self):
        for campo in ("id", "titulo", "grupo", "origem"):
            with self.subTest(campo=campo):
                linhas = self.exemplos()
                linhas[0][campo] = " "
                with self.assertRaisesRegex(ValueError, f"campo '{campo}'.*vazio"):
                    carregar_dados(self.escrever(linhas))


@unittest.skipUnless(shutil.which("git"), "Git não instalado neste ambiente")
class TestColetaGit(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.pasta = Path(self.temporario.name)
        self.repo = self.pasta / "repositorio"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Teste local")
        self.git("config", "user.email", "teste@example.invalid")

    def git(self, *argumentos):
        return subprocess.run(["git", "-C", str(self.repo), *argumentos], check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout

    def test_exporta_corpo_completo_sem_criar_rotulo(self):
        titulo = "fix(admin): corrigir paginação"
        corpo = "A página repetia os primeiros usuários.\n\nAgora envia o número correto.\n\nRefs: #42"
        self.git("commit", "--allow-empty", "--quiet", "-m", titulo, "-m", corpo)
        saida = self.pasta / "coleta.csv"
        self.assertEqual(coletar_git(self.repo, saida), 1)
        with saida.open(encoding="utf-8", newline="") as arquivo:
            registros = list(csv.DictReader(arquivo))
        self.assertEqual(len(registros), 1)
        registro = registros[0]
        self.assertEqual(registro["titulo"], titulo)
        self.assertEqual(registro["descricao"], corpo + "\n")
        self.assertEqual(registro["categoria"], "")
        self.assertEqual(registro["tipo_declarado"], "fix")
        self.assertEqual(registro["id"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(registro["grupo"], registro["id"])
        self.assertEqual(registro["origem"], "git:repositorio")
        antes = saida.read_bytes()
        with self.assertRaisesRegex(ValueError, "já existe.*preservar os rótulos"):
            coletar_git(self.repo, saida)
        self.assertEqual(saida.read_bytes(), antes)

    def test_respeita_limite_e_titulo_sem_prefixo(self):
        for titulo in ("Primeira alteração", "Segunda alteração"):
            self.git("commit", "--allow-empty", "--quiet", "-m", titulo)
        saida = self.pasta / "coleta.csv"
        self.assertEqual(coletar_git(self.repo, saida, 1), 1)
        with saida.open(encoding="utf-8", newline="") as arquivo:
            registro = next(csv.DictReader(arquivo))
        self.assertEqual(registro["titulo"], "Segunda alteração")
        self.assertEqual(registro["tipo_declarado"], "")

    def test_preserva_descricao_sem_linha_em_branco(self):
        self.git("commit", "--allow-empty", "--quiet", "-m", "fix: corrigir paginação\nA segunda página repetia registros.")
        saida = self.pasta / "coleta.csv"
        coletar_git(self.repo, saida)
        with saida.open(encoding="utf-8", newline="") as arquivo:
            registro = next(csv.DictReader(arquivo))
        self.assertEqual(registro["titulo"], "fix: corrigir paginação")
        self.assertEqual(registro["descricao"], "A segunda página repetia registros.\n")

    def test_mensagem_vazia_nao_aborta_coleta(self):
        self.git("commit", "--allow-empty", "--allow-empty-message", "--quiet", "-m", "")
        self.git("commit", "--allow-empty", "--quiet", "-m", "docs: explicar instalação")
        saida = self.pasta / "coleta.csv"
        self.assertEqual(coletar_git(self.repo, saida), 2)
        with saida.open(encoding="utf-8", newline="") as arquivo:
            registros = list(csv.DictReader(arquivo))
        self.assertEqual(registros[1]["titulo"], "")
        self.assertEqual(registros[1]["descricao"], "")
        self.assertEqual(registros[1]["tipo_declarado"], "")
        self.assertEqual(registros[1]["categoria"], "")

    def test_rejeita_repositorio_sem_commits(self):
        with self.assertRaisesRegex(ValueError, "não tem commits"):
            coletar_git(self.repo, self.pasta / "coleta.csv")

    def test_rejeita_pasta_que_nao_e_git(self):
        with self.assertRaisesRegex(ValueError, "não é um repositório Git"):
            coletar_git(self.pasta, self.pasta / "coleta.csv")

    def test_rejeita_pasta_inexistente(self):
        with self.assertRaisesRegex(ValueError, "não existe"):
            coletar_git(self.pasta / "ausente", self.pasta / "coleta.csv")

    def test_rejeita_limites_invalidos(self):
        for limite in (0, 1001, -1, 1.5, True):
            with self.subTest(limite=limite):
                with self.assertRaisesRegex(ValueError, "inteiro entre 1 e 1000"):
                    coletar_git(self.repo, self.pasta / "coleta.csv", limite)


if __name__ == "__main__":
    unittest.main()
