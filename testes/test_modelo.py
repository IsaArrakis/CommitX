"""Verifica separação de dados e comportamento, sem exigir métricas arbitrárias."""

import json
import unittest
from unittest.mock import patch

from commitx.dados import CLASSES
from commitx.modelo import avaliar, novo_modelo, sugerir, treinar


def exemplos(agrupados=True):
    dados = []
    verbos = ["corrigir falha", "adicionar recurso", "documentar guia", "extrair função", "testar resposta"]
    for grupo in range(2):
        for numero, categoria in enumerate(CLASSES):
            for variante in range(2):
                identificador = f"{categoria}_{grupo}_{variante}"
                # Token exclusivo permite verificar se o vocabulário viu dados do teste.
                exclusivo = "exclusivo" + chr(97 + len(dados)) * 5
                titulo = f"{verbos[numero]} {exclusivo}"
                dados.append({
                    "id": identificador, "titulo": titulo, "descricao": "",
                    "texto": titulo, "categoria": categoria,
                    "grupo": f"cenario_{grupo}" if agrupados else identificador,
                    "origem": "sintetico_teste",
                })
    return dados


class AvaliacaoTests(unittest.TestCase):
    def test_grupos_isolados_mesmos_folds_e_uma_previsao_por_linha(self):
        dados = exemplos()
        relatorio = avaliar(dados, folds=2)
        por_id = {linha["id"]: linha for linha in dados}
        vistos = []
        for fold in relatorio["folds"]:
            treino, teste = set(fold["ids_treino"]), set(fold["ids_teste"])
            self.assertFalse(treino & teste)
            self.assertFalse(
                {por_id[i]["grupo"] for i in treino} & {por_id[i]["grupo"] for i in teste}
            )
            vistos.extend(teste)
        self.assertCountEqual(vistos, por_id)
        self.assertEqual(len(vistos), len(set(vistos)))
        self.assertEqual(relatorio["metadados"]["estrategia"], "StratifiedGroupKFold")
        for linha in relatorio["previsoes"]:
            self.assertEqual(set(linha["por_modelo"]), {"palavras", "misto", "maioria"})
            self.assertTrue(all(valor in CLASSES for valor in linha["por_modelo"].values()))
        json.dumps(relatorio, ensure_ascii=False, allow_nan=False)

    def test_tfidf_nao_aprende_tokens_exclusivos_do_teste(self):
        dados, modelos = exemplos(), []

        def registrar(tipo="misto"):
            modelo = novo_modelo(tipo)
            modelos.append((tipo, modelo))
            return modelo

        with patch("commitx.modelo.novo_modelo", side_effect=registrar):
            relatorio = avaliar(dados, folds=2)
        por_id = {linha["id"]: linha for linha in dados}
        for numero, fold in enumerate(relatorio["folds"]):
            for tipo, modelo in modelos[numero * 2:numero * 2 + 2]:
                vetor = modelo.named_steps["tfidf"]
                if tipo == "misto":
                    vetor = dict(vetor.transformer_list)["palavras"]
                for identificador in fold["ids_teste"]:
                    exclusivo = por_id[identificador]["texto"].split()[-1]
                    self.assertNotIn(exclusivo, vetor.vocabulary_)
                    if tipo == "misto":
                        caracteres = dict(modelo.named_steps["tfidf"].transformer_list)["caracteres"]
                        self.assertNotIn(exclusivo[-5:], caracteres.vocabulary_)
                for identificador in fold["ids_treino"]:
                    exclusivo = por_id[identificador]["texto"].split()[-1]
                    self.assertIn(exclusivo, vetor.vocabulary_)

    def test_grupos_unitarios_usam_estratificacao_simples(self):
        relatorio = avaliar(exemplos(agrupados=False), folds=2)
        self.assertEqual(relatorio["metadados"]["estrategia"], "StratifiedKFold")

    def test_grupos_insuficientes_impedem_avaliacao(self):
        with self.assertRaisesRegex(ValueError, "grupos distintos"):
            avaliar(exemplos(), folds=3)

    def test_ids_duplicados_impedem_avaliacao(self):
        dados = exemplos()
        dados[1]["id"] = dados[0]["id"]
        with self.assertRaisesRegex(ValueError, "id único"):
            avaliar(dados, folds=2)


class SugestaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modelo = treinar(exemplos(), tipo="palavras")

    def test_abstencao_fora_do_vocabulario(self):
        resultado = sugerir(self.modelo, "zzzzzzzz qqqqqqqq")
        self.assertIsNone(resultado["categoria_sugerida"])
        self.assertTrue(any("Nenhum termo" in aviso for aviso in resultado["avisos"]))

    def test_tipo_fora_do_escopo_nao_forca_categoria(self):
        resultado = sugerir(self.modelo, "ci: adicionar recurso")
        self.assertIsNone(resultado["categoria_sugerida"])
        self.assertTrue(any("fora das classes" in aviso for aviso in resultado["avisos"]))

    def test_titulo_vazio_nao_e_classificado(self):
        with self.assertRaisesRegex(ValueError, "título"):
            sugerir(self.modelo, "  ")


if __name__ == "__main__":
    unittest.main()
