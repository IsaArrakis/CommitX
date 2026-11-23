"""Interface compativel para auditoria cega de rotulos.

A implementacao vive em auditoria_cega.py. Mantemos os comandos publicados:
  python -m commitx.auditoria_rotulos preparar --quantidade 40
  python -m commitx.auditoria_rotulos conferir

Nao altera o banco original. Somente registros de treino podem entrar.
"""
import argparse
import csv
import json
from pathlib import Path
import sqlite3

from .auditoria_cega import (
    gerar, comparar, PREVISOES, AMOSTRA, RESUMO, BANCO_AUDITORIA
)
from .treino_real import ENTRADA, BANCO


def _validar_previsoes_treino(entrada, previsoes):
    """Rejeita qualquer previsao associada a validacao/teste ou ID ausente."""
    with Path(entrada).open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not {"id", "particao"}.issubset(leitor.fieldnames or []):
            raise ValueError("CSV preparado sem id e particao")
        particoes = {}
        for linha in leitor:
            uid = linha["id"]
            if uid in particoes:
                raise ValueError("ID duplicado na base preparada")
            particoes[uid] = linha["particao"]
    with Path(previsoes).open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not {"id", "real", "previsto"}.issubset(leitor.fieldnames or []):
            raise ValueError("CSV de previsoes incompleto")
        ids = set()
        for linha in leitor:
            uid = linha["id"]
            if uid in ids:
                raise ValueError("Previsoes com ID duplicado")
            ids.add(uid)
            if uid not in particoes:
                raise ValueError("Previsao sem registro preparado: " + uid)
            if particoes[uid] != "treino":
                raise ValueError("Previsoes incluem particao reservada: " + uid)


def preparar(entrada=ENTRADA, previsoes=PREVISOES, banco_original=BANCO,
             fila=AMOSTRA, resumo=RESUMO, quantidade=40):
    _validar_previsoes_treino(entrada, previsoes)
    return gerar(
        entrada=entrada, banco=banco_original, previsoes=previsoes,
        amostra=fila, resumo=resumo, quantidade=quantidade,
    )


def conferir(fila=AMOSTRA, banco_original=BANCO,
             banco_segunda=BANCO_AUDITORIA,
             saida=Path("resultados/auditoria/conferencia-01")):
    saida = Path(saida)
    if saida.exists():
        raise FileExistsError("Pasta de conferencia ja existe: " + str(saida))
    # O comparador subjacente escreve CSV, nao uma pasta.
    csv_saida = saida / "divergencias.csv"
    # Compara em diretorio temporario, de modo que falhas nao criem saida parcial.
    import tempfile
    with tempfile.TemporaryDirectory() as pasta:
        rel = comparar(
            entrada=fila, banco_original=banco_original,
            banco_auditoria=banco_segunda,
            saida=Path(pasta) / "divergencias.csv",
        )
        saida.mkdir(parents=True, exist_ok=False)
        csv_saida.write_bytes((Path(pasta) / "divergencias.csv").read_bytes())
    resultado = {
        "total_reavaliado": rel["revisados"],
        "divergencias_categoria": rel["divergencias_categoria"],
        "divergencias_clareza": rel["divergencias_clareza"],
        "arquivo_divergencias": str(csv_saida),
        "aviso": (
            "Discordancia nao comprova erro do rotulo original. "
            "Reconciliar casos com diff. Banco original inalterado."
        ),
    }
    (saida / "resumo.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resultado


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="acao", required=True)
    g = sub.add_parser("preparar")
    g.add_argument("--entrada", type=Path, default=ENTRADA)
    g.add_argument("--previsoes", type=Path, default=PREVISOES)
    g.add_argument("--banco-original", type=Path, default=BANCO)
    g.add_argument("--fila", type=Path, default=AMOSTRA)
    g.add_argument("--resumo", type=Path, default=RESUMO)
    g.add_argument("--quantidade", type=int, default=40)
    c = sub.add_parser("conferir")
    c.add_argument("--fila", type=Path, default=AMOSTRA)
    c.add_argument("--banco-original", type=Path, default=BANCO)
    c.add_argument("--banco-segunda", type=Path, default=BANCO_AUDITORIA)
    c.add_argument("--saida", type=Path, default=Path("resultados/auditoria/conferencia-01"))
    args = parser.parse_args(argv)
    try:
        if args.acao == "preparar":
            resultado = preparar(args.entrada, args.previsoes,
                                 args.banco_original, args.fila,
                                 args.resumo, args.quantidade)
        else:
            resultado = conferir(args.fila, args.banco_original,
                                 args.banco_segunda, args.saida)
    except (OSError, ValueError, sqlite3.Error, csv.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
