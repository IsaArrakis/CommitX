"""Fase 2: amostra verificavel de commits locais rotulados para pesquisa.

Lê CSV de verificação, confirma novamente a identidade e consulta o SQLite
apenas em leitura. Por padrão não exporta conteúdo de diffs, só estatísticas.
Nenhuma partição de teste é consultada.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from .fase2_verificar_locais import _status
from .fase2_vinculos import _identificador
from .leitor_diff import analisar_commit
from .treino_real import BANCO

ENTRADA = Path("resultados/fase2/verificacao-locais-01.csv")
SAIDA = Path("resultados/fase2/base-local-treino-01.csv")
RESUMO = Path("resultados/fase2/base-local-treino-01.json")
COLUNAS = (
    "id", "repositorio", "sha_original", "particao",
    "titulo", "descricao", "categoria_humana", "clareza_humana",
    "proveniencia_rotulo", "arquivos_alterados",
    "linhas_adicionadas", "linhas_removidas", "diff_previa",
    "diff_truncado", "diff_sha256", "proveniencia_diff",
)


def _confirmar_saida(entrada, banco, saida, resumo):
    caminhos = [p.resolve() for p in (entrada, banco, saida, resumo)]
    if len(set(caminhos)) != 4:
        raise ValueError("Entradas e saidas devem ter caminhos diferentes")
    if any(p.exists() or p.is_symlink() for p in (saida, resumo)):
        raise FileExistsError("Os arquivos de saida ja existem. Escolha nomes novos.")
    if not entrada.is_file() or not banco.is_file():
        raise ValueError("CSV de verificacao ou SQLite de rotulos nao encontrado.")


def construir(entrada=ENTRADA, banco=BANCO, saida=SAIDA, resumo=RESUMO,
              *, particoes=("treino",), limite=1000, incluir_patch=False,
              max_chars=10000):
    entrada, banco, saida, resumo = map(Path, (entrada, banco, saida, resumo))
    _confirmar_saida(entrada, banco, saida, resumo)
    if not particoes or any(p not in ("treino", "validacao") for p in particoes):
        raise ValueError("Permitido apenas treino e validacao; teste permanece reservado.")
    if not 1 <= limite <= 10000 or not 100 <= max_chars <= 100000:
        raise ValueError("Limite ou tamanho do patch fora da faixa permitida.")

    uri = f"file:{banco.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        humanos = {
            uid: (cat, cla)
            for uid, cat, cla in conn.execute(
                "SELECT id, categoria, clareza FROM avaliacoes"
            )
        }
    cont = Counter()
    linhas = []
    vistos = set()
    with entrada.open(encoding="utf-8-sig", newline="") as origem:
        leitor = csv.DictReader(origem)
        campos = {
            "id", "repositorio", "sha_original", "particao", "fonte",
            "integridade_id", "verificacao_local", "situacao_origem",
        }
        faltantes = campos - set(leitor.fieldnames or [])
        if faltantes:
            raise ValueError("CSV de verificacao sem colunas: " + ", ".join(sorted(faltantes)))
        for linha in leitor:
            cont["linhas_verificadas_no_csv"] += 1
            particao = (linha.get("particao") or "").strip()
            if particao not in particoes:
                cont["fora_das_particoes_solicitadas"] += 1
                continue
            uid = (linha.get("id") or "").strip()
            if uid in vistos:
                cont["ids_duplicados_ignorados"] += 1
                continue
            vistos.add(uid)
            if len(linhas) >= limite:
                cont["limite_atingido"] += 1
                break
            if linha.get("verificacao_local") != "sha_verificado_local":
                cont["nao_verificados_ignorados"] += 1
                continue
            if uid not in humanos:
                cont["sem_rotulo_ignorado"] += 1
                continue
            repo = (linha["repositorio"] or "").strip()
            sha = (linha["sha_original"] or "").strip().lower()
            if not repo.startswith("git:") or _identificador(repo, sha) != uid:
                cont["hash_divergente_ignorado"] += 1
                continue
            estado, pasta = _status(linha)
            if estado != "sha_verificado_local":
                cont["indisponiveis_ignorados"] += 1
                continue
            try:
                detalhe = analisar_commit(pasta, sha, max_chars=max_chars)
            except (ValueError, OSError):
                cont["falha_leitura_diff"] += 1
                continue
            if detalhe["commit"].lower() != sha:
                cont["sha_divergente_ignorado"] += 1
                continue
            categoria, clareza = humanos[uid]
            # Hash da previa serve para comparar exportacoes; pode ser parcial.
            previa = detalhe["diff_previa"] if incluir_patch else ""
            linha_saida = {
                "id": uid,
                "repositorio": repo,
                "sha_original": sha,
                "particao": particao,
                "titulo": detalhe["titulo"],
                "descricao": detalhe["descricao"],
                "categoria_humana": categoria,
                "clareza_humana": clareza,
                "proveniencia_rotulo": "SQLite_humano_assistencia_IA_nao_auditada",
                "arquivos_alterados": ";".join(
                    a["arquivo"] for a in detalhe["arquivos"]
                ),
                "linhas_adicionadas": detalhe["linhas_adicionadas"],
                "linhas_removidas": detalhe["linhas_removidas"],
                "diff_previa": previa,
                "diff_truncado": "sim" if detalhe["diff_truncado"] else "nao",
                "diff_sha256": hashlib.sha256(
                    detalhe["diff_previa"].encode("utf-8")
                ).hexdigest(),
                "proveniencia_diff": "git_local_sha_confirmado",
            }
            linhas.append(linha_saida)
            cont["exportados_" + particao] += 1
            if detalhe["diff_truncado"]:
                cont["diffs_truncados"] += 1
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    informacoes = {
        "exportados": len(linhas),
        "contagens": dict(sorted(cont.items())),
        "particoes": list(particoes),
        "patch_incluido": incluir_patch,
        "max_caracteres_previa": max_chars,
        "csv": str(saida),
        "aviso": (
            "Esta base piloto NAO e avaliacao independente. Muitos rotulos "
            "receberam assistencia de IA e requerem auditoria. "
            "A base conserva as particoes originais, mas pode ser insuficiente "
            "para comparar modelos. Nunca inclui a particao teste. "
            "Nao compartilhe diffs sem revisar possiveis dados sensiveis."
        ),
    }
    resumo.parent.mkdir(parents=True, exist_ok=True)
    with resumo.open("x", encoding="utf-8") as arquivo:
        json.dump(informacoes, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    return informacoes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--banco", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--resumo", type=Path, default=RESUMO)
    parser.add_argument("--particoes", nargs="+", default=["treino"],
                        choices=["treino", "validacao"])
    parser.add_argument("--limite", type=int, default=1000)
    parser.add_argument("--incluir-patch", action="store_true")
    parser.add_argument("--max-caracteres", type=int, default=10000)
    args = parser.parse_args(argv)
    try:
        resultado = construir(args.entrada, args.banco, args.saida, args.resumo,
                              particoes=args.particoes, limite=args.limite,
                              incluir_patch=args.incluir_patch,
                              max_chars=args.max_caracteres)
    except (ValueError, OSError, sqlite3.Error, csv.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
