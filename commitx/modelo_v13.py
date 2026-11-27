"""Treino e inferência do classificador textual experimental bilíngue."""
from collections import Counter
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import joblib
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .comparacao_prefixos import CLASSES
from .escrita import PREFIXO, texto_modelo
from .v12_final import SEMENTE

SAIDA = Path("resultados/modelo-experimental-v13-01")
VERSAO = "V13-experimental-bilingue"
MODOS = ("com_prefixo", "sem_prefixo")
ARQUIVOS = {modo: f"v13_{modo}.joblib" for modo in MODOS}
CONFIGS = ("palavras", "palavras_caracteres", "palavras_caracteres_contexto")
MARGEM_MINIMA = 0.15
PESOS_ORIGEM = {
    "humano_v12": 1.0,
    "chatgpt_pseudorotulo": 0.55,
    "chatgpt_traducao_pseudorotulo": 0.35,
    "chatgpt_sintetico": 0.25,
}
# A SVM aprende o peso dos sinais em conjunto com o vocabulário.
PADROES = tuple(re.compile(padrao) for padrao in (
    r"\b(?:add|implement|introduce|support|enable|adicion\w*|implement\w*|integr\w*|introduz\w*|habilit\w*)\b.{0,70}\b(?:api|ast|opcion\w*|option\w*|support|suporte|funcionalidade|endpoint|route|rota|feature|handler|mode|modo)\b",
    r"\b(?:compar\w*|analis\w*|analy[sz]\w*)\b.{0,60}\b(?:ast|estrutur\w*|structur\w*)\b",
    r"\b(?:fix\w*|correct\w*|corrig\w*|correcao|prevent\w*|evit\w*|resolv\w*)\b.{0,70}\b(?:bug|err\w*|crash\w*|falh\w*|regress\w*|incorrect\w*|incorret\w*|null|except\w*|exce\w*)\b",
    r"\b(?:extract\w*|restructur\w*|reorganiz\w*|refator\w*|refactor\w*|simplif\w*|extra[ir]\w*|agrup\w*)\b",
    r"\b(?:readme|changelog|docstrings?|documenta\w*|guides?|guias?|tutorial\w*)\b",
    r"\b(?:tests?|testes?|pytest|unittest|assert\w*|coverage|cobertura)\b",
    r"\b(?:sem alterar|without chang\w*|preserv\w*)\b.{0,50}\b(?:behavior|comportamento|semantics|semantica)\b",
))


def normalizar(texto):
    base = unicodedata.normalize("NFKD", texto.casefold())
    return " ".join("".join(c for c in base if not unicodedata.combining(c)).split())


def texto_classificador(titulo, modo):
    return normalizar(titulo if modo == "com_prefixo" else texto_modelo(titulo))


class SinaisBilingues(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return csr_matrix([[float(bool(p.search(titulo))) for p in PADROES] for titulo in X])


def treinar_modelo(config, registros, modo):
    if config not in CONFIGS:
        raise ValueError(f"Configuração V13 desconhecida: {config}")
    vetores = [("palavras", TfidfVectorizer(
        ngram_range=(1, 2), sublinear_tf=True, max_features=20000,
    ))]
    if config != "palavras":
        vetores.append(("caracteres", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, max_features=30000,
        )))
    if config == "palavras_caracteres_contexto":
        vetores.append(("contexto", SinaisBilingues()))
    pesos_vetores = {"palavras": 1.0, "caracteres": 0.75, "contexto": 0.35}
    pipeline = Pipeline([
        ("tfidf", FeatureUnion(vetores, transformer_weights={n: pesos_vetores[n] for n, _ in vetores})),
        ("model", LinearSVC(C=0.5, random_state=SEMENTE, max_iter=5000)),
    ])
    pesos = [PESOS_ORIGEM[r.origem] for r in registros]
    rotulos = [r.categoria for r in registros]
    massas = Counter()
    for categoria, peso in zip(rotulos, pesos):
        massas[categoria] += peso
    media = sum(pesos) / len(massas)
    return pipeline.fit(
        [texto_classificador(r.titulo, modo) for r in registros],
        rotulos,
        model__sample_weight=[peso * media / massas[c] for peso, c in zip(pesos, rotulos)],
    )


