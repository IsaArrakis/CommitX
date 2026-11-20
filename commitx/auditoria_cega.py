"""Auditoria cega de rotulos existentes sem alterar o banco principal.

A fila contem somente exemplos da particao de TREINO com rótulos existentes.
A rotulagem de auditoria deve usar outro SQLite e sempre --sem-sugestoes.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from .escrita import texto_modelo
from .treino_real import BANCO, ENTRADA, CATEGORIAS_VALIDAS, carregar_revisados

PREVISOES = Path("resultados/avaliacao-robusta-500-v1/previsoes_svm_palavras.csv")
AMOSTRA = Path("resultados/auditoria/rodada-01.csv")
RESUMO = Path("resultados/auditoria/rodada-01.json")
BANCO_AUDITORIA = Path("resultados/auditoria/avaliacoes-cegas.sqlite3")
COMPARACAO = Path("resultados/auditoria/comparacao-rodada-01.csv")


def _hash(uid, salt=""):
    return hashlib.sha256((salt + ":" + uid).encode("utf-8")).hexdigest()


def _ler_previsoes(arquivo):
    with Path(arquivo).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"id", "real", "previsto"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV de previsoes sem colunas exigidas")
        saida = {}
        for r in reader:
            uid = r["id"].strip()
            if uid in saida:
                raise ValueError("Previsoes com ID duplicado")
            saida[uid] = (r["real"], r["previsto"])
    return saida


def _ler_titulos(entrada, ids):
    dados = {}
    with Path(entrada).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        colunas = {"id", "titulo", "descricao", "repositorio", "particao", "origem"}
        if not colunas.issubset(reader.fieldnames or []):
            raise ValueError("CSV preparado nao contem colunas necessarias")
        for r in reader:
            uid = r["id"]
            if uid in ids:
                if uid in dados:
                    raise ValueError("ID duplicado no CSV preparado")
                dados[uid] = r
    return dados


def gerar(entrada=ENTRADA, banco=BANCO, previsoes=PREVISOES,
          amostra=AMOSTRA, resumo=RESUMO, quantidade=80):
    entrada, banco, previsoes, amostra, resumo = map(
        Path, (entrada, banco, previsoes, amostra, resumo)
    )
    if len({p.resolve() for p in (entrada, banco, previsoes, amostra, resumo)}) != 5:
        raise ValueError("Entradas e saidas devem ter caminhos diferentes")
    if amostra.exists() or resumo.exists():
        raise FileExistsError("Saida ja existe; escolha outro nome de arquivo")
    if quantidade < 5 or quantidade > 397:
        raise ValueError("--quantidade deve estar entre 5 e 397")

    revisados = {
        r["id"]: r for r in carregar_revisados(entrada, banco)
        if r["particao"] == "treino" and r["categoria"] in CATEGORIAS_VALIDAS
    }
    preds = _ler_previsoes(previsoes)
    candidatos = []
    for uid, registro in revisados.items():
        if uid not in preds:
            continue
        real, pred = preds[uid]
        if real != registro["categoria"]:
            raise ValueError("O rótulo de treino mudou desde a avaliacao cruzada")
        candidatos.append((uid, real, pred))
    if len(candidatos) < quantidade:
        raise ValueError(
            f"Somente {len(candidatos)} candidatos. Reduza --quantidade."
        )

    # Amostragem de auditoria, nao de estimativa de acuracia.
    # Reserva metade dos casos para erros; a outra para exemplos de controle
    # corretamente classificados, equilibrando a distribuicao por categoria.
    erros = defaultdict(list)
    acertos = defaultdict(list)
    for uid, real, pred in candidatos:
        (erros if real != pred else acertos)[real].append(uid)
    for bucket in (erros, acertos):
        for classe in bucket:
            bucket[classe].sort(key=lambda uid: _hash(uid, "prioridade"))

    escolhidos = []
    usados = set()
    classes = tuple(CATEGORIAS_VALIDAS)
    for alvo in (erros, acertos):
        quota = quantidade // 2 if alvo is erros else quantidade - (quantidade // 2)
        n = 0
        while n < quota:
            mudou = False
            for classe in classes:
                opcoes = alvo[classe]
                if opcoes and n < quota:
                    uid = opcoes.pop(0)
                    if uid not in usados:
                        usados.add(uid)
                        escolhidos.append(uid)
                        n += 1
                        mudou = True
            if not mudou:
                break
    if len(escolhidos) < quantidade:
        restantes = sorted(
            (uid for uid, _, _ in candidatos if uid not in usados),
            key=lambda uid: _hash(uid, "restantes"),
        )
        escolhidos.extend(restantes[: quantidade - len(escolhidos)])
    escolhidos.sort(key=lambda uid: _hash(uid, "embaralhar"))
    dados = _ler_titulos(entrada, set(escolhidos))
    if len(dados) != len(escolhidos):
        raise ValueError("Alguns IDs da auditoria nao aparecem no CSV preparado")

    registros = []
    for uid in escolhidos:
        r = dados[uid]
        if r["particao"] != "treino":
            raise ValueError("Tentativa de incluir particao reservada")
        # Remove o prefixo convencional para que ele nao entregue a resposta.
        # Nao revela os rotulos originais nem as previsoes.
        titulo = texto_modelo(r["titulo"], "")
        if not titulo:
            raise ValueError("Mensagem sem conteudo depois do prefixo")
        registros.append({
            "id": uid,
            "titulo": titulo,
            "descricao": r["descricao"],
            "grupo": uid,
            "origem": r.get("origem", ""),
            "repositorio": r["repositorio"],
            "particao": "treino",
        })
    amostra.parent.mkdir(parents=True, exist_ok=True)
    with amostra.open("x", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(
            f, fieldnames=["id", "titulo", "descricao", "grupo",
                           "origem", "repositorio", "particao"]
        )
        escritor.writeheader()
        escritor.writerows(registros)
    rel = {
        "quantidade": len(registros),
        "amostra": str(amostra),
        "origens": len({r["repositorio"] for r in registros}),
        "nota": (
            "Auditoria intencionalmente enriquecida com erros do modelo: "
            "nao e amostra representativa e nao mede acuracia. "
            "Os rotulos originais e previsoes estao ocultos no CSV; "
            "nao consultar os arquivos antigos durante a revisao. "
            "O corpo da mensagem pode conter pistas ou prefixos."
        ),
        "proximo_passo": (
            "python -m commitx.rotulagem --amostra " + str(amostra) +
            " --banco " + str(BANCO_AUDITORIA) +
            " lote --tamanho 20 --limite " + str(len(registros)) +
            " --sem-sugestoes"
        ),
    }
    resumo.parent.mkdir(parents=True, exist_ok=True)
    with resumo.open("x", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return rel


def comparar(entrada=AMOSTRA, banco_original=BANCO, banco_auditoria=BANCO_AUDITORIA,
             saida=COMPARACAO):
    entrada, banco_original, banco_auditoria, saida = map(
        Path, (entrada, banco_original, banco_auditoria, saida)
    )
    if saida.exists():
        raise FileExistsError("Comparacao ja existe. Use outro arquivo")
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        ids = [r["id"] for r in csv.DictReader(f)]
    if len(set(ids)) != len(ids):
        raise ValueError("Amostra de auditoria com IDs duplicados")
    def ler(banco):
        if not banco.is_file():
            raise ValueError("Banco nao encontrado: " + str(banco))
        uri = "file:" + banco.resolve().as_posix() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as con:
            return {
                uid: (categoria, clareza)
                for uid, categoria, clareza in con.execute(
                    "SELECT id, categoria, clareza FROM avaliacoes"
                )
            }
    originais = ler(banco_original)
    auditados = ler(banco_auditoria)
    faltantes = [uid for uid in ids if uid not in auditados]
    if faltantes:
        raise ValueError(
            f"Ainda faltam {len(faltantes)} itens da auditoria; conclua antes de comparar."
        )
    if any(uid not in originais for uid in ids):
        raise ValueError("Amostra com IDs sem rotulos originais")
    linhas = []
    for uid in ids:
        cat, cla = originais[uid]
        novo_cat, novo_cla = auditados[uid]
        linhas.append({
            "id": uid, "categoria_original": cat, "categoria_revisao": novo_cat,
            "clareza_original": cla, "clareza_revisao": novo_cla,
            "divergencia_categoria": int(cat != novo_cat),
            "divergencia_clareza": int(cla != novo_cla),
        })
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    return {
        "revisados": len(linhas),
        "divergencias_categoria": sum(r["divergencia_categoria"] for r in linhas),
        "divergencias_clareza": sum(r["divergencia_clareza"] for r in linhas),
        "saida": str(saida),
        "observacao": (
            "Divergencia nao implica que o rotulo original esteja errado. "
            "A reconciliacao exige uma segunda revisao; nenhum banco foi modificado."
        ),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="acao", required=True)
    g = sub.add_parser("gerar")
    g.add_argument("--entrada", type=Path, default=ENTRADA)
    g.add_argument("--banco", type=Path, default=BANCO)
    g.add_argument("--previsoes", type=Path, default=PREVISOES)
    g.add_argument("--amostra", type=Path, default=AMOSTRA)
    g.add_argument("--resumo", type=Path, default=RESUMO)
    g.add_argument("--quantidade", type=int, default=80)
    c = sub.add_parser("comparar")
    c.add_argument("--entrada", type=Path, default=AMOSTRA)
    c.add_argument("--banco-original", type=Path, default=BANCO)
    c.add_argument("--banco-auditoria", type=Path, default=BANCO_AUDITORIA)
    c.add_argument("--saida", type=Path, default=COMPARACAO)
    args = p.parse_args(argv)
    try:
        if args.acao == "gerar":
            rel = gerar(
                args.entrada, args.banco, args.previsoes, args.amostra,
                args.resumo, args.quantidade,
            )
        else:
            rel = comparar(
                args.entrada, args.banco_original, args.banco_auditoria,
                args.saida,
            )
    except (OSError, ValueError, sqlite3.Error, csv.Error) as erro:
        p.error(str(erro))
    print(json.dumps(rel, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
