"""V4: comparacao OOF por grupos entre TF-IDF e embeddings locais Ollama.

O Ollama e consultado APENAS para gerar representacoes numericas de textos.
Nao usa rotulos na geracao de embeddings; treino e avaliacao sao isolados por grupos.
O cache contem TEXTO e vetores derivados dos titulos: dados locais, nao compartilhe.
A comparacao e exploratoria; nao acessa validacao/teste reservado.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, recall_score, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import normalize
from sklearn.svm import LinearSVC

from .experimento_v3 import carregar_treino, componentes, CLASSES
from .treino_real import ENTRADA, BANCO


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _request_embeddings(texts, *, modelo, host, batch):
    for start in range(0, len(texts), batch):
        parte = texts[start:start + batch]
        payload = json.dumps({"model": modelo, "input": parte}).encode("utf-8")
        req = urllib.request.Request(
            host.rstrip("/") + "/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError) as e:
            raise ValueError(
                "Ollama nao respondeu. Verifique: ollama serve; ollama pull " + modelo
            ) from e
        emb = data.get("embeddings")
        if not isinstance(emb, list) or len(emb) != len(parte):
            raise ValueError("Resposta Ollama invalida: esperado um vetor por titulo")
        for v in emb:
            arr = np.asarray(v, dtype=np.float32)
            if arr.ndim != 1 or arr.size < 8 or not np.isfinite(arr).all():
                raise ValueError("Embedding invalido do Ollama")
            yield arr.tolist()


def carregar_embeddings(textos, *, modelo, cache, host="http://127.0.0.1:11434", batch=16):
    cache = Path(cache)
    if not 1 <= batch <= 64:
        raise ValueError("batch deve estar entre 1 e 64")
    anterior = {}
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if payload.get("modelo") != modelo:
            raise ValueError("O cache foi gerado com outro modelo. Escolha outro arquivo")
        anterior = payload.get("vetores", {})
    chaves = [_sha(t) for t in textos]
    faltantes = {}
    for t, chave in zip(textos, chaves):
        if chave not in anterior:
            faltantes[chave] = t
    if faltantes:
        novos = list(_request_embeddings(
            list(faltantes.values()), modelo=modelo, host=host, batch=batch
        ))
        if len(novos) != len(faltantes):
            raise ValueError("Numero inesperado de embeddings")
        for chave, vec in zip(faltantes, novos):
            anterior[chave] = vec
        # Cache contem apenas hashes e vetores, nao os textos originais.
        cache.parent.mkdir(parents=True, exist_ok=True)
        temp = cache.with_name(cache.name + ".tmp")
        with temp.open("w", encoding="utf-8") as f:
            json.dump({"modelo": modelo, "vetores": anterior}, f, ensure_ascii=False)
        temp.replace(cache)
    try:
        vetores = np.asarray([anterior[k] for k in chaves], dtype=np.float32)
    except (KeyError, ValueError) as e:
        raise ValueError("Cache de embeddings inconsistente") from e
    if vetores.ndim != 2 or not np.isfinite(vetores).all():
        raise ValueError("Dimensoes ou valores de embedding invalidos")
    return normalize(vetores)


def executar(registros, embeddings, saida, *, folds=5):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Saida ja existe: " + str(saida))
    if not 3 <= folds <= 8:
        raise ValueError("folds deve ficar entre 3 e 8")
    if len(registros) != len(embeddings) or len(registros) < 30:
        raise ValueError("Dados ou embeddings com tamanho invalido")
    y = np.asarray([r["categoria"] for r in registros])
    if set(y) != set(CLASSES):
        raise ValueError("Necessarias cinco classes do treino")
    grupos = componentes(registros)
    if len(set(grupos)) < folds:
        raise ValueError("Grupos insuficientes")
    titles = [r["titulo"] for r in registros]
    embeddings = np.asarray(embeddings, dtype=np.float32)
    if not np.isfinite(embeddings).all() or embeddings.ndim != 2:
        raise ValueError("Embeddings invalidos")
    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=42)
    preds = []
    for fold, (train, val) in enumerate(cv.split(np.zeros(len(y)), y, grupos), start=1):
        if set(grupos[train]) & set(grupos[val]):
            raise ValueError("Vazamento entre grupos")
        if set(y[train]) != set(CLASSES):
            raise ValueError("Classe ausente no treino de um fold")
        tfidf = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), strip_accents="unicode",
            sublinear_tf=True, max_features=20000
        )
        tr_txt = tfidf.fit_transform([titles[i] for i in train])
        va_txt = tfidf.transform([titles[i] for i in val])
        tr_emb, va_emb = embeddings[train], embeddings[val]
        # Prefixos iguais para todos os folds; sem parametros escolhidos nos dados de validacao.
        datasets = {
            "svm_titulo": (tr_txt, va_txt),
            "svm_embeddings": (csr_matrix(tr_emb), csr_matrix(va_emb)),
            "svm_hibrido": (
                hstack([tr_txt, csr_matrix(tr_emb)], format="csr"),
                hstack([va_txt, csr_matrix(va_emb)], format="csr"),
            )
        }
        for nome, (xtr, xva) in datasets.items():
            modelo = LinearSVC(C=1.0, class_weight="balanced", random_state=42)
            modelo.fit(xtr, y[train])
            for idx, pred in zip(val, modelo.predict(xva)):
                preds.append({
                    "id": registros[int(idx)]["id"], "fold": fold, "modelo": nome,
                    "real": y[int(idx)], "previsto": str(pred),
                    "acertou": int(y[int(idx)] == pred)
                })
    metricas = {}
    for nome in ("svm_titulo", "svm_embeddings", "svm_hibrido"):
        atual = [x for x in preds if x["modelo"] == nome]
        if len(atual) != len(registros) or len(set(x["id"] for x in atual)) != len(registros):
            raise ValueError("Predicoes incompletas ou duplicadas")
        real = [x["real"] for x in atual]
        previsto = [x["previsto"] for x in atual]
        metricas[nome] = {
            "acuracia": float(accuracy_score(real, previsto)),
            "macro_f1": float(f1_score(real, previsto, labels=list(CLASSES), average="macro", zero_division=0)),
            "recall_por_classe": {
                c: float(recall_score(real, previsto, labels=[c], average="macro", zero_division=0))
                for c in CLASSES
            },
            "matriz_confusao": confusion_matrix(real, previsto, labels=list(CLASSES)).tolist(),
        }
    result = {
        "protocolo": "V4-stratified-groupcv-Ollama-embeddings",
        "treino": len(registros),
        "grupos": len(set(grupos)),
        "folds": folds,
        "modelos": metricas,
        "restricoes": [
            "Apenas treino; validacao e teste reservado nao foram usados",
            "Nenhum rotulo ou banco foi alterado",
            "Dados assistidos por IA; resultado exploratorio, nao teste externo",
            "Embeddings locais via Ollama; o cache nao deve ser compartilhado",
            "Mesmos folds para os tres classificadores",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "resumo.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (saida / "previsoes.csv").open("x", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(preds[0]))
        writer.writeheader()
        writer.writerows(preds)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--banco", type=Path, default=BANCO)
    p.add_argument("--saida", type=Path, default=Path("resultados/semantica-v4-01"))
    p.add_argument("--cache", type=Path, default=Path("resultados/cache-embeddings-ollama-v4.json"))
    p.add_argument("--modelo-ollama", default="embeddinggemma")
    p.add_argument("--host", default="http://127.0.0.1:11434")
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--folds", type=int, default=5)
    a = p.parse_args(argv)
    try:
        registros = carregar_treino(a.entrada, a.banco)
        vetores = carregar_embeddings(
            [r["titulo"] for r in registros], modelo=a.modelo_ollama,
            cache=a.cache, host=a.host, batch=a.batch
        )
        saida = executar(registros, vetores, a.saida, folds=a.folds)
    except (ValueError, OSError, json.JSONDecodeError, csv.Error) as e:
        p.error(str(e))
    print("Commits:", saida["treino"], "Grupos:", saida["grupos"])
    for nome, m in saida["modelos"].items():
        print(f"{nome}: acuracia={m['acuracia']:.3f}; macro-F1={m['macro_f1']:.3f}")
        print("  recall:", m["recall_por_classe"])
    print("Resultado:", a.saida)


if __name__ == "__main__":
    main()
