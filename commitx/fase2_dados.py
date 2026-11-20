"""Fase 2: auditoria de proveniencia e piloto de commits/diffs locais.

Somente leitura dos dados existentes. Arquivos novos sao criados com modo x.
Nenhum rotulo e atribuido automaticamente.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sqlite3

from .leitor_diff import analisar_commit, _git
from .treino_real import ENTRADA, BANCO

SHA = re.compile(r"^[0-9a-fA-F]{40}$")
CAMPOS_PILOTO = (
    "id", "titulo", "descricao", "repositorio", "particao",
    "categoria", "clareza", "arquivos_alterados", "linhas_adicionadas",
    "linhas_removidas", "diff_previa", "diff_truncado",
    "comparado_com", "merge", "proveniencia",
)


def _destino_livre(caminho):
    caminho = Path(caminho)
    if caminho.exists() or caminho.is_symlink():
        raise FileExistsError(f"Arquivo existente: {caminho}. Escolha outra saida.")
    return caminho


def _escrever_json(caminho, conteudo):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("x", encoding="utf-8") as arq:
        json.dump(conteudo, arq, ensure_ascii=False, indent=2)
        arq.write("\n")


def auditar(entrada=ENTRADA, banco=BANCO, saida=Path("resultados/fase2/auditoria.json")):
    """Audita metadados; SHA aparente nao comprova a origem do commit."""
    entrada, banco, saida = map(Path, (entrada, banco, saida))
    _destino_livre(saida)
    if not entrada.is_file():
        raise ValueError("CSV preparado nao encontrado: " + str(entrada))
    humanos = set()
    if banco.is_file():
        with sqlite3.connect(f"file:{banco.resolve().as_posix()}?mode=ro", uri=True) as con:
            humanos = {linha[0] for linha in con.execute("SELECT id FROM avaliacoes")}
    cont = Counter()
    amostras = []
    with entrada.open(encoding="utf-8-sig", newline="") as arq:
        leitor = csv.DictReader(arq)
        necessarios = {"id", "titulo", "descricao", "repositorio", "particao"}
        if not necessarios.issubset(leitor.fieldnames or []):
            raise ValueError("CSV sem colunas: " + ", ".join(sorted(necessarios - set(leitor.fieldnames or []))))
        for linha in leitor:
            cont["total_preparado"] += 1
            uid = (linha.get("id") or "").strip()
            repo = (linha.get("repositorio") or "").strip()
            particao = (linha.get("particao") or "").strip()
            if SHA.fullmatch(uid):
                cont["ids_sha40_aparentes"] += 1
            else:
                cont["ids_nao_sha40"] += 1
                if len(amostras) < 5:
                    amostras.append({"id": uid[:120], "repositorio": repo[:120]})
            if repo:
                cont["com_repositorio"] += 1
            if particao in ("treino", "validacao", "teste"):
                cont["particao_valida"] += 1
            else:
                cont["particao_invalida"] += 1
            if uid in humanos:
                cont["rotulos_encontrados"] += 1
                if SHA.fullmatch(uid):
                    cont["rotulados_sha40_aparente"] += 1
    relatorio = {
        "resultado": dict(cont),
        "exemplos_ids_nao_sha40": amostras,
        "rotulos_sqlite_total": len(humanos),
        "explicacao": (
            "Ter 40 digitos hexadecimais e ter um campo repositorio NAO comprovam "
            "que o commit esteja disponivel localmente nem que a origem seja correta. "
            "Nenhum commit foi associado ou classificado nesta auditoria."
        ),
        "teste_reservado": "Nenhuma particao foi usada para treinamento ou revisao.",
    }
    _escrever_json(saida, relatorio)
    return relatorio


def piloto(repositorio, saida=Path("resultados/fase2/piloto-local.csv"),
           resumo=Path("resultados/fase2/piloto-local.json"), quantidade=10,
           max_chars=1500):
    """Extrai commits reais por SHA de um repo local. Rotulos vazios.

    Mantem somente commits sem merge, para facilitar a primeira experiencia.
    """
    saida, resumo = Path(saida), Path(resumo)
    if saida.resolve() == resumo.resolve():
        raise ValueError("CSV e JSON precisam de caminhos diferentes")
    _destino_livre(saida)
    _destino_livre(resumo)
    if not 1 <= quantidade <= 30:
        raise ValueError("--quantidade precisa estar entre 1 e 30")
    if not 100 <= max_chars <= 100000:
        raise ValueError("--max-caracteres precisa estar entre 100 e 100000")
    raiz = Path(repositorio).expanduser().resolve()
    if not raiz.is_dir():
        raise ValueError("Repositorio local nao encontrado")
    if Path(_git(raiz, "rev-parse", "--show-toplevel").strip()).resolve() != raiz:
        raise ValueError("Informe a pasta raiz de um repositorio Git")
    shas = _git(
        raiz, "log", "--no-merges", f"--max-count={quantidade}",
        "--format=%H", "HEAD", "--",
    ).splitlines()
    if not shas:
        raise ValueError("Nao foram encontrados commits locais")
    registros = []
    truncados = 0
    for sha in shas:
        detalhe = analisar_commit(raiz, sha, max_chars=max_chars)
        truncados += int(detalhe["diff_truncado"])
        registros.append({
            "id": detalhe["commit"],
            "titulo": detalhe["titulo"],
            "descricao": detalhe["descricao"],
            "repositorio": str(raiz),
            "particao": "nao_atribuida",
            "categoria": "",
            "clareza": "",
            "arquivos_alterados": ";".join(a["arquivo"] for a in detalhe["arquivos"]),
            "linhas_adicionadas": detalhe["linhas_adicionadas"],
            "linhas_removidas": detalhe["linhas_removidas"],
            "diff_previa": detalhe["diff_previa"],
            "diff_truncado": int(detalhe["diff_truncado"]),
            "comparado_com": detalhe["comparado_com"] or "",
            "merge": int(detalhe["merge"]),
            "proveniencia": "git_local_sha_verificado",
        })
    # Os arquivos sao exclusivos; nao toca no CSV mestre nem no SQLite.
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("x", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=CAMPOS_PILOTO)
        escritor.writeheader()
        escritor.writerows(registros)
    relatorio = {
        "quantidade": len(registros),
        "diffs_truncados": truncados,
        "repositorio_local": str(raiz),
        "csv": str(saida),
        "sem_rotulos": True,
        "particao": "nao_atribuida",
        "limites": (
            "Piloto nao e uma base pronta para treinar ou avaliar. "
            "Nenhum rotulo foi copiado, nenhuma particao foi definida, "
            "e a visualizacao de patch pode estar truncada. "
            "Os commits sao selecionados por recencia, sem representar uma populacao."
        ),
    }
    _escrever_json(resumo, relatorio)
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="acao", required=True)
    a = sub.add_parser("auditar", help="Audita ids do CSV preparado sem baixar nada")
    a.add_argument("--entrada", type=Path, default=ENTRADA)
    a.add_argument("--banco", type=Path, default=BANCO)
    a.add_argument("--saida", type=Path, default=Path("resultados/fase2/auditoria.json"))
    p = sub.add_parser("piloto", help="Extrai diffs de commits reais locais sem rotular")
    p.add_argument("--repositorio", type=Path, default=Path("."))
    p.add_argument("--saida", type=Path, default=Path("resultados/fase2/piloto-local.csv"))
    p.add_argument("--resumo", type=Path, default=Path("resultados/fase2/piloto-local.json"))
    p.add_argument("--quantidade", type=int, default=10)
    p.add_argument("--max-caracteres", type=int, default=1500)
    args = parser.parse_args(argv)
    try:
        resultado = (
            auditar(args.entrada, args.banco, args.saida)
            if args.acao == "auditar" else
            piloto(args.repositorio, args.saida, args.resumo, args.quantidade,
                   args.max_caracteres)
        )
    except (ValueError, OSError, csv.Error, sqlite3.Error) as erro:
        parser.error(str(erro))
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
