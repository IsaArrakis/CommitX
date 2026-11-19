"""Avaliação supervisionada com rótulos humanos e validação por repositório.

Comandos:
  python -m commitx.avaliacao_real status
  python -m commitx.avaliacao_real avaliar --saida resultados/avaliacao-humana-01

Não utiliza pseudo-rótulos nem a partição de teste. O classificador é ajustado
somente com registros humanos da partição de treino, exclusivamente em memória.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sqlite3

from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score,
)

from .treino_real import (
    BANCO, ENTRADA, CATEGORIAS_VALIDAS, CLAREZAS_VALIDAS,
    carregar_revisados, construir_modelo, verificar, repositorios_da_linha,
)

DESTINO = Path("resultados/avaliacao-humana-01")
TAREFAS = (
    ("categoria", CATEGORIAS_VALIDAS),
    ("clareza", CLAREZAS_VALIDAS),
)
PARTICOES = ("treino", "validacao", "teste")


def validar_particoes(registros):
    """Impede vazamento entre repositórios e detecta IDs/partições incorretos."""
    ids = [r["id"] for r in registros]
    if len(ids) != len(set(ids)):
        raise ValueError("ID duplicado entre os commits revisados")
    invalidos = sorted({r["particao"] for r in registros if r["particao"] not in PARTICOES})
    if invalidos:
        raise ValueError("Partições inválidas: " + ", ".join(invalidos))
    if any(not r["repositorio"].strip() for r in registros):
        raise ValueError("Há commit revisado sem repositório; não é seguro avaliar")
    conjuntos = {
        p: set().union(*(
            repositorios_da_linha(r["repositorio"])
            for r in registros if r["particao"] == p
        ))
        for p in PARTICOES
    }
    return sorted(
        (conjuntos["treino"] & conjuntos["validacao"])
        | (conjuntos["treino"] & conjuntos["teste"])
        | (conjuntos["validacao"] & conjuntos["teste"])
    )


def _quantidades(registros, tarefa):
    return dict(sorted(Counter(r[tarefa] for r in registros).items()))


def _descricao_tarefa(registros, tarefa, classes, sobreposicoes):
    verificacao = verificar(registros, tarefa, classes)
    treino = verificacao["treino"]
    validacao = verificacao["validacao"]
    teste = verificacao["teste"]
    motivos = []
    if sobreposicoes:
        motivos.append("Repositórios presentes em partições diferentes")
    if verificacao["sobreposicoes_repositorio"]:
        motivos.append("Sobreposição de repositórios na tarefa")
    if verificacao["faltas_treino"]:
        motivos.append("Ainda faltam rótulos humanos no treino por classe")
    if verificacao["faltas_validacao"]:
        motivos.append("Ainda faltam rótulos humanos na validação por classe")
    return {
        "situacao": "bloqueada" if motivos else "pronta",
        "motivos": motivos,
        "classes": list(classes),
        "quantidades": {
            "treino": len(treino),
            "validacao": len(validacao),
            "teste_reservado": len(teste),
        },
        "treino_por_classe": _quantidades(treino, tarefa),
        "validacao_por_classe": _quantidades(validacao, tarefa),
        "faltam_treino": verificacao["faltas_treino"],
        "faltam_validacao": verificacao["faltas_validacao"],
        "repositorios_sobrepostos": verificacao["sobreposicoes_repositorio"],
    }, treino, validacao


def _metricas(reais, previstos, classes):
    return {
        "acuracia": float(accuracy_score(reais, previstos)),
        "macro_f1": float(f1_score(
            reais, previstos, labels=list(classes),
            average="macro", zero_division=0,
        )),
        "ordem_classes": list(classes),
        "matriz_confusao": confusion_matrix(
            reais, previstos, labels=list(classes)
        ).tolist(),
        "por_classe": {
            classe: {
                "precisao": float(valores["precision"]),
                "recall": float(valores["recall"]),
                "f1": float(valores["f1-score"]),
                "suporte": int(valores["support"]),
            }
            for classe, valores in classification_report(
                reais, previstos, labels=list(classes),
                output_dict=True, zero_division=0,
            ).items() if classe in classes
        },
    }


def _avaliar_tarefa(treino, validacao, tarefa, classes):
    textos_treino = [r["texto"] for r in treino]
    rotulos_treino = [r[tarefa] for r in treino]
    textos_validacao = [r["texto"] for r in validacao]
    reais = [r[tarefa] for r in validacao]

    # Pipeline TF-IDF é ajustado SOMENTE no treino humano desta tarefa.
    modelo = construir_modelo()
    modelo.fit(textos_treino, rotulos_treino)
    previstos = [str(r) for r in modelo.predict(textos_validacao)]

    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit(textos_treino, rotulos_treino)
    previstos_baseline = [str(r) for r in baseline.predict(textos_validacao)]

    previsoes = [
        {
            "id": r["id"],
            "repositorio": r["repositorio"],
            "particao": "validacao",
            "texto": r["texto"],
            "real": real,
            "previsto": previsto,
            "baseline": b,
            "correto": int(real == previsto),
        }
        for r, real, previsto, b
        in zip(validacao, reais, previstos, previstos_baseline)
    ]
    return {
        "modelo": _metricas(reais, previstos, classes),
        "baseline_maioria": _metricas(reais, previstos_baseline, classes),
        "previsoes": previsoes,
    }


def executar(entrada=ENTRADA, banco=BANCO, saida=DESTINO, apenas_status=False):
    """Avalia duas tarefas separadamente; não usa nem prevê a partição teste."""
    entrada, banco, saida = Path(entrada), Path(banco), Path(saida)
    registros = carregar_revisados(entrada, banco)
    sobreposicoes = validar_particoes(registros)
    relatorio = {
        "protocolo": "supervisionado-humano-validacao-v1",
        "fonte_rotulos": "somente SQLite de avaliações humanas",
        "base": str(entrada),
        "banco_humano": str(banco),
        "rotulos_humanos_encontrados": len(registros),
        "repositorios_sobrepostos": sobreposicoes,
        "tarefas": {},
        "importante": (
            "Modelos TF-IDF + regressão logística treinados exclusivamente com "
            "rótulos humanos da partição treino. Avaliados em validação de "
            "repositórios distintos. Nenhum registro de teste é usado para "
            "ajuste, seleção ou cálculo de métricas. Previsões do Ollama "
            "e rótulos automáticos não participam. Não é teste final."
        ),
    }
    saidas_tarefa = {}
    for tarefa, classes in TAREFAS:
        estado, treino, validacao = _descricao_tarefa(
            registros, tarefa, classes, sobreposicoes
        )
        relatorio["tarefas"][tarefa] = estado
        if not apenas_status and estado["situacao"] == "pronta":
            resultados = _avaliar_tarefa(treino, validacao, tarefa, classes)
            estado["situacao"] = "avaliada"
            estado["metricas"] = {
                "regressao_logistica": resultados["modelo"],
                "baseline_maioria": resultados["baseline_maioria"],
            }
            saidas_tarefa[tarefa] = resultados["previsoes"]

    if apenas_status:
        return relatorio

    # Não substitui arquivos anteriores, modelos ou bancos de dados.
    if saida.exists():
        raise FileExistsError(
            "A pasta de saída já existe. Use outro caminho em --saida: " + str(saida)
        )
    saida.mkdir(parents=True, exist_ok=False)
    with (saida / "relatorio.json").open("x", encoding="utf-8") as arq:
        json.dump(relatorio, arq, ensure_ascii=False, indent=2)
        arq.write("\n")
    for tarefa, linhas in saidas_tarefa.items():
        _escrever_csv(saida / f"previsoes_{tarefa}.csv", linhas, [
            "id", "repositorio", "particao", "texto", "real",
            "previsto", "baseline", "correto",
        ])
        _escrever_csv(saida / f"erros_{tarefa}.csv", [
            r for r in linhas if r["correto"] == 0
        ], [
            "id", "repositorio", "particao", "texto", "real",
            "previsto", "baseline", "correto",
        ])
        met = relatorio["tarefas"][tarefa]["metricas"]["regressao_logistica"]
        _escrever_csv(
            saida / f"matriz_{tarefa}.csv",
            [
                {"real": classe, **dict(zip(met["ordem_classes"], valores))}
                for classe, valores in zip(
                    met["ordem_classes"], met["matriz_confusao"]
                )
            ],
            ["real", *met["ordem_classes"]],
        )
    (saida / "resumo.md").write_text(_resumo_markdown(relatorio), encoding="utf-8")
    return relatorio


def _escrever_csv(caminho, linhas, colunas):
    with caminho.open("x", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas)


def _resumo_markdown(relatorio):
    linhas = [
        "# Avaliação supervisionada do CommitX",
        "",
        f"Rótulos humanos encontrados: **{relatorio['rotulos_humanos_encontrados']}**.",
        "",
        "| Tarefa | Situação | Treino | Validação | Teste reservado | Acurácia | Macro-F1 | Baseline macro-F1 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for tarefa, _ in TAREFAS:
        estado = relatorio["tarefas"][tarefa]
        quant = estado["quantidades"]
        metricas = estado.get("metricas")
        if metricas:
            ml = metricas["regressao_logistica"]
            base = metricas["baseline_maioria"]
            valores = (
                f"{ml['acuracia']:.3f}", f"{ml['macro_f1']:.3f}",
                f"{base['macro_f1']:.3f}",
            )
        else:
            valores = ("—", "—", "—")
        linhas.append(
            f"| {tarefa} | {estado['situacao']} | {quant['treino']} | "
            f"{quant['validacao']} | {quant['teste_reservado']} | "
            + " | ".join(valores) + " |"
        )
    linhas += ["", "## Diagnóstico por tarefa", ""]
    for tarefa, _ in TAREFAS:
        estado = relatorio["tarefas"][tarefa]
        linhas.append(f"### {tarefa}")
        if estado["motivos"]:
            for motivo in estado["motivos"]:
                linhas.append(f"- Impedimento: {motivo}.")
        if estado["faltam_treino"]:
            linhas.append(f"- Faltam no treino: {estado['faltam_treino']}.")
        if estado["faltam_validacao"]:
            linhas.append(f"- Faltam na validação: {estado['faltam_validacao']}.")
        if estado.get("metricas"):
            linhas.append("- Matriz: linhas = rótulos humanos reais; colunas = previsões.")
            linhas.append("- Verifique os arquivos erros e previsoes desta tarefa.")
        linhas.append("")
    linhas += [
        "## Limites metodológicos", "",
        "- Usa apenas rótulos humanos, nunca sugestões do Ollama ou prefixos como gabarito.",
        "- O TF-IDF é ajustado só no treino; o teste reservado permanece intocado.",
        "- A validação não é um teste externo final e pode ter amostra pequena.",
        "- As métricas não podem ser interpretadas como qualidade dos 100 mil commits.",
        "- Um baseline majoritário permite identificar ganhos aparentes enganosos.",
        "",
    ]
    return "\n".join(linhas)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=DESTINO)
    sub = parser.add_subparsers(dest="acao", required=True)
    sub.add_parser("status", help="Prévia de classes e rótulos necessários")
    sub.add_parser("avaliar", help="Treina em memória e avalia somente validação")
    args = parser.parse_args(argv)
    try:
        resultado = executar(
            args.entrada, args.banco, args.saida,
            apenas_status=args.acao == "status",
        )
    except (OSError, ValueError, sqlite3.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
