"""Avaliacao externa simples e CEGA para os modelos academicos do CommitX.

Utiliza repositorios Git locais NOVOS, seleciona commits que nao aparecem
na base preparada de treinamento nem nas previsoes antigas (por ID ou titulo),
registra rótulos humanos sem mostrar previsoes e avalia modelos CONGELADOS.

Etapas:
  python -m commitx.avaliacao_externa preparar --repos R1 R2 R3
  python -m commitx.avaliacao_externa rotular
  python -m commitx.avaliacao_externa status
  python -m commitx.avaliacao_externa avaliar

Nunca modifica base de treinamento, modelos ou teste reservado V5.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from joblib import load
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

from .escrita import texto_modelo
from .experimento_v3 import carregar_treino
from .treino_real import ENTRADA as BASE_ANTIGA, BANCO as BANCO_ANTIGO

CLASSES = ("fix", "feat", "docs", "refactor", "test")
OUTRAS = ("indeterminado", "fora_escopo")
ROTULOS = CLASSES + OUTRAS
SAIDA = Path("resultados/avaliacao-externa-01")
PREVISOES_ANTIGAS = Path("resultados/academico-simples-01/previsoes.csv")
MODELOS = {
    "original": Path("resultados/academico-simples-01/modelo.joblib"),
    "pseudo": Path("resultados/academico-pseudo-02/modelo.joblib"),
}
SHA = re.compile(r"^[0-9a-f]{40}$")
RESPOSTA = re.compile(r"^(\d+)=(\d+)$")


def _json(path, valor):
    Path(path).write_text(json.dumps(valor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _csv(path, campos, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(rows)


def _ler(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _norm(titulo):
    try:
        return " ".join(texto_modelo(titulo.strip(), "").casefold().split())
    except (ValueError, AttributeError):
        return ""


def _repo_nome(s):
    s = str(s).strip().lower().rstrip("/").removesuffix(".git")
    return s.split("/")[-1].split(":")[-1]


def _git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=45, check=False,
    )
    if result.returncode:
        raise ValueError("Git falhou em " + str(repo) + ": " + result.stderr.strip()[:300])
    return result.stdout.strip()


def _exclusoes(arquivo_preparado, arquivo_previsoes):
    if not Path(arquivo_preparado).is_file() or not Path(arquivo_previsoes).is_file():
        raise FileNotFoundError("Base preparada ou previsoes antigas ausentes; nao e seguro medir independencia")
    ids, textos = set(), set()
    for path in (arquivo_preparado, arquivo_previsoes):
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not {"id", "titulo"}.issubset(reader.fieldnames or []):
                raise ValueError("CSV antigo sem id e titulo: " + str(path))
            for row in reader:
                uid = (row.get("id") or "").strip()
                titulo = _norm(row.get("titulo") or "")
                if uid:
                    ids.add(uid)
                if titulo:
                    textos.add(titulo)
    return ids, textos


def _amostrar(pools, quantidade, seed=42):
    rng = random.Random(seed)
    listas = {repo: list(commits) for repo, commits in pools.items()}
    for pool in listas.values():
        rng.shuffle(pool)
    nomes = sorted(listas)
    escolhidos, usados = [], set()
    while len(escolhidos) < quantidade and any(listas.values()):
        for repo in nomes:
            while listas[repo]:
                row = listas[repo].pop()
                key = _norm(row["titulo"])
                if row["id"] not in usados and key and key not in usados:
                    escolhidos.append(row)
                    usados.add(row["id"])
                    usados.add(key)
                    break
            if len(escolhidos) == quantidade:
                break
    return escolhidos


def preparar(repos, *, saida=SAIDA, quantidade=45, preparado=BASE_ANTIGA,
             previsoes_antigas=PREVISOES_ANTIGAS, banco=BANCO_ANTIGO):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Pasta ja existe: " + str(saida))
    if not 20 <= quantidade <= 200:
        raise ValueError("Quantidade deve estar entre 20 e 200")
    if len(repos) < 2:
        raise ValueError("Informe pelo menos dois repositorios Git novos")
    # Nomes de repositórios usados em rótulos humanos: nunca reutilizar.
    treino_antigo = carregar_treino(preparado, banco)
    repos_proibidos = {
        _repo_nome(nome) for r in treino_antigo for nome in r["repositorios"]
    }
    # Protege também o histórico de 8 projetos da avaliação V5.
    plano_v5 = Path("resultados/revisao-git-v5-01/plano.json")
    if plano_v5.is_file():
        dados = json.loads(plano_v5.read_text(encoding="utf-8"))
        repos_proibidos.update(_repo_nome(x) for x in dados.get("repositorios", {}))
    ids_vistos, titulos_vistos = _exclusoes(preparado, previsoes_antigas)
    pools, fontes = {}, []
    for repo in repos:
        repo = Path(repo).expanduser().resolve()
        raiz = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
        if raiz != repo:
            raise ValueError("Informe a raiz do repositorio: " + str(raiz))
        remoto = _git(repo, "remote", "get-url", "origin")
        nome = _repo_nome(remoto)
        if not nome or nome in repos_proibidos:
            raise ValueError("Repositorio possivelmente visto no treino ou V5: " + nome +
                             ". Escolha outro projeto publico.")
        if nome in pools:
            raise ValueError("Mesmo repositorio repetido: " + nome)
        log = _git(repo, "log", "--no-merges", "-n", "500", "--format=%H%x09%s")
        linhas = []
        for item in log.splitlines():
            if "\t" not in item:
                continue
            sha, titulo = item.split("\t", 1)
            titulo = titulo.strip()
            if not SHA.fullmatch(sha) or not _norm(titulo):
                continue
            if sha in ids_vistos or _norm(titulo) in titulos_vistos:
                continue
            linhas.append({"id": sha, "repositorio": nome, "titulo": titulo})
        pools[nome] = linhas
        fontes.append({"nome": nome, "remoto": remoto, "head": _git(repo, "rev-parse", "HEAD"),
                       "elegiveis": len(linhas)})
    escolhidos = _amostrar(pools, quantidade)
    if len(escolhidos) < quantidade:
        raise ValueError(f"Apenas {len(escolhidos)} candidatos novos; solicite menos ou clone mais repositorios")
    saida.mkdir(parents=True)
    amostra = saida / "amostra.csv"
    _csv(amostra, ["id", "repositorio", "titulo"], escolhidos)
    digest = hashlib.sha256(amostra.read_bytes()).hexdigest()
    manifesto = {
        "protocolo": "teste-externo-cego-v1-sem-ajustes",
        "amostra_sha256": digest,
        "quantidade": len(escolhidos),
        "origem": fontes,
        "categorias_permitidas": list(ROTULOS),
        "politica": [
            "Modelos congelados; nenhum novo treinamento ou ajuste de hiperparametros.",
            "Amostra nao presente nos CSV de base preparada ou previsoes anteriores (SHA/titulo).",
            "Repositorios nao podem constar nos rotulos humanos de treino nem no plano V5.",
            "Rotular sem ver predicoes; permitir indeterminado/fora_escopo.",
            "Resultados apenas das cinco classes com cobertura informada.",
            "Se rótulos forem assistidos por IA, nao denominar avaliacao independente.",
            "Revisar contextos ambiguos no Git antes de rotular.",
            "Nao reutilizar este teste para escolher modelo e proclamar nova acuracia.",
        ],
    }
    _json(saida / "manifesto.json", manifesto)
    return manifesto


def _abrir(saida):
    saida = Path(saida)
    arquivo = saida / "amostra.csv"
    manifesto = json.loads((saida / "manifesto.json").read_text(encoding="utf-8"))
    if hashlib.sha256(arquivo.read_bytes()).hexdigest() != manifesto["amostra_sha256"]:
        raise ValueError("Amostra mudou; interrompido")
    linhas = _ler(arquivo)
    if len(linhas) != manifesto["quantidade"] or len({r["id"] for r in linhas}) != len(linhas):
        raise ValueError("Amostra adulterada ou duplicada")
    return linhas, manifesto


def _rotulos(saida, rows):
    path = Path(saida) / "rotulos.csv"
    labels = {}
    if path.exists():
        for r in _ler(path):
            if r["id"] in labels or r["categoria"] not in ROTULOS:
                raise ValueError("Rotulos duplicados ou invalidos")
            labels[r["id"]] = r["categoria"]
    if not set(labels).issubset({r["id"] for r in rows}):
        raise ValueError("Rotulos contem IDs fora da amostra")
    return labels


def _salvar(saida, labels, rows):
    # Validar toda a amostra ANTES de abrir ou criar qualquer arquivo.
    ids = [r.get("id") for r in rows]
    if (len(ids) != len(set(ids)) or
            any(not isinstance(uid, str) or not SHA.fullmatch(uid) for uid in ids)):
        raise ValueError("Amostra com IDs invalidos ou duplicados")
    if any(not isinstance(uid, str) or not SHA.fullmatch(uid) or
           categoria not in ROTULOS for uid, categoria in labels.items()):
        raise ValueError("Rotulos com ID ou categoria invalida")
    if not set(labels).issubset(set(ids)):
        raise ValueError("Rotulos contem IDs fora da amostra")
    path = Path(saida) / "rotulos.csv"
    temp = path.with_suffix(".tmp")
    _csv(temp, ["id", "categoria"],
         [{"id": r["id"], "categoria": labels[r["id"]]}
          for r in rows if r["id"] in labels])
    temp.replace(path)


def rotular(*, saida=SAIDA, tamanho=15, limite=45, input_fn=input, output_fn=print):
    if not 1 <= tamanho <= 30 or not 1 <= limite <= 200:
        raise ValueError("Tamanho 1..30 e limite 1..200")
    rows, _ = _abrir(saida)
    labels = _rotulos(saida, rows)
    adicionados = 0
    while adicionados < limite:
        lote = [r for r in rows if r["id"] not in labels][:min(tamanho, limite-adicionados)]
        if not lote:
            break
        output_fn(f"\n== REVISAO EXTERNA: {len(labels)}/{len(rows)} rotulados ==")
        for i, r in enumerate(lote, 1):
            output_fn(f"[{i}] {r['titulo'][:160]} | {r['repositorio']}")
        output_fn("1=fix 2=feat 3=docs 4=refactor 5=test 6=indeterminado 7=fora_escopo")
        output_fn("Exemplo: 1=1;2=3;3=7  |  q=sair, dados salvos")
        try:
            comando = input_fn("Externo> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break
        if comando == "q":
            break
        marcacoes, indices, erro = {}, set(), None
        for item in comando.split(";"):
            item = item.strip()
            if not item:
                continue
            match = RESPOSTA.fullmatch(item)
            if not match:
                erro = "Formato invalido: " + item
                break
            indice, cat = map(int, match.groups())
            if not 1 <= indice <= len(lote) or not 1 <= cat <= len(ROTULOS) or indice in indices:
                erro = "Indice ou categoria invalida/repetida"
                break
            indices.add(indice)
            marcacoes[lote[indice - 1]["id"]] = ROTULOS[cat - 1]
        if erro or not marcacoes:
            output_fn((erro or "Nenhum rotulo") + ". Nada salvo.")
            continue
        labels.update(marcacoes)
        _salvar(saida, labels, rows)
        adicionados += len(marcacoes)
        output_fn(f"Salvos {len(marcacoes)}; total {len(labels)}/{len(rows)}")
    return len(labels)


def status(saida=SAIDA):
    rows, _ = _abrir(saida)
    labels = _rotulos(saida, rows)
    return {"total": len(rows), "rotulados": len(labels),
            "faltam": len(rows)-len(labels), "categorias": dict(Counter(labels.values()))}


def avaliar(*, saida=SAIDA, modelos=None):
    saida = Path(saida)
    rows, manifest = _abrir(saida)
    labels = _rotulos(saida, rows)
    if len(labels) != len(rows):
        raise ValueError(f"Amostra incompleta: {len(labels)}/{len(rows)}. Termine rotular primeiro.")
    usados = [r for r in rows if labels[r["id"]] in CLASSES]
    if len(usados) < 15:
        raise ValueError("Menos de 15 commits nas cinco classes: amostra insuficiente")
    destino = saida / "resultado"
    if destino.exists():
        raise FileExistsError("Resultado ja existe; nao reutilize o teste para ajuste")
    caminhos = modelos or MODELOS
    y = [labels[r["id"]] for r in usados]
    x = [texto_modelo(r["titulo"], "") for r in usados]
    predicoes, metricas = {}, {}
    for nome, caminho in caminhos.items():
        caminho = Path(caminho)
        if not caminho.is_file():
            raise FileNotFoundError("Modelo nao encontrado: " + str(caminho))
        # SOMENTE artefatos joblib locais confiaveis gerados pelo proprio usuario.
        modelo = load(caminho)
        previsto = [str(v) for v in modelo.predict(x)]
        predicoes[nome] = previsto
        metricas[nome] = {
            "acertos": sum(a == b for a, b in zip(y, previsto)),
            "acuracia": float(accuracy_score(y, previsto)),
            "macro_f1": float(f1_score(y, previsto, labels=CLASSES, average="macro",
                                       zero_division=0)),
            "por_classe": classification_report(y, previsto, labels=CLASSES,
                                                output_dict=True, zero_division=0),
            "matriz_confusao": confusion_matrix(y, previsto, labels=CLASSES).tolist(),
        }
    destino.mkdir()
    _csv(destino / "previsoes.csv",
         ["id", "titulo", "repositorio", "real", "original", "pseudo"],
         [{"id": r["id"], "titulo": r["titulo"], "repositorio": r["repositorio"],
           "real": real, "original": predicoes["original"][i],
           "pseudo": predicoes["pseudo"][i]}
          for i, (r, real) in enumerate(zip(usados, y))])
    resumo = {
        "protocolo": manifest["protocolo"], "total_amostra": len(rows),
        "avaliados_cinco_classes": len(usados),
        "cobertura": len(usados) / len(rows),
        "ignorados": dict(Counter(labels[r["id"]] for r in rows if labels[r["id"]] not in CLASSES)),
        "distribuicao_real": dict(Counter(y)), "classes": list(CLASSES),
        "modelos": metricas,
        "advertencias": [
            "Resultados de uma amostra pequena; nao garantem desempenho em todos os projetos.",
            "Qualidade depende da independencia da revisao humana.",
            "Nao ajustar modelos e reivindicar desempenho novo neste mesmo teste.",
            "Matriz de confusao: linhas reais, colunas previstas.",
            "Treino, pseudorrotulos antigos, validacao V5 e teste reservado nao foram alterados.",
        ],
    }
    _json(destino / "resumo.json", resumo)
    md = ["# CommitX - avaliacao externa congelada", "",
          f"Amostra: {len(rows)}; avaliados nas cinco classes: {len(usados)} ({len(usados)/len(rows):.1%}).",
          "", "| Modelo | Acuracia | Macro-F1 | Acertos |",
          "|---|---:|---:|---:|"]
    for nome, m in metricas.items():
        md.append(f"| {nome} | {m['acuracia']:.1%} | {m['macro_f1']:.3f} | {m['acertos']}/{len(usados)} |")
    md += ["", "Classes por quantidade real: " + str(dict(Counter(y))), "",
           "Limitacoes: amostra pequena, revisao deve ser independente e nao se deve ajustar",
           "modelos usando estes resultados e depois reportar este mesmo teste como novo.",
           "Matrizes de confusao e metricas por classe: resultado/resumo.json."]
    (destino / "relatorio.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return resumo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("preparar", help="Selecionar commits de projetos novos sem consultar modelos")
    p.add_argument("--repos", type=Path, nargs="+", required=True)
    p.add_argument("--quantidade", type=int, default=45)
    p.add_argument("--saida", type=Path, default=SAIDA)
    r = sub.add_parser("rotular", help="Rotular amostra cegamente")
    r.add_argument("--saida", type=Path, default=SAIDA)
    r.add_argument("--tamanho", type=int, default=15)
    r.add_argument("--limite", type=int, default=45)
    s = sub.add_parser("status", help="Ver quanto falta para concluir a amostra")
    s.add_argument("--saida", type=Path, default=SAIDA)
    a = sub.add_parser("avaliar", help="Avaliar modelos congelados uma unica vez")
    a.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args(argv)
    try:
        if args.comando == "preparar":
            result = preparar(args.repos, saida=args.saida, quantidade=args.quantidade)
        elif args.comando == "rotular":
            result = {"rotulados": rotular(saida=args.saida, tamanho=args.tamanho,
                                          limite=args.limite)}
        elif args.comando == "status":
            result = status(args.saida)
        else:
            result = avaliar(saida=args.saida)
    except (ValueError, OSError, subprocess.TimeoutExpired, csv.Error, json.JSONDecodeError) as e:
        parser.error(str(e))
    if args.comando == "avaliar":
        for nome, dados in result["modelos"].items():
            print(f"{nome}: acuracia {dados['acuracia']:.1%} | macro-F1 {dados['macro_f1']:.3f}")
        print("Relatorio:", args.saida / "resultado/relatorio.md")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
