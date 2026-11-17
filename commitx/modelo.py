"""Classificação supervisionada e comparação exploratória, sem teste externo."""

from collections import Counter
import hashlib
import json
from statistics import pstdev
import sys

import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.pipeline import FeatureUnion, Pipeline

from .dados import CLASSES
from .escrita import parse_cabecalho, texto_modelo


SEMENTE = 42
CONFIGURACOES = {
    "palavras": {
        "palavras": {"strip_accents": "unicode", "ngram_range": (1, 2), "sublinear_tf": False},
        "classificador": {"C": 1.0, "max_iter": 1000, "class_weight": None, "random_state": SEMENTE},
    },
    "misto": {
        "palavras": {"strip_accents": "unicode", "ngram_range": (1, 2), "sublinear_tf": True},
        "caracteres": {
            "analyzer": "char_wb", "strip_accents": "unicode", "ngram_range": (3, 5), "sublinear_tf": True,
        },
        "classificador": {"C": 1.0, "max_iter": 1000, "class_weight": "balanced", "random_state": SEMENTE},
    },
    "maioria": {"strategy": "most_frequent"},
}


def novo_modelo(tipo="misto"):
    """Parâmetros fixos: nenhuma escolha de configuração usa os resultados da CV."""
    if tipo not in ("palavras", "misto"):
        raise ValueError("Modelo desconhecido. Use 'palavras' ou 'misto'.")
    config = CONFIGURACOES[tipo]
    palavras = TfidfVectorizer(**config["palavras"])
    if tipo == "palavras":
        vetor = palavras
    elif tipo == "misto":
        vetor = FeatureUnion([
            ("palavras", palavras),
            ("caracteres", TfidfVectorizer(**config["caracteres"])),
        ])
    return Pipeline([
        ("tfidf", vetor),
        ("classificador", LogisticRegression(**config["classificador"])),
    ])


def treinar(dados, tipo="misto"):
    """Treina toda a base para demonstração; isto não mede generalização."""
    if not dados:
        raise ValueError("A base de treino está vazia.")
    return novo_modelo(tipo).fit(
        [linha["texto"] for linha in dados], [linha["categoria"] for linha in dados]
    )


def sugerir(modelo, titulo, descricao=""):
    """Pode abster-se; não apresenta probabilidades como confiança calibrada."""
    if not titulo.strip():
        raise ValueError("Informe um título para analisar.")
    texto = texto_modelo(titulo, descricao)
    if not texto.strip():
        raise ValueError("Descreva a mudança após o prefixo.")
    cabecalho = parse_cabecalho(titulo)
    declarado = cabecalho["tipo"].lower() if cabecalho else None
    avisos = [
        "A sugestão representa a intenção da mensagem; não verifica o diff nem a correção do código.",
        "O modelo conhece cinco classes e não detecta todos os casos fora desse escopo.",
    ]
    resultado = {"categoria_sugerida": None, "avisos": avisos, "evidencias": []}
    if declarado and declarado not in CLASSES:
        avisos.append(
            f"O tipo declarado '{declarado}' está fora das classes treinadas; sem sugestão automática."
        )
        return resultado
    if modelo.named_steps["tfidf"].transform([texto]).nnz == 0:
        avisos.append("Nenhum termo ou fragmento conhecido foi encontrado; sem sugestão automática.")
        return resultado
    categoria = str(modelo.predict([texto])[0])
    resultado["categoria_sugerida"] = categoria
    if declarado and declarado != categoria:
        avisos.append(
            "O tipo declarado difere da previsão. Revise a mensagem: essa divergência não prova erro."
        )
    return resultado


def _dividir(dados, folds):
    if isinstance(folds, bool) or not isinstance(folds, int) or folds < 2:
        raise ValueError("Use um número inteiro de folds igual ou maior que 2.")
    if not dados:
        raise ValueError("A base de avaliação está vazia.")
    ids = [linha["id"] for linha in dados]
    if len(set(ids)) != len(ids):
        raise ValueError("Cada exemplo deve ter um id único.")
    categorias = [linha["categoria"] for linha in dados]
    if set(categorias) != set(CLASSES):
        raise ValueError("A avaliação precisa das cinco categorias previstas em CLASSES.")
    grupos = [linha["grupo"] for linha in dados]
    for categoria in CLASSES:
        quantidade = len({g for g, c in zip(grupos, categorias) if c == categoria})
        if quantidade < folds:
            raise ValueError(
                f"A categoria '{categoria}' precisa de pelo menos {folds} grupos distintos."
            )
    textos = [linha["texto"] for linha in dados]
    agrupado = len(set(grupos)) != len(grupos)
    if agrupado:
        divisor = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=SEMENTE)
        particoes = list(divisor.split(textos, categorias, groups=grupos))
    else:
        divisor = StratifiedKFold(n_splits=folds, shuffle=True, random_state=SEMENTE)
        particoes = list(divisor.split(textos, categorias))
    for treino, teste in particoes:
        if any({categorias[i] for i in indices} != set(CLASSES) for indices in (treino, teste)):
            raise ValueError(
                "Um fold ficou sem alguma classe. Revise os grupos ou reduza folds; "
                "a semente não foi trocada para procurar um resultado melhor."
            )
        if {grupos[i] for i in treino} & {grupos[i] for i in teste}:
            raise ValueError("A divisão colocou um grupo em treino e teste simultaneamente.")
    return particoes, type(divisor).__name__


