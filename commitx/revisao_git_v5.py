"""Revisao humana com acesso opcional a diff Git verificado.

Base V5 totalmente isolada dos 500 rotulos antigos. Separe repositorios antes
de rotular: 6 treino, 1 validacao, 1 teste BLOQUEADO. Nenhum rotulo e inferido
de prefixo ou paths. Use os detalhes 'dN' so em commits do treino/validacao.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .leitor_diff import analisar_commit

CATEGORIAS = ("fix", "feat", "docs", "refactor", "test", "indeterminado", "fora_escopo")
CLAREZAS = ("vago", "parcial", "claro", "indeterminado")
ENTRADA = Path("resultados/coleta-git-real-v5-01/commits_git_reais.csv")
PLANO = Path("resultados/revisao-git-v5-01/plano.json")
BANCO = Path("resultados/revisao-git-v5-01/rotulos_v5.sqlite3")
PREENCHER = re.compile(r"^(\d+)=(\d+),(\d+)$")
SHA = re.compile(r"^[0-9a-f]{40}$")

def carregar_csv(entrada):
    with Path(entrada).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"id", "titulo", "repositorio", "particao"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV sem id, titulo, repositorio ou particao")
        linhas = list(reader)
    if not linhas:
        raise ValueError("CSV vazio")
    if len(set(r["id"] for r in linhas)) != len(linhas):
        raise ValueError("IDs duplicados")
    for r in linhas:
        if not SHA.fullmatch(r["id"]) or not r["repositorio"].startswith("git:"):
            raise ValueError("Registro nao corresponde a SHA40 e origem Git local")
        if r["particao"] != "nao_atribuida":
            raise ValueError("CSV de coleta ja particionado; nao misture planos")
    return linhas

def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def preparar(*, entrada=ENTRADA, plano=PLANO, banco=BANCO):
    entrada, plano, banco = Path(entrada), Path(plano), Path(banco)
    if plano.exists() or banco.exists():
        raise FileExistsError("Ja existe um plano ou banco: nao sobrescreva o projeto V5")
    linhas = carregar_csv(entrada)
    repos = sorted({r["repositorio"] for r in linhas})
    if len(repos) < 4:
        raise ValueError("Use no minimo 4 repositorios para separar treino/validacao/teste")
    # Escolha deterministica dos repositorios por hash. Nao usa rótulos nem prefixos.
    ordenados = sorted(repos, key=lambda s: (hashlib.sha256(s.encode()).hexdigest(), s))
    teste, validacao = ordenados[-1], ordenados[-2]
    grupos = {r: ("teste" if r == teste else "validacao" if r == validacao else "treino")
              for r in repos}
    plano_dados = {
        "protocolo": "v5-repositorios-disjuntos-separados-antes-da-rotulagem",
        "entrada": str(entrada),
        "sha256_entrada": _digest(entrada),
        "repositorios": grupos,
        "contagens": dict(Counter(grupos[r["repositorio"]] for r in linhas)),
        "teste_bloqueado": True,
        "regras": [
            "Nao acessar exemplos do repositorio teste na revisao nem no treino.",
            "Nao usar prefixos de commits como rotulos.",
            "Nao treinar modelo usando exemplos da validacao.",
            "Amostra limitada a commits recentes; revisar por pessoa e com contexto.",
            "Resultados anteriores de 76,9 por cento nao sao comparaveis diretamente.",
        ],
    }
    plano.parent.mkdir(parents=True, exist_ok=True)
    banco.parent.mkdir(parents=True, exist_ok=True)
    plano.write_text(json.dumps(plano_dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with sqlite3.connect(banco) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS avaliacoes (
            id TEXT PRIMARY KEY, categoria TEXT NOT NULL, clareza TEXT NOT NULL,
            observacao TEXT NOT NULL DEFAULT '')""")
    return plano_dados

def abrir(*, entrada=ENTRADA, plano=PLANO, banco=BANCO):
    entrada, plano, banco = Path(entrada), Path(plano), Path(banco)
    if not plano.exists() or not banco.exists():
        raise ValueError("Execute primeiro o comando preparar")
    dados = json.loads(plano.read_text(encoding="utf-8"))
    if dados["sha256_entrada"] != _digest(entrada):
        raise ValueError("CSV mudou; nao rotule um plano montado com outro conjunto")
    rows = carregar_csv(entrada)
    repos = {r["repositorio"] for r in rows}
    if set(dados["repositorios"]) != repos:
        raise ValueError("Lista de repositorios diferente do plano")
    return rows, dados

def _candidatos(rows, dados, con, particao, limite):
    marcados = {uid for (uid,) in con.execute("SELECT id FROM avaliacoes")}
    return [r for r in rows if dados["repositorios"][r["repositorio"]] == particao
            and r["id"] not in marcados][:limite]

def _diff(r, *, raiz):
    repo = Path(r["repositorio"][4:]).expanduser().resolve()
    raiz = Path(raiz).expanduser().resolve()
    if not repo.is_relative_to(raiz) or repo == raiz:
        raise ValueError("Repositorio fora da pasta Git autorizada")
    resultado = analisar_commit(repo, r["id"], max_chars=2200)
    if resultado["commit"].lower() != r["id"] or resultado["titulo"].strip() != r["titulo"].strip():
        raise ValueError("SHA ou titulo nao conferem com o Git local")
    return resultado

