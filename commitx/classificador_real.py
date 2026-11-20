"""CommitX: classificador utilizavel treinado nos rotulos de TREINO reais.

Este comando NAO usa dados de validacao/teste nem muda rotulos.
Treinamento: python -m commitx.classificador_real treinar
Inferencia:   python -m commitx.classificador_real analisar --titulo "Corrige crash"
Lote:         python -m commitx.classificador_real lote --entrada mensagens.csv --saida previsoes.csv

O prefixo declarado nao entra no modelo e so e mostrado como informacao auxiliar.
A margem da SVM nao e uma probabilidade. Modelo joblib deve ser local e confiavel.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from joblib import dump, load
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from .escrita import parse_cabecalho, texto_modelo
from .experimento_v3 import _model, carregar_treino
from .treino_real import ENTRADA, BANCO, CATEGORIAS_VALIDAS

CLASSES = set(CATEGORIAS_VALIDAS)
DESTINO = Path("resultados/classificador-real-01")
ARQUIVO_MODELO = "modelo.joblib"
ARQUIVO_MANIFESTO = "manifesto.json"


def _hash_arquivo(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for parte in iter(lambda: f.read(1024 * 1024), b""):
            h.update(parte)
    return h.hexdigest()


def treinar(*, entrada=ENTRADA, banco=BANCO, saida=DESTINO):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Saida ja existe. Preserve o modelo anterior: " + str(saida))
    dados = carregar_treino(entrada, banco)
    classes = Counter(x["categoria"] for x in dados)
    if set(classes) != CLASSES or any(n < 5 for n in classes.values()):
        raise ValueError("Precisamos de pelo menos 5 rotulos por categoria de treino")
    model = _model("svm_words_title", 1.0)
    titulos = [x["titulo"] for x in dados]
    model.fit(titulos, [x["categoria"] for x in dados])
    if not isinstance(model, Pipeline) or not isinstance(model.named_steps["model"], LinearSVC):
        raise ValueError("O classificador final nao e a SVM esperada")
    manifesto = {
        "modelo": "SVM Linear C=1.0 + TF-IDF palavras 1-2gram",
        "entrada_modelo": "somente titulo sem prefixo convencional",
        "treino_registros": len(dados),
        "classes_treino": dict(classes),
        "origem": "rotulos de treino do SQLite; exclui validacao e teste",
        "sha256_csv_preparado": _hash_arquivo(entrada),
        "sha256_sqlite_rotulos": _hash_arquivo(banco),
        "avaliacao_exploratoria_anterior": {
            "protocolo": "V3 OOF agrupada por repositorios e titulos",
            "acuracia": 0.654911838790932,
            "macro_f1": 0.6137571883685776,
            "observacao": "Esses valores sao do experimento V3, NAO do modelo final treinado em todos os exemplos."
        },
        "ressalvas": [
            "Treinado apenas em 5 categorias de commits. Nao identifica outros tipos com confianca.",
            "Predicao de uma SVM nao e evidencia de que o commit foi classificado corretamente.",
            "Margens da SVM nao sao probabilidades calibradas.",
            "Os dados rotulados ja tiveram assistencia de IA; avaliar em projetos novos.",
            "Nao usar validacao ou teste na escolha de parametros.",
            "Nao carregar modelos joblib de fontes desconhecidas.",
        ]
    }
    saida.mkdir(parents=True, exist_ok=False)
    dump(model, saida / ARQUIVO_MODELO)
    (saida / ARQUIVO_MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifesto


def carregar_modelo(caminho):
    path = Path(caminho)
    if path.is_dir():
        path = path / ARQUIVO_MODELO
    if not path.is_file():
        raise FileNotFoundError("Modelo nao encontrado: " + str(path))
    # Somente arquivos locais gerados pelo proprio programa, nunca vindos de terceiros.
    model = load(path)
    if not isinstance(model, Pipeline) or "tfidf" not in model.named_steps:
        raise ValueError("Modelo carregado com formato inesperado")
    return model


def prever(modelo, titulo, descricao=""):
    if not isinstance(titulo, str) or not titulo.strip():
        raise ValueError("Informe um titulo nao vazio")
    texto = texto_modelo(titulo, "")
    tipo = parse_cabecalho(titulo)
    tipo_declarado = tipo["tipo"] if tipo else ""
    resultado = {
        "titulo": titulo.strip(),
        "categoria_prevista": "",
        "tipo_declarado": tipo_declarado,
        "divergencia_com_tipo_declarado": False,
        "margem_top2": None,
        "revisar_manualmente": True,
        "motivo": "",
    }
    if not texto:
        resultado["motivo"] = "Titulo sem conteudo apos o prefixo"
        return resultado
    vetores = modelo.named_steps["tfidf"].transform([texto])
    if vetores.nnz == 0:
        resultado["motivo"] = "Nenhuma palavra conhecida pelo modelo; nao inferir categoria"
        return resultado
    decisao = modelo.named_steps["model"].decision_function(vetores)[0]
    indices = sorted(range(len(decisao)), key=lambda i: float(decisao[i]), reverse=True)
    classes = modelo.named_steps["model"].classes_
    primeira, segunda = indices[:2]
    classe = str(classes[primeira])
    margem = float(decisao[primeira] - decisao[segunda])
    discordou = tipo_declarado in CLASSES and tipo_declarado != classe
    resultado.update({
        "categoria_prevista": classe,
        "margem_top2": round(margem, 4),
        "divergencia_com_tipo_declarado": discordou,
        "revisar_manualmente": bool(discordou or margem < .20),
        "motivo": (
            "Divergencia entre autor e modelo; conferir diff" if discordou else
            "Predicao pouco separada da segunda opcao" if margem < .20 else
            "Predicao automatica; ainda pode estar incorreta"
        ),
    })
    return resultado


def analisar_lote(modelo, entrada, saida):
    entrada, saida = Path(entrada), Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Nao sobrescrever arquivo existente: " + str(saida))
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        if not leitor.fieldnames or "titulo" not in leitor.fieldnames:
            raise ValueError("CSV de entrada precisa ter coluna 'titulo'")
        previsoes = []
        for i, r in enumerate(leitor, 1):
            p = prever(modelo, r["titulo"] or "", r.get("descricao") or "")
            previsoes.append({"id": r.get("id") or str(i), **p})
    if not previsoes:
        raise ValueError("CSV vazio")
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as f:
        gravador = csv.DictWriter(f, fieldnames=list(previsoes[0]))
        gravador.writeheader()
        gravador.writerows(previsoes)
    return {"quantidade": len(previsoes), "para_revisao": sum(int(x["revisar_manualmente"]) for x in previsoes), "saida": str(saida)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="acao", required=True)
    treino = sub.add_parser("treinar", help="Treina modelo real SOMENTE em treino")
    treino.add_argument("--entrada", type=Path, default=ENTRADA)
    treino.add_argument("--banco", type=Path, default=BANCO)
    treino.add_argument("--saida", type=Path, default=DESTINO)
    analise = sub.add_parser("analisar", help="Classifica uma mensagem nova")
    analise.add_argument("--modelo", type=Path, default=DESTINO)
    analise.add_argument("--titulo", required=True)
    analise.add_argument("--descricao", default="")
    lote = sub.add_parser("lote", help="Classifica CSV com titulo")
    lote.add_argument("--modelo", type=Path, default=DESTINO)
    lote.add_argument("--entrada", type=Path, required=True)
    lote.add_argument("--saida", type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        if a.acao == "treinar":
            resposta = treinar(entrada=a.entrada, banco=a.banco, saida=a.saida)
        elif a.acao == "analisar":
            resposta = prever(carregar_modelo(a.modelo), a.titulo, a.descricao)
        else:
            resposta = analisar_lote(carregar_modelo(a.modelo), a.entrada, a.saida)
    except (ValueError, OSError, sqlite3.Error, csv.Error) as e:
        parser.error(str(e))
    print(json.dumps(resposta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
