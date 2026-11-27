"""Valida a expansão e isola grupos relacionados aos conjuntos reservados."""
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from pathlib import Path
import re

from .escrita import texto_modelo
from .modelo_v13 import normalizar
from .v12_final import carregar_gold, CLASSES

EXPANSAO = Path("resultados/expansao-v13/expansao-v13-treino-bilingue-909.csv")
ORIGENS = {
    "original_pseudorrotulado": "chatgpt_pseudorotulo",
    "traducao_ia": "chatgpt_traducao_pseudorotulo",
    "sintetico_ia": "chatgpt_sintetico",
}
COLUNAS = {
    "id", "titulo", "grupo", "origem", "repositorio", "particao", "categoria_ia",
    "origem_rotulo", "revisao_humana", "usar_treino_experimental", "motivo_exclusao",
    "idioma", "tipo_aumento", "id_origem", "titulo_origem",
}


@dataclass(frozen=True)
class Registro:
    id: str
    titulo: str
    categoria: str
    origem: str
    idioma: str


def _titulo(titulo):
    return normalizar(texto_modelo(titulo)) if titulo.strip() else ""


def _repositorios(texto):
    return {r.strip().casefold().removesuffix("/") for r in texto.split(",") if r.strip()}


def _identificadores(linha):
    grupo = linha["grupo"].strip().casefold()
    sha = grupo.rsplit(":", 1)[-1]
    titulo = _titulo(linha["titulo"])
    chaves = {("id", linha["id"])}
    chaves.update(("repo", repo) for repo in _repositorios(linha["repositorio"]))
    if grupo:
        chaves.add(("grupo", grupo))
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        chaves.add(("sha", sha))
    if titulo:
        chaves.add(("titulo", titulo))
    if linha.get("id_origem"):
        chaves.add(("id", linha["id_origem"]))
    return chaves


def _componentes(chaves_por_id):
    pais = {uid: uid for uid in chaves_por_id}
    donos = {}

    def raiz(uid):
        while pais[uid] != uid:
            pais[uid] = pais[pais[uid]]
            uid = pais[uid]
        return uid

    for uid, chaves in chaves_por_id.items():
        for chave in chaves:
            a, b = raiz(uid), raiz(donos.setdefault(chave, uid))
            if a != b:
                pais[max(a, b)] = min(a, b)
    return {uid: raiz(uid) for uid in pais}


def ler_expansao(caminho):
    with Path(caminho).open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        if not COLUNAS.issubset(leitor.fieldnames or ()):
            raise ValueError("CSV bilíngue sem as colunas obrigatórias da expansão V13.")
        linhas = {}
        for linha in leitor:
            uid = linha["id"]
            tipo = linha["tipo_aumento"]
            if (not uid or uid in linhas or not _titulo(linha["titulo"] or "")
                    or not linha["grupo"] or not linha["repositorio"] or not linha["origem"]
                    or tipo not in ORIGENS or linha["origem_rotulo"] != ORIGENS[tipo]
                    or linha["categoria_ia"] not in CLASSES or linha["particao"] != "treino"
                    or linha["revisao_humana"] != "nao"
                    or linha["usar_treino_experimental"] != "sim" or linha["motivo_exclusao"]
                    or linha["idioma"] != ("en" if tipo == "original_pseudorrotulado" else "pt-BR")):
                raise ValueError(f"Registro de expansão inválido ou ID repetido na linha {leitor.line_num}.")
            linhas[uid] = linha
    tot = Counter(r["tipo_aumento"] for r in linhas.values())
    if tot != {"original_pseudorrotulado": 509, "traducao_ia": 331, "sintetico_ia": 69}:
        raise ValueError(f"Esperava a expansão bilíngue 909; encontrado {dict(tot)}.")
    for linha in linhas.values():
        if linha["tipo_aumento"] == "traducao_ia":
            fonte = linhas.get(linha["id_origem"])
            campos = ("grupo", "repositorio", "origem", "categoria_ia")
            if (not fonte or fonte["tipo_aumento"] != "original_pseudorrotulado"
                    or linha["titulo_origem"] != fonte["titulo"]
                    or any(linha[c] != fonte[c] for c in campos)):
                raise ValueError(f"Tradução sem vínculo válido: {linha['id']}.")
        elif linha["id_origem"] or linha["titulo_origem"]:
            raise ValueError(f"Vínculo inesperado no registro {linha['id']}.")
    traducoes = [r["id_origem"] for r in linhas.values() if r["id_origem"]]
    if len(traducoes) != len(set(traducoes)):
        raise ValueError("Há mais de uma tradução para o mesmo original na expansão 909.")
    return linhas