def revisar(*, entrada=ENTRADA, plano=PLANO, banco=BANCO,
           particao="treino", tamanho=30, limite=120, raiz=Path("repos"), input_fn=input, output_fn=print):
    if particao not in ("treino", "validacao"):
        raise ValueError("Teste esta bloqueado para revisao")
    if not 1 <= tamanho <= 50 or not 1 <= limite <= 1200:
        raise ValueError("Tamanho 1..50 e limite 1..1200")
    rows, dados = abrir(entrada=entrada, plano=plano, banco=banco)
    feitas = 0
    with sqlite3.connect(banco) as con:
        while feitas < limite:
            lote = _candidatos(rows, dados, con, particao, min(tamanho, limite-feitas))
            if not lote:
                break
            output_fn(f"\n=== {particao.upper()}: {len(lote)} commits | revisados nesta sessao: {feitas} ===")
            for i, r in enumerate(lote, 1):
                output_fn(f"[{i}] {r['titulo'][:150]} | {r['repositorio'][4:].split('/')[-1]}")
                output_fn(f"    arquivos: {str(r.get('arquivos_modificados',''))} | +{r.get('linhas_adicionadas','')} -{r.get('linhas_removidas','')}")
                output_fn(f"    nomes: {str(r.get('arquivos',''))[:180]}")
            output_fn("CATEGORIA: 1=fix 2=feat 3=docs 4=refactor 5=test 6=indeterminado 7=fora_escopo")
            output_fn("CLAREZA: 1=vago 2=parcial 3=claro 4=indeterminado")
            output_fn("Use 1=1,3;2=2,2 para salvar; d3 para ver o diff do item 3; q para sair.")
            try:
                comando = input_fn("V5> ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break
            if comando == "q":
                break
            if comando.startswith("d") and comando[1:].isdigit():
                n = int(comando[1:])
                if not 1 <= n <= len(lote):
                    output_fn("Indice invalido")
                    continue
                try:
                    info = _diff(lote[n-1], raiz=raiz)
                    output_fn(f"SHA: {info['commit']}")
                    output_fn("Arquivos: " + ", ".join(a["arquivo"] for a in info["arquivos"][:30]))
                    output_fn("Patch (trecho; pode conter informacoes sensiveis):\n" + info["diff_previa"])
                    if info["diff_truncado"]:
                        output_fn("AVISO: diff truncado")
                except (ValueError, OSError) as erro:
                    output_fn("Git indisponivel: " + str(erro))
                continue
            entradas = [v.strip() for v in comando.split(";") if v.strip()]
            if not entradas:
                output_fn("Nada salvo")
                continue
            pedidos = []
            erro = None
            vistos = set()
            for entrada_item in entradas:
                match = PREENCHER.fullmatch(entrada_item)
                if not match:
                    erro = "Formato invalido: " + entrada_item
                    break
                indice, cat, cla = map(int, match.groups())
                if not 1 <= indice <= len(lote) or not 1 <= cat <= 7 or not 1 <= cla <= 4:
                    erro = "Indice ou rotulo fora do intervalo"
                    break
                if indice in vistos:
                    erro = "Indice repetido"
                    break
                vistos.add(indice)
                pedidos.append((lote[indice-1]["id"], CATEGORIAS[cat-1], CLAREZAS[cla-1]))
            if erro:
                output_fn(erro + ". Nada foi salvo.")
                continue
            with con:
                con.executemany("INSERT INTO avaliacoes(id,categoria,clareza) VALUES(?,?,?)", pedidos)
            feitas += len(pedidos)
            output_fn(f"Salvos nesta rodada: {len(pedidos)}; nesta sessao: {feitas}")
    return feitas

def status(*, entrada=ENTRADA, plano=PLANO, banco=BANCO):
    rows, dados = abrir(entrada=entrada, plano=plano, banco=banco)
    with sqlite3.connect(banco) as con:
        ids = {uid for (uid,) in con.execute("SELECT id FROM avaliacoes")}
    por_grupo = Counter(dados["repositorios"][r["repositorio"]] for r in rows if r["id"] in ids)
    # Defesa contra insercao acidental de rotulos reservados no banco.
    if por_grupo["teste"]:
        raise ValueError("O banco contem rotulos do teste bloqueado; interrompendo")
    return {
        "rotulados": len(ids), "treino": por_grupo["treino"],
        "validacao": por_grupo["validacao"],
        "teste_reservado": dados["contagens"]["teste"],
        "total_coletado": len(rows),
    }

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--plano", type=Path, default=PLANO)
    p.add_argument("--banco", type=Path, default=BANCO)
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("preparar")
    sub.add_parser("status")
    rev = sub.add_parser("revisar")
    rev.add_argument("--particao", choices=("treino", "validacao"), default="treino")
    rev.add_argument("--tamanho", type=int, default=30)
    rev.add_argument("--limite", type=int, default=120)
    rev.add_argument("--raiz-repos", type=Path, default=Path("repos"))
    a = p.parse_args(argv)
    try:
        if a.comando == "preparar":
            print(json.dumps(preparar(entrada=a.entrada, plano=a.plano, banco=a.banco),
                             indent=2, ensure_ascii=False))
        elif a.comando == "status":
            print(json.dumps(status(entrada=a.entrada, plano=a.plano, banco=a.banco),
                             indent=2, ensure_ascii=False))
        else:
            print("Novos rotulos:", revisar(
                entrada=a.entrada, plano=a.plano, banco=a.banco,
                particao=a.particao, tamanho=a.tamanho, limite=a.limite, raiz=a.raiz_repos))
    except (OSError, ValueError, sqlite3.Error) as e:
        p.error(str(e))

if __name__ == "__main__":
    main()
