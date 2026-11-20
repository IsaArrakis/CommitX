"""Recupera o SHA Git original a partir do ID SHA-256 do banco de coleta.

O coletor calculou: sha256(repositorio.casefold() + '\\0' + sha.lower()).
Esta ferramenta verifica essa relacao, mas NAO baixa diffs, nao rotula e
nao modifica as bases existentes.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .treino_real import ENTRADA, BANCO

COLETA = Path("resultados/coleta/commits.sqlite3")
SAIDA = Path("resultados/fase2/vinculos-rotulados-01.csv")
RESUMO = Path("resultados/fase2/vinculos-rotulados-01.json")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
COLUNAS = (
    "id", "titulo", "repositorio", "particao", "sha_original",
    "fonte", "integridade_id", "situacao_origem", "revisado",
)


def _conectar_leitura(caminho):
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ValueError("Banco nao encontrado: " + str(caminho))
    return sqlite3.connect(
        f"file:{caminho.resolve().as_posix()}?mode=ro", uri=True
    )


def _identificador(repo, sha):
    return hashlib.sha256(
        (repo.casefold() + "\\0" + sha.lower()).encode("utf-8")
    ).hexdigest()


def _classificar(uid, repo_csv, registro):
    if registro is None:
        return "nao_encontrado", "sem_correspondencia"
    repo, sha, fonte = registro
    if _identificador(repo, sha) != uid:
        return "invalido", "hash_divergente"
    if repo_csv != repo:
        return "valido", "repositorio_divergente"
    if not SHA40.fullmatch(sha):
        return "valido", "sha_original_fora_formato_40"
    if "," in repo:
        return "valido", "repositorios_multiplos"
    if fonte == "git:local" and repo.startswith("git:"):
        return "valido", "git_local_pendente_verificacao"
    if fonte.startswith("huggingface:"):
        return "valido", "huggingface_pendente_verificacao"
    return "valido", "origem_nao_classificada"


def gerar(entrada=ENTRADA, coleta=COLETA, rotulos=BANCO,
          saida=SAIDA, resumo=RESUMO, *, todos=False):
    entrada, coleta, rotulos, saida, resumo = map(
        Path, (entrada, coleta, rotulos, saida, resumo)
    )
    caminhos = [p.resolve() for p in (entrada, coleta, rotulos, saida, resumo)]
    if len(set(caminhos)) != len(caminhos):
        raise ValueError("Entradas e saidas precisam ter caminhos diferentes")
    if saida.exists() or saida.is_symlink() or resumo.exists() or resumo.is_symlink():
        raise FileExistsError("Saida ja existe; escolha caminhos novos.")
    if not entrada.is_file():
        raise ValueError("CSV preparado nao encontrado: " + str(entrada))
    with _conectar_leitura(rotulos) as db_rot:
        revisados = {r[0] for r in db_rot.execute("SELECT id FROM avaliacoes")}
    contagem = Counter()
    with _conectar_leitura(coleta) as db:
        with entrada.open(encoding="utf-8-sig", newline="") as origem:
            leitor = csv.DictReader(origem)
            campos = {"id", "titulo", "repositorio", "particao"}
            if not campos.issubset(leitor.fieldnames or []):
                raise ValueError(
                    "CSV sem colunas: " + ", ".join(sorted(campos - set(leitor.fieldnames or [])))
                )
            saida.parent.mkdir(parents=True, exist_ok=True)
            with saida.open("x", encoding="utf-8", newline="") as destino:
                escritor = csv.DictWriter(destino, fieldnames=COLUNAS)
                escritor.writeheader()
                for linha in leitor:
                    uid = (linha["id"] or "").strip()
                    if not todos and uid not in revisados:
                        continue
                    original = db.execute(
                        "SELECT repositorio, sha, fonte FROM commits WHERE id = ?",
                        (uid,),
                    ).fetchone()
                    integridade, situacao = _classificar(
                        uid, (linha["repositorio"] or "").strip(), original
                    )
                    repo, sha, fonte = original if original else ("", "", "")
                    escritor.writerow({
                        "id": uid,
                        "titulo": linha["titulo"],
                        "repositorio": repo if integridade == "valido" else "",
                        "particao": linha["particao"],
                        "sha_original": sha if integridade == "valido" else "",
                        "fonte": fonte if integridade == "valido" else "",
                        "integridade_id": integridade,
                        "situacao_origem": situacao,
                        "revisado": "sim" if uid in revisados else "nao",
                    })
                    contagem["registros_auditados"] += 1
                    contagem["situacao_" + situacao] += 1
                    contagem["integridade_" + integridade] += 1
                    if uid in revisados:
                        contagem["registros_revisados"] += 1
    relatorio = {
        "contagens": dict(sorted(contagem.items())),
        "rotulos_existentes": len(revisados),
        "modo": "todos" if todos else "somente_rotulados",
        "observacao": (
            "O ID gerado pelo coletor foi verificado contra repositorio + SHA original. "
            "Essa integridade confirma o vinculo no banco, mas nao comprova que "
            "o commit remoto ou local esteja acessivel. Nao foram baixados diffs, "
            "atribuidos rotulos ou lidas particoes para treinamento."
        ),
        "saida_csv": str(saida),
    }
    resumo.parent.mkdir(parents=True, exist_ok=True)
    with resumo.open("x", encoding="utf-8") as arq:
        json.dump(relatorio, arq, ensure_ascii=False, indent=2)
        arq.write("\n")
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--coleta", type=Path, default=COLETA)
    parser.add_argument("--rotulos", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--resumo", type=Path, default=RESUMO)
    parser.add_argument("--todos", action="store_true",
                        help="Audita todos os 97 mil registros, nao apenas revisados")
    args = parser.parse_args(argv)
    try:
        resultado = gerar(args.entrada, args.coleta, args.rotulos,
                         args.saida, args.resumo, todos=args.todos)
    except (ValueError, OSError, csv.Error, sqlite3.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
