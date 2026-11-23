"""Fila inteligente de commits para rotulagem humana, sem pseudo-rótulos.

Treino: mistura incerteza do classificador supervisionado, diversidade e exploração.
Validação: amostragem independente por hash, sem consultar qualquer classificador.
Teste: nunca selecionado. A saída é compatível com commitx.rotulagem lote.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import heapq
import json
from pathlib import Path

from sklearn.metrics.pairwise import cosine_similarity

from .escrita import texto_modelo
from .rotulagem_automatica import rotulos_humanos
from .treino_real import (
    BANCO, ENTRADA, CATEGORIAS_VALIDAS,
    MIN_TREINO_POR_CLASSE, carregar_revisados,
    construir_modelo, repositorios_da_linha,
)

SAIDA = Path("resultados/amostras/fila-inteligente-01.csv")
RESUMO = Path("resultados/amostras/fila-inteligente-01.json")
PARTICOES = ("treino", "validacao", "teste")
CAMPOS = (
    "id", "titulo", "descricao", "categoria", "clareza", "grupo",
    "origem", "repositorio", "particao", "tipo_declarado",
    "categoria_candidata", "hipotese_categoria", "incerteza_estimativa",
    "motivo_selecao", "sinal_texto_curto",
)
BUCKETS = (*CATEGORIAS_VALIDAS, "sem_prefixo")


def _hash(valor, semente):
    return int.from_bytes(
        hashlib.sha256(f"{semente}:{valor}".encode("utf-8")).digest()[:8],
        "big",
    )


def _fonte(linha):
    valor = (linha.get("origem") or "").lower()
    return "hf" if valor.startswith(("huggingface", "hf")) else "git"


def _chave_estrato(linha):
    prefixo = linha.get("categoria_candidata") or linha.get("tipo_declarado") or ""
    if prefixo not in CATEGORIAS_VALIDAS:
        prefixo = "sem_prefixo"
    return _fonte(linha), prefixo


def _ler_exclusoes(caminhos):
    ids = set()
    for caminho in caminhos:
        with Path(caminho).open(encoding="utf-8-sig", newline="") as arq:
            leitor = csv.DictReader(arq)
            if "id" not in (leitor.fieldnames or []):
                raise ValueError(f"Arquivo de exclusão sem coluna id: {caminho}")
            ids.update((linha.get("id") or "").strip() for linha in leitor)
    ids.discard("")
    return ids


def _pegar_pool(entrada, humanos, excluidos, particao, tamanho_pool, semente):
    """Seleção por hash em estratos, preservando memória limitada e deduplicação."""
    por_estrato = defaultdict(list)
    particoes_repos = defaultdict(set)
    totais = Counter()
    vistos_id = set()
    vistos_texto = set()
    capacidade = max(1, (tamanho_pool + 11) // 12)
    with Path(entrada).open(encoding="utf-8-sig", newline="") as arq:
        leitor = csv.DictReader(arq)
        obrigatorios = {
            "id", "titulo", "descricao", "grupo", "origem",
            "repositorio", "particao",
        }
        faltando = obrigatorios - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError("CSV preparado sem colunas: " + ", ".join(sorted(faltando)))
        for linha in leitor:
            totais["lidos"] += 1
            uid = (linha.get("id") or "").strip()
            titulo = (linha.get("titulo") or "").strip()
            p = (linha.get("particao") or "").strip()
            repos = repositorios_da_linha(linha.get("repositorio"))
            if p not in PARTICOES or not repos:
                totais["invalidos"] += 1
                continue
            for repo in repos:
                particoes_repos[repo].add(p)
            if p != particao or not uid or not titulo:
                continue
            if uid in humanos or uid in excluidos:
                totais["excluidos"] += 1
                continue
            if uid in vistos_id:
                totais["ids_repetidos"] += 1
                continue
            vistos_id.add(uid)
            digest_texto = hashlib.sha256(
                (titulo + "\n" + (linha.get("descricao") or "")).strip().casefold().encode("utf-8")
            ).hexdigest()
            if digest_texto in vistos_texto:
                totais["textos_repetidos"] += 1
                continue
            vistos_texto.add(digest_texto)
            totais["elegiveis"] += 1
            estrato = _chave_estrato(linha) if particao == "treino" else ("aleatorio", "geral")
            heap = por_estrato[estrato]
            prioridade = _hash(uid, semente)
            item = (-prioridade, uid, linha)
            limite = capacidade if particao == "treino" else tamanho_pool
            if len(heap) < limite:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    candidatos = [
        linha for heap in por_estrato.values()
        for _, _, linha in heap
    ]
    candidatos = [
        linha for linha in candidatos
        if not any(
            len(particoes_repos[repo]) > 1
            for repo in repositorios_da_linha(linha["repositorio"])
        )
    ]
    totais["pool"] = len(candidatos)
    return candidatos, totais


def _classificador_treino(entrada, banco):
    """Aprende apenas com os rótulos humanos de treino, nunca validação/teste."""
    registros = carregar_revisados(entrada, banco)
    treino = [
        r for r in registros if r["particao"] == "treino"
        and r["categoria"] in CATEGORIAS_VALIDAS
    ]
    contagem = Counter(r["categoria"] for r in treino)
    if not all(contagem[c] >= MIN_TREINO_POR_CLASSE for c in CATEGORIAS_VALIDAS):
        return None, treino, contagem
    modelo = construir_modelo()
    modelo.fit([r["texto"] for r in treino], [r["categoria"] for r in treino])
    return modelo, treino, contagem


def _pontuar(candidatos, modelo, treino):
    """Calcula incerteza de categoria e novidade lexical, sem atribuir gabarito."""
    if not candidatos:
        return {}
    if modelo is None:
        return {
            linha["id"]: ("", None, 0.0)
            for linha in candidatos
        }
    textos = [
        texto_modelo(r["titulo"], r.get("descricao") or "")
        for r in candidatos
    ]
    proba = modelo.predict_proba(textos)
    predicoes = modelo.predict(textos)
    tfidf = modelo.named_steps["tfidf"]
    vec_candidatos = tfidf.transform(textos)
    vec_treino = tfidf.transform([r["texto"] for r in treino])
    similaridades = cosine_similarity(vec_candidatos, vec_treino).max(axis=1)
    resultado = {}
    for linha, probabilidades, pred, semelhante in zip(
        candidatos, proba, predicoes, similaridades
    ):
        incerteza = 1.0 - float(max(probabilidades))
        novidade = 1.0 - float(semelhante)
        score = 0.75 * incerteza + 0.25 * novidade
        resultado[linha["id"]] = (str(pred), incerteza, score)
    return resultado


def _montar_fila(candidatos, pontuados, quantidade, por_repo, semente,
                 particao, tem_modelo):
    """Treino: 70% casos difíceis, 30% exploração; validação: só aleatório."""
    selecionados = []
    selecionados_ids = set()
    contagem_repo = Counter()
    contagem_motivo = Counter()
    contagem_predita = Counter()
    def colocar(linha, motivo):
        uid = linha["id"]
        repos = repositorios_da_linha(linha["repositorio"])
        if uid in selecionados_ids or any(contagem_repo[r] >= por_repo for r in repos):
            return False
        selecionados_ids.add(uid)
        for repo in repos:
            contagem_repo[repo] += 1
        contagem_motivo[motivo] += 1
        contagem_predita[pontuados[uid][0] or "sem_modelo"] += 1
        selecionados.append((linha, motivo))
        return True

    aleatorios = sorted(candidatos, key=lambda r: (_hash(r["id"], semente), r["id"]))
    if particao == "treino" and tem_modelo:
        buckets = defaultdict(list)
        for linha in candidatos:
            predicao, _, score = pontuados[linha["id"]]
            buckets[predicao].append((score, _hash(linha["id"], semente), linha))
        for bucket in buckets.values():
            bucket.sort(key=lambda x: (-x[0], x[1], x[2]["id"]))
        ordem = sorted(
            buckets, key=lambda classe: (contagem_predita[classe], classe)
        )
        indice = Counter()
        meta = min(quantidade, (quantidade * 7 + 9) // 10)
        while len(selecionados) < meta:
            adicionou = False
            for classe in ordem:
                itens = buckets[classe]
                while indice[classe] < len(itens):
                    linha = itens[indice[classe]][2]
                    indice[classe] += 1
                    if colocar(linha, "incerteza_diversidade"):
                        adicionou = True
                        break
                if len(selecionados) >= meta:
                    break
            if not adicionou:
                break
    elif particao == "treino":
        # Sem exemplos humanos suficientes, apenas diversidade por prefixo,
        # explicitamente não uma predição de categoria.
        buckets = defaultdict(list)
        for linha in aleatorios:
            buckets[_chave_estrato(linha)].append(linha)
        indice = Counter()
        meta = min(quantidade, (quantidade * 7 + 9) // 10)
        while len(selecionados) < meta:
            adicionou = False
            for estrato in sorted(buckets):
                itens = buckets[estrato]
                while indice[estrato] < len(itens):
                    linha = itens[indice[estrato]]
                    indice[estrato] += 1
                    if colocar(linha, "diversidade_sem_modelo"):
                        adicionou = True
                        break
                if len(selecionados) >= meta:
                    break
            if not adicionou:
                break
    for linha in aleatorios:
        if len(selecionados) >= quantidade:
            break
        colocar(linha, "exploracao_aleatoria" if particao == "treino" else "validacao_aleatoria")
    return selecionados, contagem_motivo, contagem_predita, contagem_repo


def gerar(entrada=ENTRADA, banco=BANCO, saida=SAIDA, resumo=RESUMO, *,
          quantidade=10, tamanho_pool=2400, por_repo=2, semente=42,
          particao="treino", excluir=()):
    entrada, banco, saida, resumo = map(Path, (entrada, banco, saida, resumo))
    if quantidade < 1 or tamanho_pool < quantidade or por_repo < 1:
        raise ValueError("Quantidade, tamanho do pool e limite por repo inválidos")
    if particao not in ("treino", "validacao"):
        raise ValueError("Somente treino ou validação são permitidos; teste permanece reservado")
    if not entrada.is_file():
        raise ValueError("CSV preparado não encontrado: " + str(entrada))
    caminhos = {p.resolve() for p in (entrada, saida, resumo)}
    if len(caminhos) != 3:
        raise ValueError("Entrada, saída e resumo devem ter caminhos diferentes")
    if saida.exists() or resumo.exists():
        raise FileExistsError("Arquivos de saída já existem. Use novos nomes.")
    humanos = rotulos_humanos(banco)
    excluidos = _ler_exclusoes(excluir)
    candidatos, totais = _pegar_pool(
        entrada, humanos, excluidos, particao, tamanho_pool, semente
    )
    modelo, treino, contagem_treino = (
        _classificador_treino(entrada, banco) if particao == "treino"
        else (None, [], Counter())
    )
    pontuados = _pontuar(candidatos, modelo, treino)
    selecionados, motivos, predicoes, repos = _montar_fila(
        candidatos, pontuados, quantidade, por_repo, semente, particao,
        modelo is not None
    )

    saida.parent.mkdir(parents=True, exist_ok=True)
    resumo.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=CAMPOS)
        escritor.writeheader()
        for linha, motivo in selecionados:
            predicao, incerteza, _ = pontuados[linha["id"]]
            titulo = linha["titulo"].strip()
            descricao = (linha.get("descricao") or "").strip()
            candidato = linha.get("categoria_candidata") or ""
            escritor.writerow({
                **{campo: linha.get(campo, "") for campo in CAMPOS},
                "categoria": "", "clareza": "",
                "categoria_candidata": candidato,
                "hipotese_categoria": predicao if particao == "treino" else "",
                "incerteza_estimativa": (
                    f"{incerteza:.4f}" if incerteza is not None else ""
                ),
                "motivo_selecao": motivo,
                "sinal_texto_curto": (
                    "sim" if len(titulo.split()) <= 3 and not descricao else "nao"
                ),
            })
    relatorio = {
        "particao": particao,
        "solicitados": quantidade,
        "selecionados": len(selecionados),
        "candidatos": dict(totais),
        "humanos_existentes": len(humanos),
        "excluidos_por_csv": len(excluidos),
        "modelo_categoria_usado": modelo is not None,
        "rotulos_treino_por_classe": dict(contagem_treino),
        "motivos": dict(motivos),
        "hipoteses_por_categoria": dict(predicoes),
        "repositorios_selecionados": len(repos),
        "aviso": (
            "NENHUM rótulo foi atribuído automaticamente. Hipóteses e incerteza "
            "não são gabarito nem probabilidades calibradas. A revisão precisa "
            "ser humana, preferencialmente cega (--sem-sugestoes). "
            "A validação é amostrada aleatoriamente e não usa o modelo; "
            "o teste nunca entra na fila. Use uma amostra de teste final "
            "separada, apenas depois de encerrar o desenvolvimento."
        ),
    }
    with resumo.open("x", encoding="utf-8") as arq:
        json.dump(relatorio, arq, indent=2, ensure_ascii=False)
        arq.write("\n")
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--resumo", type=Path, default=RESUMO)
    parser.add_argument("--quantidade", type=int, default=10)
    parser.add_argument("--tamanho-pool", type=int, default=2400)
    parser.add_argument("--por-repo", type=int, default=2)
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--particao", choices=("treino", "validacao"), default="treino")
    parser.add_argument(
        "--excluir", type=Path, action="append", default=[],
        help="CSV anterior com coluna id a excluir (pode repetir --excluir)",
    )
    args = parser.parse_args(argv)
    try:
        relatorio = gerar(
            args.entrada, args.banco, args.saida, args.resumo,
            quantidade=args.quantidade, tamanho_pool=args.tamanho_pool,
            por_repo=args.por_repo, semente=args.semente,
            particao=args.particao, excluir=args.excluir,
        )
    except (OSError, ValueError, csv.Error) as erro:
        parser.error(str(erro))
    print("Selecionados:", relatorio["selecionados"], "de", relatorio["solicitados"])
    print("Modelo para priorização:", "sim" if relatorio["modelo_categoria_usado"] else "não")
    print("Amostra:", args.saida)
    print("Relatório:", args.resumo)
    print(
        "Rotule humanamente: .venv/bin/python -m commitx.rotulagem "
        f"--amostra {args.saida} lote --tamanho 10 --limite 10 --sem-sugestoes"
    )


if __name__ == "__main__":
    main()
