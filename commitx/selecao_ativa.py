"""Seleção estratificada e determinística de commits para revisão humana.

Não transforma previsão em rótulo. Mantém treino, validação e teste isolados.
"""
import argparse
from collections import Counter
import csv
import hashlib
import heapq
import json
from pathlib import Path

from .rotulagem_automatica import rotulos_humanos

ORIGEM = Path("resultados/triagem/todos_sugeridos.csv")
SAIDA = Path("resultados/amostras/rodada1.csv")
RELATORIO = Path("resultados/amostras/rodada1.json")
BANCO = Path("resultados/rotulagem/avaliacoes.sqlite3")
CLASSES = ("fix", "feat", "docs", "refactor", "test", "sem_previsao")
FONTES = ("hf", "git")
PRIORIDADES = ("alta", "normal")
CAMPOS = [
    "id", "titulo", "descricao", "categoria", "grupo", "origem",
    "repositorio", "particao", "tipo_declarado", "categoria_candidata",
    "categoria_sugerida", "clareza_sugerida", "fonte_categoria",
    "prioridade_revisao",
]


def identidade(texto, semente):
    return int.from_bytes(
        hashlib.sha256(f"{semente}:{texto}".encode("utf-8")).digest()[:8],
        "big",
    )


def selecionar(entrada=ORIGEM, saida=SAIDA, resumo=RELATORIO, banco=BANCO,
              quantidade=300, particao="treino", por_repo=35, semente=42):
    entrada, saida, resumo = map(Path, (entrada, saida, resumo))
    if quantidade < 1 or por_repo < 1:
        raise ValueError("Quantidade e limite por repositório devem ser positivos")
    if particao not in ("treino", "validacao", "teste"):
        raise ValueError("Partição inválida")
    if not entrada.is_file():
        raise ValueError("Arquivo de triagem inexistente: " + str(entrada))
    if len({entrada.resolve(), saida.resolve(), resumo.resolve()}) != 3:
        raise ValueError("Entrada, saída e relatório devem ser arquivos distintos")
    if saida.exists() or resumo.exists():
        raise FileExistsError("Saída já existe. Escolha outro nome para não sobrescrever.")
    avaliados = rotulos_humanos(banco)
    grupos = {
        (prioridade, fonte, classe): []
        for prioridade in PRIORIDADES for fonte in FONTES for classe in CLASSES
    }
    contadores = Counter()
    with entrada.open(encoding="utf-8-sig", newline="") as arq:
        reader = csv.DictReader(arq)
        obrigatorios = {"id", "titulo", "descricao", "grupo", "origem",
                        "particao", "categoria_sugerida", "prioridade_revisao"}
        faltantes = obrigatorios - set(reader.fieldnames or ())
        if faltantes:
            raise ValueError("Campos ausentes: " + ", ".join(sorted(faltantes)))
        for linha in reader:
            contadores["lidos"] += 1
            uid = (linha.get("id") or "").strip()
            if not uid or not (linha.get("titulo") or "").strip():
                continue
            if (linha.get("particao") or "") != particao:
                continue
            if uid in avaliados or linha.get("status") == "revisado_humano":
                contadores["ja_rotulados"] += 1
                continue
            classe = linha.get("categoria_sugerida", "")
            if classe not in CLASSES:
                classe = "sem_previsao"
            fonte = "hf" if (linha.get("origem") or "").startswith("huggingface:") else "git"
            prioridade = "alta" if linha.get("prioridade_revisao") == "alta" else "normal"
            chave = (prioridade, fonte, classe)
            score = identidade(uid, semente)
            item = (-score, uid, linha)
            heap = grupos[chave]
            # Mantém somente os melhores candidatos de cada estrato; memória limitada.
            if len(heap) < quantidade:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
            contadores["elegiveis"] += 1

    for k, heap in grupos.items():
        grupos[k] = [row for _, _, row in sorted(heap, key=lambda item: -item[0])]

    selecionadas = []
    selecionados_ids = set()
    por_repositorio = Counter()
    por_estrato = Counter()
    # Mistura prioridades, origens e classes; 60% casos difíceis, 40% auditoria.
    meta_alta = (quantidade * 3 + 4) // 5
    indices = Counter()
    def consumir(prioridade, meta):
        adicionadas = 0
        while adicionadas < meta and len(selecionadas) < quantidade:
            houve_progresso = False
            for classe in CLASSES:
                for fonte in FONTES:
                    chave = (prioridade, fonte, classe)
                    candidatos = grupos[chave]
                    while indices[chave] < len(candidatos):
                        linha = candidatos[indices[chave]]
                        indices[chave] += 1
                        uid = linha["id"]
                        repo = linha.get("repositorio") or linha.get("origem") or "indefinido"
                        if uid in selecionados_ids or por_repositorio[repo] >= por_repo:
                            continue
                        selecionados_ids.add(uid)
                        por_repositorio[repo] += 1
                        por_estrato["/".join(chave)] += 1
                        selecionadas.append(linha)
                        adicionadas += 1
                        houve_progresso = True
                        break
                    if adicionadas >= meta or len(selecionadas) >= quantidade:
                        break
                if adicionadas >= meta or len(selecionadas) >= quantidade:
                    break
            if not houve_progresso:
                break

    consumir("alta", meta_alta)
    consumir("normal", quantidade - len(selecionadas))
    # Completa a amostra com o que houver, sem ultrapassar o limite por repo.
    if len(selecionadas) < quantidade:
        consumir("alta", quantidade - len(selecionadas))
    if len(selecionadas) < quantidade:
        consumir("normal", quantidade - len(selecionadas))

    saida.parent.mkdir(parents=True, exist_ok=True)
    resumo.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as arq:
        writer = csv.DictWriter(arq, fieldnames=CAMPOS)
        writer.writeheader()
        for linha in selecionadas:
            writer.writerow({
                **{campo: linha.get(campo, "") for campo in CAMPOS},
                "categoria": "",  # Rótulo sempre requer decisão humana.
                "categoria_candidata": linha.get("categoria_sugerida") or "",
            })
    resultado = {
        "particao": particao,
        "solicitados": quantidade,
        "selecionados": len(selecionadas),
        "candidatos": dict(contadores),
        "estratos": dict(por_estrato),
        "repositorios": len(por_repositorio),
        "aviso": (
            "Seleção baseada em discordância e diversidade, não em incerteza calibrada. "
            "Previsões não são rótulos. Para avaliação final, reserve a partição teste e "
            "rotule-a sem mostrar sugestões (--sem-sugestoes)."
        ),
    }
    with resumo.open("x", encoding="utf-8") as arq:
        json.dump(resultado, arq, ensure_ascii=False, indent=2)
        arq.write("\n")
    return resultado


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ORIGEM)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--resumo", type=Path, default=RELATORIO)
    parser.add_argument("--banco-humano", type=Path, default=BANCO)
    parser.add_argument("--quantidade", type=int, default=300)
    parser.add_argument("--particao", choices=("treino", "validacao", "teste"), default="treino")
    parser.add_argument("--por-repo", type=int, default=35)
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        resultado = selecionar(
            entrada=args.entrada, saida=args.saida, resumo=args.resumo,
            banco=args.banco_humano, quantidade=args.quantidade,
            particao=args.particao, por_repo=args.por_repo, semente=args.semente,
        )
    except (OSError, ValueError, csv.Error) as erro:
        parser.error(str(erro))
    print(f"Selecionados: {resultado['selecionados']}/{resultado['solicitados']}")
    print("Repositórios:", resultado["repositorios"])
    print("Amostra:", args.saida)
    print("Relatório:", args.resumo)


if __name__ == "__main__":
    main()
