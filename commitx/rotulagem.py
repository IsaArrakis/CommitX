"""Rotulagem humana de commits preparada para retomada.

python -m commitx.rotulagem iniciar
python -m commitx.rotulagem status
python -m commitx.rotulagem exportar --saida resultados/rotulagem/rotulados.csv
"""
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

CATEGORIAS = ("fix", "feat", "docs", "refactor", "test", "indeterminado", "fora_escopo")
CLAREZAS = ("vago", "parcial", "claro", "indeterminado")
OPCOES_CATEGORIA = {str(i): rotulo for i, rotulo in enumerate(CATEGORIAS, 1)}
OPCOES_CLAREZA = {str(i): rotulo for i, rotulo in enumerate(CLAREZAS, 1)}
FONTE = Path("resultados/preparacao-inicial/amostra_para_rotular.csv")
BANCO = Path("resultados/rotulagem/avaliacoes.sqlite3")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS avaliacoes (
 id TEXT PRIMARY KEY,
 categoria TEXT NOT NULL,
 clareza TEXT NOT NULL,
 observacao TEXT NOT NULL DEFAULT '',
 atualizado_em TEXT NOT NULL
)
"""

def abrir_banco(caminho):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(caminho)
    db.execute(ESQUEMA)
    return db

def ler_amostra(caminho):
    with Path(caminho).open(encoding="utf-8-sig", newline="") as arq:
        leitor = csv.DictReader(arq)
        campos = leitor.fieldnames or []
        obrigatorios = {"id", "titulo", "descricao", "grupo", "origem"}
        if not obrigatorios.issubset(campos):
            raise ValueError("Amostra não possui os campos exigidos: " +
                             ", ".join(sorted(obrigatorios - set(campos))))
        encontrados = set()
        registros = []
        for linha in leitor:
            uid = (linha.get("id") or "").strip()
            if not uid or uid in encontrados or not (linha.get("titulo") or "").strip():
                raise ValueError("Amostra com ID duplicado, vazio ou título vazio")
            encontrados.add(uid)
            registros.append(linha)
        return registros

def registrar(db, uid, categoria, clareza, observacao=""):
    if categoria not in CATEGORIAS:
        raise ValueError("Categoria inválida: " + str(categoria))
    if clareza not in CLAREZAS:
        raise ValueError("Clareza inválida: " + str(clareza))
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db:
        db.execute(
            """INSERT INTO avaliacoes(id, categoria, clareza, observacao, atualizado_em)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET categoria=excluded.categoria,
            clareza=excluded.clareza, observacao=excluded.observacao,
            atualizado_em=excluded.atualizado_em""",
            (uid, categoria, clareza, observacao, agora),
        )

def avaliados(db):
    return {
        uid: (categoria, clareza)
        for uid, categoria, clareza in db.execute(
            "SELECT id, categoria, clareza FROM avaliacoes"
        )
    }

def perguntar(rotulos, titulo, *, entrada=input, saida=print, sugestao=None):
    saida(titulo)
    saida(" | ".join(f"{chave}={nome}" for chave, nome in rotulos.items()))
    if sugestao in rotulos.values():
        saida(f"Sugestão: {sugestao}. Pressione ENTER para confirmar ou escolha outro número.")
    while True:
        valor = entrada("> ").strip().lower()
        if not valor and sugestao in rotulos.values():
            return sugestao
        if valor in ("q", "s"):
            return valor
        if valor in rotulos:
            return rotulos[valor]
        saida("Opção inválida. Digite um número, s para pular ou q para sair.")

def rotular(amostra, db, *, entrada=input, saida=print, revisar=False, limite=None,
           sugestor=None):
    anteriores = avaliados(db)
    salvos = 0
    for pos, linha in enumerate(amostra, start=1):
        uid = linha["id"]
        if uid in anteriores and not revisar:
            continue
        if limite is not None and salvos >= limite:
            break
        saida(f"\n[{pos}/{len(amostra)}] ID: {uid}")
        saida("Título: " + linha["titulo"])
        if (linha.get("descricao") or "").strip():
            saida("Corpo: " + linha["descricao"][:1200])
        saida("Origem: " + (linha.get("origem") or ""))
        proposta = sugestor.analisar(
            linha["titulo"], linha.get("descricao") or ""
        ) if sugestor else {}
        if proposta:
            tipo_ia = proposta.get("previsao_ml_categoria")
            saida("Modelo ML de demonstração (50 exemplos sintéticos): " +
                  (tipo_ia or "sem previsão"))
            if proposta.get("origem_categoria"):
                saida("Origem da sugestão de categoria: " +
                      proposta["origem_categoria"])
            if proposta.get("aviso_categoria"):
                saida("ATENÇÃO: " + proposta["aviso_categoria"])
            if proposta.get("origem_clareza"):
                saida("Origem da sugestão de clareza: " +
                      proposta["origem_clareza"])
            else:
                saida("Clareza: sem sugestão automática confiável neste momento.")
            for alerta in proposta.get("alertas", []):
                saida("Sinal de escrita: " + alerta)
        saida("O prefixo e as sugestões são hipóteses, não gabarito.")
        categoria = perguntar(
            OPCOES_CATEGORIA, "CATEGORIA:", entrada=entrada, saida=saida,
            sugestao=proposta.get("categoria"),
        )
        if categoria == "q":
            break
        if categoria == "s":
            continue
        clareza = perguntar(
            OPCOES_CLAREZA, "CLAREZA:", entrada=entrada, saida=saida,
            sugestao=proposta.get("clareza"),
        )
        if clareza == "q":
            break
        if clareza == "s":
            continue
        registrar(db, uid, categoria, clareza)
        salvos += 1
        saida("Salvo.")
    return salvos

def status(amostra, db):
    ids = {linha["id"] for linha in amostra}
    registros = [
        (categoria, clareza)
        for uid, categoria, clareza in db.execute(
            "SELECT id, categoria, clareza FROM avaliacoes"
        )
        if uid in ids
    ]
    return {
        "total": len(amostra),
        "avaliados": len(registros),
        "restantes": len(amostra) - len(registros),
        "categorias": dict(Counter(x[0] for x in registros)),
        "clareza": dict(Counter(x[1] for x in registros)),
    }

def exportar(amostra, db, destino):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    rotulos = {
        uid: (categoria, clareza, observacao, atualizado)
        for uid, categoria, clareza, observacao, atualizado in db.execute(
            "SELECT id, categoria, clareza, observacao, atualizado_em FROM avaliacoes"
        )
    }
    campos = list(amostra[0].keys()) if amostra else [
        "id", "titulo", "descricao", "grupo", "origem"
    ]
    extras = ["clareza", "observacao_humana", "avaliado_em"]
    campos = list(dict.fromkeys(campos + extras))
    quantidade = 0
    with destino.open("x", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=campos)
        escritor.writeheader()
        for linha in amostra:
            if linha["id"] not in rotulos:
                continue
            cat, cla, obs, data = rotulos[linha["id"]]
            novo = dict(linha)
            novo.update(categoria=cat, clareza=cla,
                        observacao_humana=obs, avaliado_em=data)
            escritor.writerow(novo)
            quantidade += 1
    return quantidade

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amostra", type=Path, default=FONTE)
    parser.add_argument("--banco", type=Path, default=BANCO)
    sub = parser.add_subparsers(dest="comando", required=True)
    iniciar = sub.add_parser("iniciar", help="Abre sessão de rotulagem, retomável.")
    iniciar.add_argument("--limite", type=int, default=20)
    iniciar.add_argument("--revisar", action="store_true")
    iniciar.add_argument(
        "--sem-sugestoes", action="store_true",
        help="Desabilita sugestões; volta à rotulagem inteiramente manual."
    )
    sub.add_parser("status", help="Mostra quantos já foram rotulados.")
    exp = sub.add_parser("exportar", help="Gera CSV com rótulos humanos.")
    exp.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        amostra = ler_amostra(args.amostra)
        with abrir_banco(args.banco) as db:
            if args.comando == "iniciar":
                if args.limite < 1:
                    parser.error("--limite deve ser positivo")
                try:
                    sugestor = None
                    if not args.sem_sugestoes:
                        from .sugestoes import Sugestor
                        sugestor = Sugestor(amostra, db)
                    n = rotular(
                        amostra, db, revisar=args.revisar,
                        limite=args.limite, sugestor=sugestor
                    )
                except (EOFError, KeyboardInterrupt):
                    print("\nSessão interrompida; rótulos anteriores preservados.")
                    n = 0
                print(f"Novos registros salvos nesta sessão: {n}")
            elif args.comando == "status":
                dados = status(amostra, db)
                for nome in ("total", "avaliados", "restantes"):
                    print(f"{nome}: {dados[nome]}")
                print("categorias:", dados["categorias"])
                print("clareza:", dados["clareza"])
            else:
                n = exportar(amostra, db, args.saida)
                print(f"Exportados {n} exemplos revisados em {args.saida}")
    except (ValueError, OSError, sqlite3.Error) as erro:
        parser.error(str(erro))

if __name__ == "__main__":
    main()
