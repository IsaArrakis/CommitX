"""Sugestões auditáveis para revisão humana de commits.

A categoria utiliza o classificador didático existente; não é gabarito.
Clareza usa regras e só passa a usar ML local quando houver rótulos suficientes.
"""
from collections import Counter
from pathlib import Path

from .dados import carregar_dados
from .escrita import revisar_escrita, texto_modelo
from .modelo import sugerir, treinar

BASE_DIDATICA = Path(__file__).resolve().parents[1] / "dados" / "commits_exemplo.csv"
CLAREZAS_TREINAVEIS = ("vago", "parcial", "claro")


class Sugestor:
    def __init__(self, amostra, db, base_didatica=BASE_DIDATICA):
        """Treina uma vez por sessão; nunca altera rótulos humanos."""
        self.modelo_categoria = treinar(carregar_dados(base_didatica), tipo="misto")
        self.modelo_clareza = None
        self.exemplos_clareza = 0

        humanos = {
            uid: rotulo
            for uid, rotulo in db.execute("SELECT id, clareza FROM avaliacoes")
        }
        textos, rotulos = [], []
        for registro in amostra:
            rotulo = humanos.get(registro["id"])
            if rotulo not in CLAREZAS_TREINAVEIS:
                continue
            try:
                texto = texto_modelo(
                    registro.get("titulo", ""), registro.get("descricao", "")
                )
            except (ValueError, TypeError):
                continue
            if texto:
                textos.append(texto)
                rotulos.append(rotulo)

        contagem = Counter(rotulos)
        self.exemplos_clareza = len(rotulos)
        # Para não aprender uma regra a partir de dois ou três exemplos.
        if len(rotulos) >= 30 and all(contagem[c] >= 5 for c in CLAREZAS_TREINAVEIS):
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline

            self.modelo_clareza = Pipeline([
                ("tfidf", TfidfVectorizer(
                    strip_accents="unicode", ngram_range=(1, 2),
                    sublinear_tf=True
                )),
                ("classificador", LogisticRegression(
                    class_weight="balanced", max_iter=1000, random_state=42
                )),
            ])
            self.modelo_clareza.fit(textos, rotulos)

    def analisar(self, titulo, descricao=""):
        """Retorna sugestões distintas; nenhuma é salva automaticamente."""
        predicao = sugerir(self.modelo_categoria, titulo, descricao)
        ia_categoria = predicao.get("categoria_sugerida")
        revisao = revisar_escrita(titulo, descricao)
        declarado = revisao.get("tipo_declarado")
        validos = ("fix", "feat", "docs", "refactor", "test")
        categoria = None
        origem_categoria = None

        if declarado in validos:
            categoria = declarado
            origem_categoria = "prefixo declarado; não verificado"
        elif not declarado and ia_categoria in validos:
            categoria = ia_categoria
            origem_categoria = "modelo didático (50 exemplos sintéticos)"
        # Um tipo não-convencional pode ser nome de módulo; não force categoria.

        if declarado in validos and ia_categoria and ia_categoria != declarado:
            aviso_categoria = (
                "Prefixo e modelo didático discordam; examine a mensagem antes de confirmar."
            )
        else:
            aviso_categoria = None

        clareza = None
        origem_clareza = None
        if self.modelo_clareza is not None:
            texto = texto_modelo(titulo, descricao)
            clareza = str(self.modelo_clareza.predict([texto])[0])
            origem_clareza = (
                f"modelo experimental treinado em {self.exemplos_clareza} "
                "avaliações humanas, ainda sem validação independente"
            )
        elif any(a["codigo"] == "titulo_vago" for a in revisao["alertas"]) and not descricao.strip():
            clareza = "vago"
            origem_clareza = "regra de título genérico, não IA treinada"

        return {
            "categoria": categoria,
            "origem_categoria": origem_categoria,
            "previsao_ml_categoria": ia_categoria,
            "aviso_categoria": aviso_categoria,
            "clareza": clareza,
            "origem_clareza": origem_clareza,
            "alertas": [a["mensagem"] for a in revisao["alertas"]],
        }
