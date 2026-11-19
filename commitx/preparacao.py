"""Prepara amostras de commits coletados, sem criar rótulos supervisionados.

Exemplo: python -m commitx.preparacao --amostra 300
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import heapq
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

CLASSES = ("fix", "feat", "docs", "refactor", "test")
GRUPOS_AMOSTRA = (*CLASSES, "sem_tipo")
FONTES_AMOSTRA = ("hf", "git")
PREFIXO = re.compile(r"^([a-z][a-z0-9_-]*)(?:\([^()\n\r]+\))?!?:\s+", re.IGNORECASE)
PALAVRAS = re.compile(r"\w+", re.UNICODE)
COLUNAS = (
    "id", "titulo", "descricao", "categoria", "categoria_candidata",
    "tipo_declarado", "grupo", "origem", "repositorio", "linguagem",
    "licenca", "particao", "alertas",
)


def normalizar(texto):
    texto = unicodedata.normalize("NFKC", texto or "").casefold()
    return " ".join(texto.split())


def cabecalho(titulo):
    match = PREFIXO.match(titulo or "")
    return match.group(1).lower() if match else ""


def particao_por_repositorio(repositorio):
    """Split determinístico (80/10/10), sem distribuir commits do mesmo repo."""
    digest = hashlib.sha256(repositorio.casefold().encode("utf-8")).digest()
    valor = int.from_bytes(digest[:8], "big") % 100
    if valor < 80:
        return "treino"
    if valor < 90:
        return "validacao"
    return "teste"


def limpar_texto(titulo, descricao):
    titulo = " ".join((titulo or "").replace("\x00", " ").split())
    descricao = (descricao or "").replace("\x00", " ").strip()
    return titulo, descricao


def alertas_mensagem(titulo, descricao, tipo):
    resumo = PREFIXO.sub("", titulo, count=1) if tipo else titulo
    termos = PALAVRAS.findall(resumo)
    alertas = []
    if len(termos) <= 2:
        alertas.append("resumo_muito_curto")
    if re.search(r"\b(merge pull request|automated|dependabot|renovate)\b", titulo, re.I):
        alertas.append("possivel_automacao")
    if not descricao:
        alertas.append("sem_corpo")
    return alertas


def preparar(banco, saida, tamanho_amostra=300):
    """Lê banco existente em modo somente leitura; preserva exemplos vagos."""
    banco, saida = Path(banco), Path(saida)
    if not banco.is_file():
        raise ValueError(f"Banco não encontrado: {banco}")
    if tamanho_amostra < 0:
        raise ValueError("--amostra não pode ser negativo")
    if saida.exists() and any(saida.iterdir()):
        raise FileExistsError(
            f"Pasta de saída já contém arquivos: {saida}. Informe outra pasta em --saida."
        )
    saida.mkdir(parents=True, exist_ok=True)
    totais = Counter()
    por_fonte, por_linguagem, por_tipo, por_particao = (Counter() for _ in range(4))
    grupos_por_particao = defaultdict(set)
    buckets = {(fonte, classe): [] for fonte in FONTES_AMOSTRA for classe in GRUPOS_AMOSTRA}
    capacidade = (tamanho_amostra + len(buckets) - 1) // len(buckets)
    vistos = set()
    con = sqlite3.connect(f"file:{banco.resolve().as_posix()}?mode=ro", uri=True)
    try:
        consulta = con.execute(
            "SELECT id, repositorio, sha, titulo, descricao, fonte, linguagem, licenca "
            "FROM commits ORDER BY id"
        )
        with (saida / "commits_preparados.csv").open("x", encoding="utf-8", newline="") as arq:
            escritor = csv.DictWriter(arq, fieldnames=COLUNAS)
            escritor.writeheader()
            for (uid, repo, sha, titulo, descricao, fonte, linguagem, licenca) in consulta:
                totais["lidos"] += 1
                titulo, descricao = limpar_texto(titulo, descricao)
                if not titulo:
                    totais["sem_titulo"] += 1
                    continue
                texto = normalizar(titulo + "\n" + descricao)
                digest_texto = hashlib.sha256(texto.encode("utf-8")).hexdigest()
                if digest_texto in vistos:
                    totais["duplicados_texto"] += 1
                    continue
                vistos.add(digest_texto)
                tipo = cabecalho(titulo)
                candidato = tipo if tipo in CLASSES else ""
                particao = particao_por_repositorio(repo)
                avisos = alertas_mensagem(titulo, descricao, tipo)
                reg = {
                    "id": uid, "titulo": titulo, "descricao": descricao,
                    "categoria": "", "categoria_candidata": candidato,
                    "tipo_declarado": tipo, "grupo": f"{repo}:{sha}",
                    "origem": fonte, "repositorio": repo,
                    "linguagem": linguagem, "licenca": licenca,
                    "particao": particao, "alertas": ";".join(avisos),
                }
                escritor.writerow(reg)
                totais["preparados"] += 1
                por_fonte[fonte] += 1
                por_linguagem[linguagem or "nao_identificada"] += 1
                por_tipo[tipo or "sem_tipo"] += 1
                por_particao[particao] += 1
                grupos_por_particao[particao].add(repo)
                for aviso in avisos:
                    totais[f"alerta_{aviso}"] += 1
                if capacidade:
                    bucket_nome = candidato or "sem_tipo"
                    grupo_fonte = "hf" if fonte.startswith("huggingface:") else "git"
                    bucket = buckets[(grupo_fonte, bucket_nome)]
                    # Seleção determinística, independente da ordem do CSV.
                    prioridade = int.from_bytes(
                        hashlib.sha256(uid.encode("utf-8")).digest()[:8], "big"
                    )
                    item = (-prioridade, uid, reg)
                    if len(bucket) < capacidade:
                        heapq.heappush(bucket, item)
                    elif item > bucket[0]:
                        heapq.heapreplace(bucket, item)
    finally:
        con.close()
    amostra = []
    for bucket in buckets.values():
        amostra.extend(reg for _, _, reg in sorted(bucket, reverse=True))
    amostra.sort(key=lambda reg: reg["id"])
    amostra = amostra[:tamanho_amostra]
    with (saida / "amostra_para_rotular.csv").open("x", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(amostra)
    resumo = {
        "totais": dict(totais),
        "amostra": len(amostra),
        "por_fonte": dict(por_fonte.most_common()),
        "por_linguagem": dict(por_linguagem.most_common()),
        "por_tipo_declarado": dict(por_tipo.most_common()),
        "por_particao": dict(por_particao),
        "repositorios_por_particao": {
            chave: len(valor) for chave, valor in grupos_por_particao.items()
        },
        "avisos_metodologicos": [
            "categoria está vazia e requer revisão humana; categoria_candidata é apenas o prefixo declarado",
            "partição por repositório é proposta; antes de treinar, verifique classe e fonte em cada partição",
            "a base filtrada CommitPackFT não representa adequadamente mensagens vagas",
            "os alertas não são notas de clareza nem determinam a qualidade da mensagem",
            "a deduplicação exata de texto não elimina paráfrases nem forks",
            "verifique licenças e dados sensíveis antes de usar ou divulgar registros",
        ],
    }
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return resumo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--banco", type=Path, default=Path("resultados/coleta/commits.sqlite3")
    )
    parser.add_argument(
        "--saida", type=Path, default=Path("resultados/preparacao-inicial")
    )
    parser.add_argument("--amostra", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        resumo = preparar(args.banco, args.saida, args.amostra)
    except (ValueError, FileExistsError, sqlite3.Error, OSError) as erro:
        parser.error(str(erro))
    print("Registros lidos:", resumo["totais"].get("lidos", 0))
    print("Mensagens preparadas:", resumo["totais"].get("preparados", 0))
    print("Duplicações de texto:", resumo["totais"].get("duplicados_texto", 0))
    print("Amostra para revisão humana:", resumo["amostra"])
    print("Detalhes em:", args.saida / "resumo.json")


if __name__ == "__main__":
    main()