def carregar(entrada, banco, expansao):
    ids, com, sem, y, grupos_v12 = carregar_gold(entrada, banco)
    novas = ler_expansao(expansao)
    if set(ids) & novas.keys():
        raise ValueError("IDs da expansão coincidem com avaliações humanas da V12.")
    reais = {uid for uid, r in novas.items() if r["tipo_aumento"] == "original_pseudorrotulado"}
    existentes = {}
    chaves = {uid: _identificadores(r) for uid, r in novas.items()}
    particoes = Counter()
    humanos = set(ids)
    with Path(entrada).open(encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            uid = linha["id"]
            particao = linha["particao"]
            if particao not in {"treino", "validacao", "teste"}:
                raise ValueError(f"Partição desconhecida no CSV preparado: {particao!r}.")
            particoes[particao] += 1
            if uid in humanos or uid in reais:
                if uid in existentes or particao != "treino":
                    raise ValueError(f"Registro original repetido ou fora do treino: {uid}.")
                existentes[uid] = linha

    if existentes.keys() != humanos | reais:
        raise ValueError("Há registros originais ausentes do CSV preparado.")
    for uid in reais:
        if any(novas[uid][c] != existentes[uid][c] for c in ("titulo", "repositorio", "grupo", "origem")):
            raise ValueError(f"O pseudo-rótulo {uid} diverge dos metadados preparados.")

    originais = [Registro(uid, t, str(c), "humano_v12", existentes[uid].get("idioma", "incerto"))
                 for uid, t, c in zip(ids, com, y)]
    for uid, grupo in zip(ids, grupos_v12):
        chaves[uid] = _identificadores(existentes[uid]) | {("grupo_v12", grupo)}
    componentes = _componentes(chaves)
    chaves_relevantes = set().union(*chaves.values())
    reservadas = set()
    with Path(entrada).open(encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha["particao"] != "treino":
                # As partições reservadas fornecem apenas chaves de exclusão.
                reservadas.update(_identificadores(linha) & chaves_relevantes)
    bloqueados = {componentes[uid] for uid, ks in chaves.items() if ks & reservadas}
    gold_reservado = {uid for uid in ids if componentes[uid] in bloqueados}
    repeticoes = defaultdict(list)
    candidatos = [Registro(uid, r["titulo"], r["categoria_ia"], r["origem_rotulo"], r["idioma"])
                  for tipo in ORIGENS for uid, r in novas.items() if r["tipo_aumento"] == tipo]
    for r in originais + candidatos:
        repeticoes[_titulo(r.titulo)].append(r)
    descartes = dict.fromkeys(sorted(gold_reservado), "relacao_particao_reservada")
    conflitos = set()
    for iguais in repeticoes.values():
        if len({r.categoria for r in iguais}) > 1:
            conflitos.update(r.id for r in iguais if r.id in novas)
    for r in candidatos:
        if r.id in conflitos or novas[r.id]["id_origem"] in conflitos:
            descartes[r.id] = "conflito_rotulo"
        elif componentes[r.id] in bloqueados:
            descartes[r.id] = "relacao_particao_reservada"
    vistos = {_titulo(r.titulo) for r in originais}
    aptos = []
    for r in candidatos:
        if r.id in descartes:
            continue
        chave = _titulo(r.titulo)
        if chave in vistos:
            descartes[r.id] = "titulo_duplicado"
        else:
            aptos.append(r)
            vistos.add(chave)
    auditoria = {
        "particoes_base_preparada": dict(particoes),
        "grupos_csv_expansao": len({r["grupo"] for r in novas.values()}),
        "duplicatas_titulo_sem_prefixo": sum(len(rs) - 1 for rs in repeticoes.values()),
        "grupos_titulo_com_conflito": sum(len({r.categoria for r in rs}) > 1 for rs in repeticoes.values()),
        "descartes_por_origem": {
            origem: dict(Counter(descartes[r.id] for r in candidatos
                                if r.origem == origem and r.id in descartes))
            for origem in ORIGENS.values()
        } | {"humano_v12": dict(Counter(descartes[uid] for uid in gold_reservado))},
        "descartes": descartes,
    }
    return originais, aptos, (ids, com, sem, y, grupos_v12), componentes, auditoria
