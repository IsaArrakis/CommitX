"""Acompanhamento dos marcos de rotulagem humana do CommitX.

python -m commitx.plano_rotulagem status
python -m commitx.plano_rotulagem --json status

Somente leitura. Não treina, não classifica e não modifica o SQLite.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from .avaliacao_real import validar_particoes
from .treino_real import (
    BANCO, ENTRADA, CATEGORIAS_VALIDAS, CLAREZAS_VALIDAS,
    carregar_revisados, verificar,
)

MARCOS = (150, 250, 500, 1000)
META_PRINCIPAL = 500
PARTICOES = ("treino", "validacao", "teste")


def _tarefa(registros, campo, classes, sobrepostos):
    verificar_tarefa = verificar(registros, campo, classes)
    treino = verificar_tarefa["treino"]
    validacao = verificar_tarefa["validacao"]
    teste = verificar_tarefa["teste"]
    motivo = []
    if sobrepostos or verificar_tarefa["sobreposicoes_repositorio"]:
        motivo.append("Há repositórios sobrepostos nas partições")
    if verificar_tarefa["faltas_treino"]:
        motivo.append("Faltam exemplos humanos de treino em algumas classes")
    if verificar_tarefa["faltas_validacao"]:
        motivo.append("Faltam exemplos humanos de validação em algumas classes")
    return {
        "situacao": "pronta" if not motivo else "bloqueada",
        "motivos": motivo,
        "treino": len(treino),
        "validacao": len(validacao),
        "teste_reservado": len(teste),
        "treino_por_classe": dict(sorted(Counter(r[campo] for r in treino).items())),
        "validacao_por_classe": dict(sorted(Counter(r[campo] for r in validacao).items())),
        "faltam_treino": verificar_tarefa["faltas_treino"],
        "faltam_validacao": verificar_tarefa["faltas_validacao"],
    }


def resumo(entrada=ENTRADA, banco=BANCO):
    """Contabiliza humanos identificados na base preparada; não usa rótulos de IA."""
    entrada, banco = Path(entrada), Path(banco)
    registros = carregar_revisados(entrada, banco)
    sobrepostos = validar_particoes(registros)
    total = len(registros)
    proximo = next((marco for marco in MARCOS if total < marco), None)
    por_particao = dict(sorted(Counter(r["particao"] for r in registros).items()))
    return {
        "protocolo": "progresso-rotulagem-humana-500-v1",
        "origem": "SQLite de avaliações humanas associado à base preparada",
        "observacao_procedencia": (
            "O SQLite identifica rótulos registrados por humanos, mas não comprova "
            "revisão cega ou independente. Não trate como gabarito sem auditoria."
        ),
        "total_rotulado": total,
        "meta_principal": META_PRINCIPAL,
        "percentual_meta": round(100.0 * min(total, META_PRINCIPAL) / META_PRINCIPAL, 1),
        "faltam_ate_500": max(META_PRINCIPAL - total, 0),
        "proximo_marco": proximo,
        "faltam_proximo_marco": max(proximo - total, 0) if proximo else 0,
        "marcos": [
            {
                "meta": marco,
                "atingido": total >= marco,
                "restantes": max(marco - total, 0),
            }
            for marco in MARCOS
        ],
        "revisoes_por_particao": por_particao,
        "repositorios_sobrepostos": sobrepostos,
        "tarefas": {
            "categoria": _tarefa(
                registros, "categoria", CATEGORIAS_VALIDAS, sobrepostos
            ),
            "clareza": _tarefa(
                registros, "clareza", CLAREZAS_VALIDAS, sobrepostos
            ),
        },
        "orientacao": (
            "Priorize pequenos lotes de treino e confira os rótulos; não force "
            "classes para atingir mínimos. Validação aleatória e teste reservado "
            "não entram no treino. Reavaliar em marcos pré-definidos, sem usar "
            "a validação para escolher repetidamente hiperparâmetros."
        ),
    }


def _mostrar_texto(info):
    print("CommitX — acompanhamento de rótulos humanos")
    print(f"Total: {info['total_rotulado']} / {info['meta_principal']} "
          f"({info['percentual_meta']:.1f}%)")
    print(f"Faltam para 500: {info['faltam_ate_500']}")
    if info["proximo_marco"] is not None:
        print(f"Próximo marco: {info['proximo_marco']} "
              f"({info['faltam_proximo_marco']} restantes)")
    print("Partições:", info["revisoes_por_particao"])
    if info["repositorios_sobrepostos"]:
        print("ALERTA: repositórios sobrepostos:", info["repositorios_sobrepostos"])
    for nome, estado in info["tarefas"].items():
        print(f"\n{nome}: {estado['situacao']} "
              f"({estado['treino']} treino / {estado['validacao']} validação / "
              f"{estado['teste_reservado']} teste reservado)")
        print("  treino por classe:", estado["treino_por_classe"])
        if estado["faltam_treino"]:
            print("  faltam treino:", estado["faltam_treino"])
        if estado["faltam_validacao"]:
            print("  faltam validação:", estado["faltam_validacao"])
    print("\nNota: não é necessário rotular os 500 de uma vez. "
          "Os exemplos de teste permanecem reservados.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--json", action="store_true", help="Mostrar relatório em JSON")
    sub = parser.add_subparsers(dest="acao", required=True)
    sub.add_parser("status", help="Mostrar progresso e lacunas por classe")
    args = parser.parse_args(argv)
    try:
        dados = resumo(args.entrada, args.banco)
    except (OSError, ValueError) as erro:
        parser.error(str(erro))
    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
    else:
        _mostrar_texto(dados)


if __name__ == "__main__":
    main()