def _metricas(real, previsto):
    return {
        "acuracia": float(accuracy_score(real, previsto)),
        "macro_f1": float(f1_score(
            real, previsto, labels=CLASSES, average="macro", zero_division=0
        )),
    }


def avaliar(dados, folds=5):
    """Cada linha recebe uma previsão OOF por referência, nos mesmos folds.

    TF-IDF é ajustado somente no treino de cada fold. Resultados são exploratórios:
    dados sintéticos não comprovam desempenho real; CV não substitui teste externo.
    """
    particoes, estrategia = _dividir(dados, folds)
    nomes = ("palavras", "misto", "maioria")
    categorias = [linha["categoria"] for linha in dados]
    textos = [linha["texto"] for linha in dados]
    oof = {nome: [None] * len(dados) for nome in nomes}
    por_fold = {nome: [] for nome in nomes}
    fold_das_linhas = [None] * len(dados)
    metadados_folds = []
    for numero, (treino, teste) in enumerate(particoes, start=1):
        x_treino, x_teste = ([textos[i] for i in indices] for indices in (treino, teste))
        y_treino, y_teste = ([categorias[i] for i in indices] for indices in (treino, teste))
        metadados_folds.append({
            "fold": numero,
            "ids_treino": [dados[i]["id"] for i in treino],
            "ids_teste": [dados[i]["id"] for i in teste],
        })
        for i in teste:
            if fold_das_linhas[i] is not None:
                raise RuntimeError("Uma linha apareceu mais de uma vez no teste.")
            fold_das_linhas[i] = numero
        for nome in nomes:
            modelo = DummyClassifier(**CONFIGURACOES["maioria"]) if nome == "maioria" else novo_modelo(nome)
            modelo.fit(x_treino, y_treino)
            previsto = [str(valor) for valor in modelo.predict(x_teste)]
            por_fold[nome].append({"fold": numero, **_metricas(y_teste, previsto)})
            for i, previsao in zip(teste, previsto):
                oof[nome][i] = previsao
    if any(valor is None for previsoes in oof.values() for valor in previsoes):
        raise RuntimeError("Alguma linha não recebeu previsão fora do treino.")
    resultados = {}
    for nome in nomes:
        resultados[nome] = {
            **_metricas(categorias, oof[nome]),
            "desvio_macro_f1": float(pstdev(m["macro_f1"] for m in por_fold[nome])),
            "metricas_por_fold": por_fold[nome],
            "por_classe": classification_report(
                categorias, oof[nome], labels=CLASSES, output_dict=True, zero_division=0
            ),
            "matriz_confusao": confusion_matrix(categorias, oof[nome], labels=CLASSES).tolist(),
        }
    return {
        "classes": list(CLASSES),
        "n_exemplos": len(dados),
        "origens": dict(Counter(linha["origem"] for linha in dados)),
        "folds": metadados_folds,
        "resultados": resultados,
        "previsoes": [
            {**{chave: linha[chave] for chave in (
                "id", "titulo", "descricao", "categoria", "grupo", "origem"
            )}, "fold": fold_das_linhas[i], "por_modelo": {nome: oof[nome][i] for nome in nomes}}
            for i, linha in enumerate(dados)
        ],
        "metadados": {
            "estrategia": estrategia, "n_folds": folds, "semente": SEMENTE,
            "versao_python": sys.version.split()[0], "versao_sklearn": sklearn.__version__,
            "configuracoes": CONFIGURACOES,
            "sha256_base_canonica": hashlib.sha256(json.dumps(
                dados, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest(),
            "formato_hash": "SHA-256 do JSON UTF-8 de dados, sort_keys=True, sem espaços; ordem das linhas preservada.",
            "avaliacao": "Predições out-of-fold; sem conjunto de teste externo.",
            "comparacao": "Os três modelos usam as mesmas partições e parâmetros fixos; sem tuning.",
            "configuracoes_comparadas": (
                "O modelo de palavras preserva a configuração original. O misto adiciona caracteres, "
                "TF sublinear e pesos balanced; a comparação não isola o efeito dos caracteres."
            ),
            "desvio": "Desvio padrão populacional do macro-F1 entre folds; não é intervalo de confiança.",
            "matriz": "Linhas = categorias reais; colunas = previsões; ordem em classes.",
            "limites": (
                "Avaliação exploratória de classificação. Dados sintéticos não comprovam desempenho "
                "real. As métricas não avaliam clareza. Escolher ou ajustar o modelo após observar "
                "estes resultados exige uma avaliação independente posterior."
            ),
        },
    }
