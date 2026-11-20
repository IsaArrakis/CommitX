"""Classificador hibrido utilizavel: TF-IDF dos titulos + embeddings Ollama.

Treinar: python -m commitx.classificador_hibrido treinar
Analisar: python -m commitx.classificador_hibrido analisar --titulo "Fix deadlock"
Lote: python -m commitx.classificador_hibrido lote --entrada novos.csv --saida previsoes.csv

Treina SOMENTE na particao treino. Nao altera rotulos/banco e nao acessa
validacao ou teste. Semantica e gerada LOCALMENTE no Ollama. Arquivo joblib
deve ser carregado apenas se foi gerado neste computador e e confiavel.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from joblib import dump, load
import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

from .classificador_real import _hash_arquivo
from .escrita import parse_cabecalho, texto_modelo
from .experimento_v3 import carregar_treino, CLASSES
from .semantica_v4 import carregar_embeddings
from .treino_real import ENTRADA, BANCO

DESTINO = Path("resultados/classificador-hibrido-v4")
CACHE = Path("resultados/cache-embeddings-ollama-v4.json")
NOME_MODELO = "modelo_hibrido.joblib"
NOME_MANIFESTO = "manifesto.json"


def vetorizar(titulos, vetores, vectorizer, *, treinar_vocabulario=False):
    if len(titulos) != len(vetores):
        raise ValueError("Quantidade de textos e vetores diferente")
    if treinar_vocabulario:
        x_words = vectorizer.fit_transform(titulos)
    else:
        x_words = vectorizer.transform(titulos)
    emb = np.asarray(vetores, dtype=np.float32)
    if emb.ndim != 2 or emb.shape[0] != len(titulos) or not np.isfinite(emb).all():
        raise ValueError("Embeddings invalidos")
    return hstack([x_words, csr_matrix(emb)], format="csr")


def treinar(*, entrada=ENTRADA, banco=BANCO, saida=DESTINO, cache=CACHE,
            modelo_ollama="embeddinggemma", host="http://127.0.0.1:11434"):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("A saida ja existe; nao sobrescrever: " + str(saida))
    dados = carregar_treino(entrada, banco)
    contagens = Counter(r["categoria"] for r in dados)
    if set(contagens) != set(CLASSES) or min(contagens.values()) < 5:
        raise ValueError("Necessarios ao menos 5 exemplos por classe no treino")
    titulos = [r["titulo"] for r in dados]
    labels = [r["categoria"] for r in dados]
    vetores = carregar_embeddings(
        titulos, modelo=modelo_ollama, cache=cache, host=host
    )
    vectorizer = TfidfVectorizer(
        analyzer="word", ngram_range=(1, 2), strip_accents="unicode",
        sublinear_tf=True, max_features=20000
    )
    x = vetorizar(titulos, vetores, vectorizer, treinar_vocabulario=True)
    model = LinearSVC(C=1.0, class_weight="balanced", random_state=42)
    model.fit(x, labels)
    artifact = {
        "tfidf": vectorizer,
        "svm": model,
        "modelo_ollama": modelo_ollama,
        "dim_emb": int(vetores.shape[1]),
    }
    manifesto = {
        "protocolo": "hibrido-v4-final-ajustado-em-todos-os-exemplos-de-treino",
        "modelagem": "TF-IDF titulo sem prefixo + embeddinggemma Ollama + LinearSVC(C=1.0, balanced)",
        "modelo_ollama": modelo_ollama,
        "registros_treino": len(dados),
        "classes_treino": dict(contagens),
        "sha256_csv_preparado": _hash_arquivo(entrada),
        "sha256_banco_labels": _hash_arquivo(banco),
        "avaliacao_exploratoria": {
            "acuracia_oof_v4": 0.707808564231738,
            "macro_f1_oof_v4": 0.680,
            "nota": "Referencia da V4 em folds; NAO desempenho comprovado deste modelo final"
        },
        "cuidados": [
            "Somente treino; validacao e teste nao usados",
            "Modelo Ollama deve ser o mesmo no treino e na inferencia",
            "O prefixo declarado e retirado do texto usado pelo modelo",
            "Margem SVM nao e probabilidade nem garantia de acerto",
            "Nao carregar joblib de fonte desconhecida",
            "Rótulos assistidos por IA exigem auditoria independente",
            "Nao assegura acuracia superior a 80% em repositorios novos",
        ]
    }
    saida.mkdir(parents=True, exist_ok=False)
    dump(artifact, saida / NOME_MODELO)
    (saida / NOME_MANIFESTO).write_text(
        json.dumps(manifesto, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    return manifesto


def carregar_modelo(caminho):
    caminho = Path(caminho)
    path = caminho / NOME_MODELO if caminho.is_dir() else caminho
    if not path.is_file():
        raise FileNotFoundError("Modelo hibrido nao encontrado: " + str(path))
    obj = load(path)  # Somente artefatos locais confiaveis.
    if (not isinstance(obj, dict)
        or not isinstance(obj.get("tfidf"), TfidfVectorizer)
        or not isinstance(obj.get("svm"), LinearSVC)
        or not isinstance(obj.get("modelo_ollama"), str)
        or not isinstance(obj.get("dim_emb"), int)):
        raise ValueError("Artefato hibrido invalido")
    return obj


def prever_lote(artefato, titulos, *, cache=CACHE,
                host="http://127.0.0.1:11434"):
    if not titulos:
        raise ValueError("Lista de titulos vazia")
    if any(not isinstance(t, str) or not t.strip() for t in titulos):
        raise ValueError("Todos os titulos precisam ser textos nao vazios")
    tratados = [texto_modelo(t, "") for t in titulos]
    if any(not t for t in tratados):
        raise ValueError("Titulo vazio apos remover prefixo convencional")
    emb = carregar_embeddings(
        tratados, modelo=artefato["modelo_ollama"], cache=cache, host=host
    )
    if emb.shape[1] != artefato["dim_emb"]:
        raise ValueError("Dimensao incompatível: verifique modelo Ollama original")
    x = vetorizar(tratados, emb, artefato["tfidf"])
    decisao = np.asarray(artefato["svm"].decision_function(x))
    classes = artefato["svm"].classes_
    saida = []
    for titulo, score in zip(titulos, decisao):
        ordem = np.argsort(score)[::-1]
        primeira, segunda = map(int, ordem[:2])
        prevista = str(classes[primeira])
        margem = float(score[primeira] - score[segunda])
        cabecalho = parse_cabecalho(titulo.strip())
        tipo = cabecalho["tipo"] if cabecalho else ""
        divergente = tipo in CLASSES and tipo != prevista
        revisar = divergente or margem < .2
        saida.append({
            "titulo": titulo.strip(),
            "categoria_prevista": prevista,
            "segunda_opcao": str(classes[segunda]),
            "tipo_declarado": tipo,
            "divergencia_prefixo": divergente,
            "margem_top2": round(margem, 4),
            "revisar_manualmente": revisar,
            "motivo": (
                "Prefixo diverge: conferir codigo" if divergente else
                "Duas categorias proximas" if margem < .2 else
                "Previsao automatica; nao garante acerto"
            ),
        })
    return saida


def prever(artefato, titulo, **kwargs):
    return prever_lote(artefato, [titulo], **kwargs)[0]


def analisar_csv(artefato, entrada, saida, *, cache=CACHE, host="http://127.0.0.1:11434"):
    entrada, saida = Path(entrada), Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Saida ja existe: " + str(saida))
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "titulo" not in (reader.fieldnames or []):
            raise ValueError("CSV deve conter coluna titulo")
        linhas = list(reader)
    if not linhas:
        raise ValueError("CSV de entrada vazio")
    titulos = [r["titulo"] for r in linhas]
    previsoes = prever_lote(artefato, titulos, cache=cache, host=host)
    campos = ["id"] + list(previsoes[0])
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for i, (row, pred) in enumerate(zip(linhas, previsoes), 1):
            writer.writerow({"id": row.get("id") or str(i), **pred})
    return {
        "previsoes": len(previsoes),
        "revisao_sugerida": sum(p["revisar_manualmente"] for p in previsoes),
        "arquivo": str(saida),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="acao", required=True)
    train = sub.add_parser("treinar")
    train.add_argument("--entrada", type=Path, default=ENTRADA)
    train.add_argument("--banco", type=Path, default=BANCO)
    train.add_argument("--saida", type=Path, default=DESTINO)
    train.add_argument("--modelo-ollama", default="embeddinggemma")
    one = sub.add_parser("analisar")
    one.add_argument("--modelo", type=Path, default=DESTINO)
    one.add_argument("--titulo", required=True)
    batch = sub.add_parser("lote")
    batch.add_argument("--modelo", type=Path, default=DESTINO)
    batch.add_argument("--entrada", type=Path, required=True)
    batch.add_argument("--saida", type=Path, required=True)
    for cmd in (train, one, batch):
        cmd.add_argument("--cache", type=Path, default=CACHE)
        cmd.add_argument("--host", default="http://127.0.0.1:11434")
    args = p.parse_args(argv)
    try:
        if args.acao == "treinar":
            res = treinar(entrada=args.entrada, banco=args.banco, saida=args.saida,
                          cache=args.cache, host=args.host,
                          modelo_ollama=args.modelo_ollama)
        elif args.acao == "analisar":
            res = prever(carregar_modelo(args.modelo), args.titulo,
                         cache=args.cache, host=args.host)
        else:
            res = analisar_csv(carregar_modelo(args.modelo), args.entrada, args.saida,
                              cache=args.cache, host=args.host)
    except (ValueError, OSError, csv.Error) as exc:
        p.error(str(exc))
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
