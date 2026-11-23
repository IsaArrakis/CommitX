"""Experimento V8: comparar SVM de titulo com SVM de titulo + caminhos Git.

Usa SOMENTE rotulos da particao treino V5 para ajustar ambos os modelos.
Validacao V5 e exploratoria: rotulos anteriores assistidos por IA e ja vistos.
Nao usa a particao teste V5, nem altera bancos, rotulos ou modelos antigos.

Comandos:
  python -m commitx.modelo_contexto_v8 executar --saida resultados/contexto-v8-01
  python -m commitx.modelo_contexto_v8 analisar --modelo resultados/contexto-v8-01 --titulo "Update README" --arquivos README.md
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from joblib import dump, load
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from .escrita import texto_modelo
from .revisao_git_v5 import abrir, ENTRADA, PLANO, BANCO

CLASSES = ("fix", "feat", "docs", "refactor", "test")
ARTEFATO = "modelos.joblib"


def _limpar_titulo(titulo):
    return texto_modelo(str(titulo or "").strip(), "")


def _numero(valor):
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _faixa(valor):
    if valor == 0:
        return "zero"
    if valor == 1:
        return "um"
    if valor < 5:
        return "poucos"
    if valor < 20:
        return "varios"
    return "muitos"


def contexto_arquivos(row):
    """Extrai sinais de caminhos reais, sem inventar categoria ou ler rótulos."""
    origem = next((row[k] for k in ("arquivos", "arquivos_alterados", "caminhos")
                   if str(row.get(k) or "").strip()), "")
    paths = [p.strip().replace("\\", "/").lower()
             for p in re.split(r"\s*\|\s*|[;\n]+", str(origem))
             if p.strip()]
    paths = paths[:80]
    if not paths:
        return ""
    tokens = []
    n_docs, n_tests, n_build = 0, 0, 0
    for path in paths:
        # Termos genericos e extensoes transferem melhor entre repositorios/linguagens.
        pedacos = re.findall(r"[a-z0-9_]+", path)
        tokens.extend(pedacos[-9:])
        nome = path.rsplit("/", 1)[-1]
        ext = nome.rsplit(".", 1)[-1] if "." in nome else ""
        if ext:
            tokens.append("extensao_" + ext)
        doc = (nome.startswith(("readme", "changelog", "contributing", "license"))
               or ext in ("md", "adoc", "rst")
               or "/docs/" in "/" + path or "/documentation/" in "/" + path)
        teste = bool(re.search(r"(^|[/_.-])(tests?|specs?)([/_.-]|$)", path))
        build = nome in ("pom.xml", "build.gradle", "build.gradle.kts", "package.json",
                         "package-lock.json", "go.mod", "requirements.txt",
                         "gradle.properties", "cargo.toml")
        n_docs += bool(doc)
        n_tests += bool(teste)
        n_build += bool(build)
    tokens.extend(["quantidadearquivos_" + _faixa(len(paths)),
                   "quantidadelinhasadicionadas_" + _faixa(_numero(row.get("linhas_adicionadas"))),
                   "quantidadelinhasremovidas_" + _faixa(_numero(row.get("linhas_removidas")))])
    if n_docs == len(paths):
        tokens.append("apenasdocumentacao")
    elif n_docs:
        tokens.append("comdocumentacao")
    if n_tests == len(paths):
        tokens.append("apenastestes")
    elif n_tests:
        tokens.append("comtestes")
    if n_build == len(paths):
        tokens.append("apenasconfiguracao")
    elif n_build:
        tokens.append("comconfiguracao")
    return " ".join(tokens)


def _matriz(rows):
    return np.asarray([[_limpar_titulo(r["titulo"]), contexto_arquivos(r)]
                       for r in rows], dtype=str)


def _construir(com_arquivos=False):
    titulo = TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode",
                             sublinear_tf=True, max_features=20000)
    if not com_arquivos:
        return Pipeline([("tfidf", titulo),
                         ("svm", LinearSVC(C=1.0, class_weight="balanced", random_state=42))])
    contexto = TfidfVectorizer(ngram_range=(1, 2), strip_accents="unicode",
                               sublinear_tf=True, max_features=15000)
    return Pipeline([
        ("vetores", ColumnTransformer(
            [("titulo", titulo, 0), ("caminhos", contexto, 1)],
            transformer_weights={"titulo": 1.0, "caminhos": 1.0},
            sparse_threshold=1.0,
        )),
        ("svm", LinearSVC(C=1.0, class_weight="balanced", random_state=42)),
    ])


def _carregar_rotulados(entrada=ENTRADA, plano=PLANO, banco=BANCO):
    rows, dados = abrir(entrada=entrada, plano=plano, banco=banco)
    banco = Path(banco)
    with sqlite3.connect("file:" + banco.resolve().as_posix() + "?mode=ro", uri=True) as con:
        gold = dict(con.execute("SELECT id,categoria FROM avaliacoes"))
    treino, validacao = [], []
    for r in rows:
        particao = dados["repositorios"][r["repositorio"]]
        if particao == "teste":
            continue
        if r["id"] not in gold:
            continue
        if gold[r["id"]] not in CLASSES:
            continue
        if not _limpar_titulo(r["titulo"]):
            continue
        novo = {**r, "_rotulo": gold[r["id"]]}
        if particao == "treino":
            treino.append(novo)
        elif particao == "validacao":
            validacao.append(novo)
    if not treino:
        raise ValueError("Sem rotulos de treino V5 nas cinco categorias")
    if set(r["_rotulo"] for r in treino) != set(CLASSES):
        raise ValueError("Treino V5 ainda nao contempla as cinco categorias")
    if not any(contexto_arquivos(r) for r in treino):
        raise ValueError("Treino V5 nao contem caminhos de arquivos no CSV")
    repos_treino = {r["repositorio"] for r in treino}
    if repos_treino & {r["repositorio"] for r in validacao}:
        raise ValueError("Repositorios cruzados entre treino e validacao V5")
    # Retirar titulos identicos entre treino e validacao (mesmo com repositorios distintos).
    titulos_treino = {" ".join(_limpar_titulo(r["titulo"]).casefold().split()) for r in treino}
    valida_sem_duplicados = [
        r for r in validacao
        if " ".join(_limpar_titulo(r["titulo"]).casefold().split()) not in titulos_treino
    ]
    return treino, valida_sem_duplicados, len(validacao) - len(valida_sem_duplicados)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executar(*, saida, entrada=ENTRADA, plano=PLANO, banco=BANCO):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Saida ja existe, escolha outra pasta: " + str(saida))
    treino, validacao, repetidos = _carregar_rotulados(entrada, plano, banco)
    x_titulo = [_limpar_titulo(r["titulo"]) for r in treino]
    x_contexto = _matriz(treino)
    y = [r["_rotulo"] for r in treino]
    modelos = {
        "svm_titulo_v5": _construir(com_arquivos=False),
        "svm_titulo_arquivos_v5": _construir(com_arquivos=True),
    }
    modelos["svm_titulo_v5"].fit(x_titulo, y)
    modelos["svm_titulo_arquivos_v5"].fit(x_contexto, y)
    yv = [r["_rotulo"] for r in validacao]
    pred = {}
    rel = {}
    for nome, modelo in modelos.items():
        if validacao:
            entradas = (_matriz(validacao) if nome == "svm_titulo_arquivos_v5" else
                        [_limpar_titulo(r["titulo"]) for r in validacao])
            previsoes = [str(x) for x in modelo.predict(entradas)]
            pred[nome] = previsoes
            rel[nome] = {
                "acertos": sum(a == b for a, b in zip(yv, previsoes)),
                "acuracia": round(float(accuracy_score(yv, previsoes)), 4),
                "macro_f1": round(float(f1_score(yv, previsoes, labels=list(CLASSES),
                                                 average="macro", zero_division=0)), 4),
                "por_classe": classification_report(yv, previsoes, labels=list(CLASSES),
                                                     zero_division=0, output_dict=True),
            }
        else:
            rel[nome] = {"aviso": "Sem validacao V5 rotulada"}
    saida.mkdir(parents=True, exist_ok=False)
    dump(modelos, saida / ARTEFATO)
    with (saida / "previsoes_validacao.csv").open("x", encoding="utf-8", newline="") as f:
        campos = ["id", "titulo", "categoria_revisada", "svm_titulo_v5", "svm_titulo_arquivos_v5",
                  "arquivos_disponiveis"]
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for i, r in enumerate(validacao):
            writer.writerow({
                "id": r["id"], "titulo": r["titulo"],
                "categoria_revisada": r["_rotulo"],
                "svm_titulo_v5": pred.get("svm_titulo_v5", [])[i],
                "svm_titulo_arquivos_v5": pred.get("svm_titulo_arquivos_v5", [])[i],
                "arquivos_disponiveis": bool(contexto_arquivos(r)),
            })
    resumo = {
        "protocolo": "v8-comparacao-v5-titulo-versus-titulo-arquivos",
        "treino_v5_rotulado_cinco_classes": len(treino),
        "treino_por_classe": dict(Counter(y)),
        "validacao_v5_avaliada": len(validacao),
        "repeticoes_titulo_excluidas": repetidos,
        "validacao_por_classe": dict(Counter(yv)),
        "caminhos_treino_presentes": sum(bool(contexto_arquivos(r)) for r in treino),
        "caminhos_validacao_presentes": sum(bool(contexto_arquivos(r)) for r in validacao),
        "modelos": rel,
        "sha256_csv_coleta": _hash(entrada),
        "sha256_plano": _hash(plano),
        "observacoes": [
            "Os dois modelos V8 foram treinados SOMENTE com rotulos V5 da particao treino.",
            "O grupo teste V5 nao foi usado e os modelos antigos permanecem intocados.",
            "Validacao V5 ja utilizada, assistida por IA e pequena: comparacao apenas exploratoria.",
            "As cinco classes nao cobrem fora_escopo nem indeterminado.",
            "Esta comparacao usa treino V5 e NAO e comparacao direta com modelo antigo de 397 rotulos.",
            "A acuracia nao deve ser anunciada como desempenho independente em repositorios novos.",
            "Para aplicar contexto nos 97 mil commits, e preciso fornecer caminhos Git reais; sem caminhos a inferencia usa o modelo titulo V8.",
            "Modelos joblib devem ser carregados apenas de arquivos locais confiaveis.",
        ],
    }
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def analisar(*, modelo, titulo, arquivos=""):
    origem = Path(modelo)
    path = origem / ARTEFATO if origem.is_dir() else origem
    modelos = load(path)  # somente arquivo local confiavel
    row = {"titulo": titulo, "arquivos": arquivos}
    if not _limpar_titulo(titulo):
        raise ValueError("Titulo vazio")
    if contexto_arquivos(row):
        previsto = str(modelos["svm_titulo_arquivos_v5"].predict(_matriz([row]))[0])
        usado = "svm_titulo_arquivos_v5"
    else:
        previsto = str(modelos["svm_titulo_v5"].predict([_limpar_titulo(titulo)])[0])
        usado = "svm_titulo_v5"
    return {"categoria_prevista": previsto, "modelo_usado": usado,
            "aviso": "Previsao automatica, nao gabarito. V8 ainda nao validado independentemente."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="comando", required=True)
    ex = sub.add_parser("executar")
    ex.add_argument("--saida", type=Path, default=Path("resultados/contexto-v8-01"))
    ex.add_argument("--entrada", type=Path, default=ENTRADA)
    ex.add_argument("--plano", type=Path, default=PLANO)
    ex.add_argument("--banco", type=Path, default=BANCO)
    un = sub.add_parser("analisar")
    un.add_argument("--modelo", type=Path, required=True)
    un.add_argument("--titulo", required=True)
    un.add_argument("--arquivos", default="")
    args = p.parse_args(argv)
    try:
        if args.comando == "executar":
            resultado = executar(saida=args.saida, entrada=args.entrada,
                                 plano=args.plano, banco=args.banco)
        else:
            resultado = analisar(modelo=args.modelo, titulo=args.titulo,
                                 arquivos=args.arquivos)
    except (OSError, ValueError, sqlite3.Error) as erro:
        p.error(str(erro))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
