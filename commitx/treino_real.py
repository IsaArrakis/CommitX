"""Treino supervisionado apenas com rótulos humanos, com validação por repositório.

Uso:
python -m commitx.treino_real status
python -m commitx.treino_real treinar
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sqlite3

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from .escrita import texto_modelo
from .rotulagem import CATEGORIAS, CLAREZAS

ENTRADA = Path("resultados/preparacao-inicial/commits_preparados.csv")
BANCO = Path("resultados/rotulagem/avaliacoes.sqlite3")
DESTINO = Path("resultados/modelos-reais")
CATEGORIAS_VALIDAS = ("fix", "feat", "docs", "refactor", "test")
CLAREZAS_VALIDAS = ("vago", "parcial", "claro")
MIN_TREINO_POR_CLASSE = 5
MIN_VALIDACAO_POR_CLASSE = 2


def carregar_revisados(entrada=ENTRADA, banco=BANCO):
    entrada, banco = Path(entrada), Path(banco)
    if not entrada.is_file():
        raise ValueError("CSV preparado não encontrado: " + str(entrada))
    if not banco.is_file():
        return []
    with sqlite3.connect(f"file:{banco.resolve().as_posix()}?mode=ro", uri=True) as con:
        humanos = {
            uid: (categoria, clareza)
            for uid, categoria, clareza in con.execute(
                "SELECT id, categoria, clareza FROM avaliacoes"
            )
        }
    revisados = []
    with entrada.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        exigidos = {"id", "titulo", "descricao", "repositorio", "particao"}
        if not exigidos.issubset(leitor.fieldnames or []):
            raise ValueError("CSV sem campos essenciais: " +
                             ", ".join(sorted(exigidos - set(leitor.fieldnames or []))))
        for linha in leitor:
            rotulos = humanos.get(linha["id"])
            if rotulos is None:
                continue
            categoria, clareza = rotulos
            if categoria not in CATEGORIAS or clareza not in CLAREZAS:
                raise ValueError("Rótulo humano inválido no banco de avaliações")
            titulo = linha["titulo"]
            if not titulo.strip():
                continue
            try:
                texto = texto_modelo(titulo, linha.get("descricao") or "")
            except (TypeError, ValueError):
                continue
            if not texto:
                continue
            revisados.append({
                "id": linha["id"],
                "repositorio": linha["repositorio"],
                "particao": linha["particao"],
                "texto": texto,
                "categoria": categoria,
                "clareza": clareza,
            })
    return revisados


def distribuição(linhas, classe):
    return {
        nome: dict(Counter(r[classe] for r in linhas if r[classe] in nomes))
        for nome, nomes in (
            ("categoria", CATEGORIAS_VALIDAS),
            ("clareza", CLAREZAS_VALIDAS),
        )
    }[classe]


def verificar(revisados, coluna, classes):
    treino = [
        r for r in revisados
        if r["particao"] == "treino" and r[coluna] in classes
    ]
    validacao = [
        r for r in revisados
        if r["particao"] == "validacao" and r[coluna] in classes
    ]
    teste = [
        r for r in revisados
        if r["particao"] == "teste" and r[coluna] in classes
    ]
    ct = Counter(r[coluna] for r in treino)
    cv = Counter(r[coluna] for r in validacao)
    faltas_treino = {
        c: MIN_TREINO_POR_CLASSE - ct[c]
        for c in classes if ct[c] < MIN_TREINO_POR_CLASSE
    }
    faltas_validacao = {
        c: MIN_VALIDACAO_POR_CLASSE - cv[c]
        for c in classes if cv[c] < MIN_VALIDACAO_POR_CLASSE
    }
    # Nenhum repositório pode atravessar treino / validação / teste.
    por_particao = {}
    for nome, linhas in (("treino", treino), ("validacao", validacao), ("teste", teste)):
        por_particao[nome] = {r["repositorio"] for r in linhas}
    sobreposicoes = sorted(
        (por_particao["treino"] & por_particao["validacao"])
        | (por_particao["treino"] & por_particao["teste"])
        | (por_particao["validacao"] & por_particao["teste"])
    )
    return {
        "treino": treino, "validacao": validacao, "teste": teste,
        "faltas_treino": faltas_treino,
        "faltas_validacao": faltas_validacao,
        "sobreposicoes_repositorio": sobreposicoes,
    }


def construir_modelo():
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            strip_accents="unicode", ngram_range=(1, 2),
            sublinear_tf=True, min_df=1
        )),
        ("classificador", LogisticRegression(
            max_iter=1000, random_state=42, class_weight="balanced"
        )),
    ])


def treinar_tarefa(revisados, coluna, classes, destino):
    verificacao = verificar(revisados, coluna, classes)
    treino, validacao = verificacao["treino"], verificacao["validacao"]
    relatorio = {
        "tarefa": coluna,
        "quantidades": {
            "treino": len(treino),
            "validacao": len(validacao),
            "teste_reservado": len(verificacao["teste"]),
        },
        "treino_por_classe": dict(Counter(r[coluna] for r in treino)),
        "validacao_por_classe": dict(Counter(r[coluna] for r in validacao)),
        "faltam_treino": verificacao["faltas_treino"],
        "faltam_validacao": verificacao["faltas_validacao"],
        "repositorios_sobrepostos": verificacao["sobreposicoes_repositorio"],
        "modelo_treinado": False,
        "validacao_realizada": False,
    }
    if verificacao["sobreposicoes_repositorio"]:
        relatorio["observacao"] = "Repositórios sobrepostos: revisão necessária antes de treinar"
        return relatorio
    if verificacao["faltas_treino"]:
        relatorio["observacao"] = "Ainda faltam rótulos humanos nas classes de treinamento"
        return relatorio
    modelo = construir_modelo()
    modelo.fit([r["texto"] for r in treino], [r[coluna] for r in treino])
    relatorio["modelo_treinado"] = True
    # Salva somente um modelo que já foi treinado em rótulos humanos.
    from joblib import dump
    caminho = Path(destino) / f"{coluna}.joblib"
    dump(modelo, caminho)
    relatorio["modelo_salvo"] = str(caminho)
    if verificacao["faltas_validacao"]:
        relatorio["observacao"] = (
            "Modelo exploratório treinado. Ainda faltam rótulos de validação "
            "para aferir desempenho; não utilize resultados como gabarito."
        )
        return relatorio

    reais = [r[coluna] for r in validacao]
    previstos = [str(p) for p in modelo.predict([r["texto"] for r in validacao])]
    relatorio["validacao_realizada"] = True
    relatorio["metricas_validacao"] = {
        "acuracia": float(accuracy_score(reais, previstos)),
        "macro_f1": float(f1_score(
            reais, previstos, labels=list(classes),
            average="macro", zero_division=0
        )),
        "matriz_confusao": confusion_matrix(
            reais, previstos, labels=list(classes)
        ).tolist(),
        "ordem_classes": list(classes),
    }
    relatorio["observacao"] = (
        "Validação independente por repositório, porém amostra ainda pequena. "
        "Partição teste permaneceu intocada."
    )
    return relatorio


def executar(entrada=ENTRADA, banco=BANCO, destino=DESTINO, apenas_status=False):
    destino = Path(destino)
    revisados = carregar_revisados(entrada, banco)
    resumo = {
        "rotulos_humanos_encontrados": len(revisados),
        "base": str(entrada),
        "tarefas": {},
        "importante": (
            "Somente rótulos humanos. Prefixos e previsões automáticas são ignorados. "
            "Indeterminado e fora_escopo não entram nas cinco classes. "
            "A partição de teste não é usada para ajustar ou escolher modelos."
        ),
    }
    if apenas_status:
        for coluna, classes in (
            ("categoria", CATEGORIAS_VALIDAS), ("clareza", CLAREZAS_VALIDAS)
        ):
            v = verificar(revisados, coluna, classes)
            resumo["tarefas"][coluna] = {
                "treino": dict(Counter(r[coluna] for r in v["treino"])),
                "validacao": dict(Counter(r[coluna] for r in v["validacao"])),
                "teste_reservado": len(v["teste"]),
                "faltam_treino": v["faltas_treino"],
                "faltam_validacao": v["faltas_validacao"],
                "repositorios_sobrepostos": v["sobreposicoes_repositorio"],
            }
        return resumo
    destino.mkdir(parents=True, exist_ok=True)
    for coluna, classes in (
        ("categoria", CATEGORIAS_VALIDAS), ("clareza", CLAREZAS_VALIDAS)
    ):
        resumo["tarefas"][coluna] = treinar_tarefa(
            revisados, coluna, classes, destino
        )
    caminho = destino / "relatorio_treinamento.json"
    with caminho.open("x", encoding="utf-8") as arq:
        json.dump(resumo, arq, indent=2, ensure_ascii=False)
        arq.write("\n")
    return resumo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=DESTINO)
    sub = parser.add_subparsers(dest="acao", required=True)
    sub.add_parser("status")
    sub.add_parser("treinar")
    args = parser.parse_args(argv)
    try:
        resultado = executar(
            args.entrada, args.banco, args.saida, apenas_status=args.acao == "status"
        )
    except (OSError, ValueError, sqlite3.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
