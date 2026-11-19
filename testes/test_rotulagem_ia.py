"""Testes offline da rotulagem automática, sem precisar instalar Ollama."""
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from commitx.rotulagem_ia import classificar, status, exportar, validar_resposta


class TestRotulagemIA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.entrada = self.raiz / "commits.csv"
        self.banco = self.raiz / "ia.sqlite3"
        self.humanos = self.raiz / "humanos.sqlite3"
        with self.entrada.open("w", newline="", encoding="utf-8") as arq:
            w = csv.DictWriter(arq, fieldnames=["id", "titulo", "descricao", "particao"])
            w.writeheader()
            w.writerows([
                {"id": "a", "titulo": "docs: guia", "descricao": "", "particao": "treino"},
                {"id": "b", "titulo": "feat: busca", "descricao": "", "particao": "validacao"},
                {"id": "c", "titulo": "fix: login", "descricao": "", "particao": "teste"},
                {"id": "d", "titulo": "fix: paginação", "descricao": "", "particao": "treino"},
                {"id": "e", "titulo": "test: criar testes", "descricao": "", "particao": "treino"},
            ])
        with sqlite3.connect(self.humanos) as con:
            con.execute("CREATE TABLE avaliacoes (id TEXT PRIMARY KEY)")
            con.execute("INSERT INTO avaliacoes VALUES ('d')")
        self.chamadas = []
        def pred(titulo, descricao, modelo):
            self.chamadas.append(titulo)
            return ("docs", "parcial", "media", "hipótese")
        self.pred = pred

    def test_so_treino_nao_humanos_e_sem_contaminar(self):
        resumo = classificar(self.entrada, self.banco, self.humanos,
                             limite=0, preditor=self.pred,
                             imprimir=lambda *_: None)
        self.assertEqual(resumo["sugeridos"], 2)
        self.assertEqual(len(self.chamadas), 2)
        with sqlite3.connect(self.banco) as con:
            ids = {r[0] for r in con.execute("SELECT id FROM rotulos_ia")}
            self.assertEqual(ids, {"a", "e"})
            self.assertEqual(con.execute("SELECT categoria_ia FROM rotulos_ia WHERE id='a'").fetchone()[0], "docs")
        with sqlite3.connect(self.humanos) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM avaliacoes").fetchone()[0], 1)

    def test_retomada_e_limite(self):
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        self.assertEqual(len(self.chamadas), 2)
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        self.assertEqual(len(self.chamadas), 2)

    def test_exportacao_nao_sobrescreve(self):
        classificar(self.entrada, self.banco, self.humanos,
                    limite=1, preditor=self.pred, imprimir=lambda *_: None)
        destino = self.raiz / "s.csv"
        exportar(self.banco, destino)
        with destino.open(encoding="utf-8") as arq:
            linhas = list(csv.DictReader(arq))
        self.assertEqual(linhas[0]["categoria_ia"], "docs")
        self.assertNotIn("categoria_humana", linhas[0])
        with self.assertRaises(FileExistsError):
            exportar(self.banco, destino)

    def test_falha_salva_erro_e_pode_retentar(self):
        def falha(*args):
            raise RuntimeError("Ollama indisponível")
        classificar(self.entrada, self.banco, self.humanos, limite=1,
                    preditor=falha, imprimir=lambda *_: None)
        self.assertEqual(status(self.banco)["status"]["erro"], 1)
        classificar(self.entrada, self.banco, self.humanos, limite=1,
                    retentar_erros=True, preditor=self.pred,
                    imprimir=lambda *_: None)
        self.assertEqual(status(self.banco)["status"]["prata"], 1)

    def test_normaliza_variacoes_e_rejeita_desconhecidos(self):
        self.assertEqual(
            validar_resposta({
                "categoria": "Bugfix", "clareza": "Clear",
                "confianca": "High", "justificativa": "correção"
            }),
            ("fix", "claro", "alta", "correção"),
        )
        self.assertEqual(
            validar_resposta({
                "categoria": "chore", "clareza": "partial",
                "confianca": "low", "justificativa": ""
            })[:3],
            ("fora_escopo", "parcial", "baixa"),
        )
        with self.assertRaisesRegex(ValueError, "categoria inválido"):
            validar_resposta({"categoria": "inventado", "clareza": "vago"})
        with self.assertRaisesRegex(ValueError, "clareza inválido"):
            validar_resposta({"categoria": "fix", "clareza": "ótimo"})

    def test_outro_e_indeterminado_nao_fora_escopo(self):
        for nome in ("outro", "other", "outros"):
            cat, cla, conf, motivo = validar_resposta({
                "categoria": nome, "clareza": "claro",
                "confianca": "alta", "justificativa": "sem tipo conhecido"
            })
            self.assertEqual((cat, cla, conf), ("indeterminado", "claro", "baixa"))
            self.assertIn("convertida em indeterminado", motivo)

    def test_ollama_recebe_esquema_com_categorias_permitidas(self):
        from unittest.mock import patch
        import io
        import json
        from commitx.rotulagem_ia import prever, CATEGORIAS, CLAREZAS

        pedidos = []
        class Resposta:
            def __enter__(self):
                return io.BytesIO(json.dumps({
                    "message": {"content": json.dumps({
                        "categoria": "fix", "clareza": "claro",
                        "confianca": "alta", "justificativa": "bug corrigido"
                    })}
                }).encode("utf-8"))
            def __exit__(self, *args):
                return False
        def simular(pedido, timeout):
            pedidos.append(json.loads(pedido.data))
            return Resposta()

        with patch("commitx.rotulagem_ia.urlopen", side_effect=simular):
            prever("fix: corrigir", "", "modelo-teste")
        self.assertEqual(
            pedidos[0]["format"]["properties"]["categoria"]["enum"],
            list(CATEGORIAS),
        )
        self.assertEqual(
            pedidos[0]["format"]["properties"]["clareza"]["enum"],
            list(CLAREZAS),
        )

    def test_retentativa_json_ollama_sem_rede(self):
        from unittest.mock import patch
        import io
        import json
        from commitx.rotulagem_ia import prever

        class Resposta:
            def __init__(self, conteudo):
                self.raw = io.BytesIO(json.dumps({
                    "message": {"content": json.dumps(conteudo)}
                }).encode("utf-8"))
            def __enter__(self):
                return self.raw
            def __exit__(self, *args):
                self.raw.close()

        respostas = [
            Resposta({"categoria": "nao_existe", "clareza": "clear"}),
            Resposta({"categoria": "bugfix", "clareza": "clear",
                     "confianca": "high", "justificativa": "ok"}),
        ]
        with patch("commitx.rotulagem_ia.urlopen", side_effect=respostas) as requisicoes:
            resultado = prever("fix: resolver erro", "", "modelo-teste")
        self.assertEqual(resultado[:3], ("fix", "claro", "alta"))
        self.assertEqual(requisicoes.call_count, 2)

    def test_rubrica_nao_exige_corpo_e_contem_exemplos_auditados(self):
        from commitx.rotulagem_ia import instrucoes
        prompt = instrucoes()
        self.assertIn("NÃO penalize automaticamente mensagens sem corpo", prompt)
        self.assertIn("Add a __str__ for Tile", prompt)
        self.assertIn("Cover this exception with a test", prompt)
        self.assertIn("prefixo", prompt)

    def test_detecta_justificativas_suspeitas_sem_corpo(self):
        from commitx.rotulagem_ia import depende_apenas_da_ausencia_de_corpo
        self.assertTrue(depende_apenas_da_ausencia_de_corpo(
            ("fix", "parcial", "baixa",
             "O corpo está vazio, o que dificulta avaliar a mudança."), ""
        ))
        self.assertFalse(depende_apenas_da_ausencia_de_corpo(
            ("feat", "parcial", "baixa", "Título não identifica o alvo"), ""
        ))
        self.assertFalse(depende_apenas_da_ausencia_de_corpo(
            ("feat", "claro", "alta", "Corpo vazio"), ""
        ))
        self.assertFalse(depende_apenas_da_ausencia_de_corpo(
            ("feat", "parcial", "baixa", "Corpo vazio"), "Texto existente"
        ))

    def test_segunda_avaliacao_quando_justificativa_cita_corpo_ausente(self):
        from unittest.mock import patch
        from commitx.rotulagem_ia import prever

        previsoes = [
            ("feat", "parcial", "baixa", "O corpo está vazio"),
            ("feat", "claro", "media", "Título identifica ação e alvo"),
        ]
        with patch("commitx.rotulagem_ia._solicitar_ollama",
                   side_effect=previsoes) as solicitacoes:
            resultado = prever("Add a __str__ for Tile", "", "modelo-teste")
        self.assertEqual(resultado[:2], ("feat", "claro"))
        self.assertEqual(solicitacoes.call_count, 2)
        self.assertIn(
            "SEGUNDA AVALIAÇÃO",
            solicitacoes.call_args.args[0]["messages"][0]["content"],
        )

    def test_segunda_avaliacao_nao_promove_automaticamente(self):
        from unittest.mock import patch
        from commitx.rotulagem_ia import prever

        previsoes = [
            ("test", "parcial", "baixa", "Corpo vazio"),
            ("test", "vago", "media", "A exceção não está identificada"),
        ]
        with patch("commitx.rotulagem_ia._solicitar_ollama",
                   side_effect=previsoes) as solicitacoes:
            resultado = prever("Cover this exception with a test", "",
                              "modelo-teste")
        self.assertEqual(resultado[:2], ("test", "vago"))
        self.assertEqual(solicitacoes.call_count, 2)

    def test_erro_na_segunda_avaliacao_preserva_rotulo_e_alerta(self):
        from unittest.mock import patch
        from commitx.rotulagem_ia import prever

        respostas = [
            ("docs", "parcial", "media", "Descrição vazia"),
            RuntimeError("Falha do Ollama"),
        ]
        with patch("commitx.rotulagem_ia._solicitar_ollama",
                   side_effect=respostas):
            resultado = prever("Add copyright and license information", "",
                              "modelo-teste")
        self.assertEqual(resultado[:3], ("docs", "parcial", "baixa"))
        self.assertIn("Revisar clareza", resultado[3])


    def test_auditoria_v3_titulo_presente_nao_indetermina_clareza(self):
        from unittest.mock import patch
        from commitx.rotulagem_ia import prever

        with patch("commitx.rotulagem_ia._solicitar_ollama",
                   side_effect=[
                       ("indeterminado", "indeterminado", "baixa",
                        "O título e o corpo estão vazios"),
                       ("fix", "parcial", "media",
                        "Menciona um erro de bool, mas sem mecanismo"),
                   ]) as chamadas:
            resultado = prever("Fix bool setting dump issue.", "", "modelo")
        self.assertEqual(resultado[:2], ("fix", "parcial"))
        self.assertEqual(chamadas.call_count, 2)
        self.assertNotIn(
            "indeterminado",
            chamadas.call_args.args[0]["format"]["properties"]["clareza"]["enum"],
        )

    def test_titulo_vazio_pode_manter_indeterminado(self):
        from unittest.mock import patch
        from commitx.rotulagem_ia import prever, CLAREZAS
        with patch("commitx.rotulagem_ia._solicitar_ollama",
                   return_value=("indeterminado", "indeterminado", "baixa",
                                 "Sem texto legível")) as chamadas:
            resultado = prever("", "", "modelo")
        self.assertEqual(resultado[1], "indeterminado")
        self.assertEqual(chamadas.call_count, 1)
        self.assertEqual(
            chamadas.call_args.args[0]["format"]["properties"]["clareza"]["enum"],
            list(CLAREZAS),
        )

    def test_filtrar_apenas_ids_auditados_sem_vazar_validacao(self):
        from commitx.rotulagem_ia import classificar
        filtro = self.raiz / "ids.csv"
        with filtro.open("w", encoding="utf-8", newline="") as arq:
            escritor = csv.writer(arq)
            escritor.writerow(["id"])
            escritor.writerows([["e"], ["b"], ["c"]])
        resumo = classificar(
            self.entrada, self.banco, self.humanos,
            preditor=self.pred, ids_csv=filtro, limite=0,
            imprimir=lambda *_: None,
        )
        self.assertEqual(resumo.get("sugeridos"), 1)
        self.assertEqual(self.chamadas, ["test: criar testes"])


if __name__ == "__main__":
    unittest.main()