def prever(modelo, textos):
    vetores = modelo.named_steps["tfidf"].transform(textos).tocsr()
    svm = modelo.named_steps["model"]
    notas = svm.decision_function(vetores)
    ordem = np.argsort(-notas, axis=1, kind="stable")
    for indice, (primeiro, segundo) in enumerate(ordem[:, :2]):
        margem = float(notas[indice, primeiro] - notas[indice, segundo])
        sem_sinais = vetores.indptr[indice] == vetores.indptr[indice + 1]
        yield str(svm.classes_[primeiro]), None if sem_sinais else margem


def sugestao(categoria, margem, minimo=MARGEM_MINIMA):
    return categoria if margem is not None and margem >= minimo else None


def _manifesto(pasta):
    caminho = pasta / "manifesto.json"
    if not caminho.is_file():
        raise FileNotFoundError("Modelo V13 indisponível. Execute o treinamento V13.")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or dados.get("versao") != VERSAO:
        raise ValueError("Manifesto incompatível com a V13.")
    hashes = dados.get("artefatos_sha256")
    minimo = dados.get("margem_minima")
    if (not isinstance(hashes, dict) or dados.get("configuracao") not in CONFIGS
            or not isinstance(minimo, (int, float)) or not 0 <= minimo <= 1):
        raise ValueError("Manifesto da V13 incompleto ou inválido.")
    return dados


def _artefato(pasta, manifesto, modo):
    nome = ARQUIVOS[modo]
    conteudo = (pasta / nome).read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != manifesto["artefatos_sha256"].get(nome):
        raise ValueError(f"Integridade inválida para {nome}.")
    return conteudo


def situacao(pasta):
    try:
        manifesto = _manifesto(pasta)
        for modo in MODOS:
            _artefato(pasta, manifesto, modo)
    except (ValueError, OSError):
        return {"pronto": False}
    return {"pronto": True, "configuracao": manifesto["configuracao"]}


def escopo_titulo(titulo):
    tipo = PREFIXO.match(titulo)
    declarado = re.split(r"[(!:]", tipo[0], maxsplit=1)[0].lower() if tipo else None
    if declarado and declarado not in CLASSES:
        return declarado, f'O tipo declarado "{declarado}" está fora do escopo do CommitX.'
    if not texto_modelo(titulo):
        return declarado, "Descreva a mudança após o prefixo."
    return declarado, None


def analisar_modelo(pasta, titulo, modo="auto"):
    titulo = titulo.strip()
    if not titulo:
        raise ValueError("Informe o título do commit.")
    if modo not in ("auto", *MODOS):
        raise ValueError("Modo de classificação inválido.")
    declarado, motivo = escopo_titulo(titulo)
    escolhido = ("com_prefixo" if declarado in CLASSES else "sem_prefixo") if modo == "auto" else modo
    categoria = margem = None
    avisos = ["A previsão usa somente o título."]
    if declarado and declarado not in CLASSES:
        escolhido = None
    if not motivo:
        manifesto = _manifesto(pasta)
        # Os arquivos joblib devem ter procedência local confiável.
        modelo = joblib.load(BytesIO(_artefato(pasta, manifesto, escolhido)))
        previsto, margem = next(prever(modelo, [texto_classificador(titulo, escolhido)]))
        categoria = sugestao(previsto, margem, manifesto["margem_minima"])
        if margem is None:
            motivo = "O título não contém características reconhecidas pelo modelo."
        elif categoria is None:
            motivo = "A margem entre as duas primeiras categorias é insuficiente para sugerir uma classe."
        if categoria and declarado and declarado != categoria:
            avisos.append("O prefixo declarado diverge da categoria sugerida.")
    if motivo:
        avisos.append(motivo)
    return {"categoria_sugerida": categoria, "tipo_declarado": declarado, "modo": escolhido,
            "margem_svm": round(margem, 4) if margem is not None else None,
            "motivo": motivo, "avisos": avisos}
