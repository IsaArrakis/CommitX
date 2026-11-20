"""CommitX academico: treina, expande treino opcionalmente e classifica CSV grande.

Entrada de treinamento: somente rotulos humanos da particao TREINO original.
Pseudo-rotulos sao dados fracos; nunca sobrescrevem SQLite ou rotulos humanos.
Nao mede acuracia com previsoes automaticas nem toca no teste reservado.

Comandos:
 python -m commitx.academico executar --entrada CSV --saida PASTA
 python -m commitx.academico analisar --modelo PASTA --titulo "Corrige login"
"""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from joblib import dump, load
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from .escrita import texto_modelo, parse_cabecalho
from .experimento_v3 import carregar_treino
from .treino_real import ENTRADA as PREPARADO, BANCO, CATEGORIAS_VALIDAS

CLASSES = tuple(CATEGORIAS_VALIDAS)
COLUNAS_TITULO = ("titulo", "title", "mensagem", "message", "commit_message")
BATCH = 500
MODELO = "modelo.joblib"


def _modelo():
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2), strip_accents="unicode", sublinear_tf=True,
            max_features=50000)),
        ("model", LinearSVC(class_weight="balanced", random_state=42, C=1.0)),
    ])


def _coluna(campos):
    for nome in COLUNAS_TITULO:
        if nome in campos:
            return nome
    raise ValueError("CSV precisa de coluna titulo (ou title, mensagem, message).")


def _linhas(arquivo):
    with Path(arquivo).open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        coluna = _coluna(leitor.fieldnames or [])
        for numero, row in enumerate(leitor, 1):
            titulo = (row.get(coluna) or "").splitlines()[0].strip()
            yield numero, row, titulo


def _text(titulo):
    try:
        return texto_modelo(titulo, "")
    except ValueError:
        return ""


def _pontuacoes(model, textos):
    decisions = model.decision_function(textos)
    classes = list(model.named_steps["model"].classes_)
    rows = []
    for vec in decisions:
        ordem = sorted(range(len(classes)), key=lambda j: float(vec[j]), reverse=True)
        i, j = ordem[:2]
        rows.append((classes[i], classes[j], float(vec[i] - vec[j])))
    return rows


def _exclusoes(preparado):
    """Bloqueia IDs e textos da base conhecida; e repositorios reservados."""
    arquivo = Path(preparado)
    ids, titulos, repos_reservados = set(), set(), set()
    if not arquivo.is_file():
        raise ValueError("CSV preparado nao encontrado: " + str(arquivo))
    with arquivo.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        obrig = {"id", "titulo", "particao", "repositorio"}
        if not obrig.issubset(leitor.fieldnames or []):
            raise ValueError("CSV preparado sem colunas de controle")
        for row in leitor:
            ids.add((row["id"] or "").strip())
            title = _text((row["titulo"] or "").strip())
            if title:
                titulos.add(" ".join(title.casefold().split()))
            if row["particao"] != "treino":
                for repo in (row.get("repositorio") or "").split(","):
                    if repo.strip():
                        repos_reservados.add(repo.strip())
    return ids, titulos, repos_reservados


def _batch_previsoes(model, batch):
    textos = [_text(title) for _, _, title in batch]
    valid = [i for i,t in enumerate(textos) if t]
    resultados = [None] * len(batch)
    if valid:
        x = [textos[i] for i in valid]
        vectors = model.named_steps["tfidf"].transform(x)
        pred = _pontuacoes(model, x)
        for k, (classe, segunda, margem) in zip(valid, pred):
            _, row, titulo = batch[k]
            parsed = parse_cabecalho(titulo)
            declarado = parsed["tipo"] if parsed else ""
            resultados[k] = {
                "categoria_prevista": str(classe),
                "segunda_opcao": str(segunda),
                "margem_svm": round(margem, 4),
                "tipo_declarado": declarado,
                "revisar": int(margem < 0.65 or (declarado in CLASSES and declarado != classe)),
            }
    return resultados


def _pseudo(model, entrada, prepared, *, minimo=1.5, max_por_classe=2000):
    if max_por_classe == 0:
        return [], Counter(), Counter()
    if minimo < 0:
        raise ValueError("Margem minima deve ser nao-negativa")
    excluidos_id, excluidos_titulo, repos_proibidos = _exclusoes(prepared)
    escolhidos = defaultdict(list)
    descartados = Counter()
    lote = []
    vistos = set(excluidos_titulo)

    def consumir():
        if not lote:
            return
        preds = _batch_previsoes(model, lote)
        for (_, row, titulo), p in zip(lote, preds):
            if p is None or p["margem_svm"] < minimo or p["revisar"]:
                descartados["baixa_margem_ou_invalido"] += 1
                continue
            cat = p["categoria_prevista"]
            if len(escolhidos[cat]) >= max_por_classe:
                descartados["limite_por_classe"] += 1
                continue
            chave = " ".join(_text(titulo).casefold().split())
            uid = (row.get("id") or row.get("sha") or "").strip()
            if not chave or chave in vistos or uid in excluidos_id:
                descartados["duplicado_ou_ja_rotulado"] += 1
                continue
            repo = row.get("repositorio") or row.get("repository") or ""
            repo_set = {s.strip() for s in repo.split(",") if s.strip()}
            particao = (row.get("particao") or "").lower().strip()
            if particao in ("teste", "validacao") or repo_set & repos_proibidos:
                descartados["particao_reservada"] += 1
                continue
            vistos.add(chave)
            escolhidos[cat].append((titulo, cat))
    for num, row, titulo in _linhas(entrada):
        lote.append((num,row,titulo))
        if len(lote) >= BATCH:
            consumir()
            lote.clear()
    consumir()
    pseudo = [rec for cls in CLASSES for rec in escolhidos[cls]]
    return pseudo, Counter({c:len(escolhidos[c]) for c in CLASSES}), descartados


def executar(*, entrada, saida, preparado=PREPARADO, banco=BANCO,
             pseudo_max_por_classe=0, margem=1.5, tamanho_lote=BATCH):
    entrada, saida = Path(entrada), Path(saida)
    if not entrada.is_file():
        raise ValueError("Arquivo de commits nao encontrado: " + str(entrada))
    if saida.exists():
        raise FileExistsError("Saida existente, escolha pasta nova: " + str(saida))
    if pseudo_max_por_classe < 0 or not 1 <= tamanho_lote <= 5000:
        raise ValueError("Quantidade de pseudo rotulos ou lote invalido")
    train = carregar_treino(preparado, banco)
    counts = Counter(x["categoria"] for x in train)
    if set(counts) != set(CLASSES) or min(counts.values()) < 5:
        raise ValueError("Treino supervisionado requer as cinco classes com >=5 rotulos")
    titles = [r["titulo"] for r in train]
    labels = [r["categoria"] for r in train]
    teacher = _modelo()
    teacher.fit(titles, labels)
    pseudo, pseudo_counts, descartados = _pseudo(
        teacher, entrada, preparado, minimo=margem,
        max_por_classe=pseudo_max_por_classe,
    )
    final = teacher
    if pseudo:
        final = _modelo()
        final.fit(titles + [t for t,c in pseudo], labels + [c for t,c in pseudo])
    saida.mkdir(parents=True, exist_ok=False)
    dump(final, saida/MODELO)
    destino = saida/"previsoes.csv"
    counts_pred = Counter()
    total = 0
    revisao = 0
    buffer = []
    with destino.open("x", encoding="utf-8", newline="") as f:
        keys = ["id", "titulo", "categoria_prevista", "segunda_opcao",
                "margem_svm", "tipo_declarado", "revisar"]
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()

        def gravar():
            nonlocal total, revisao
            predictions = _batch_previsoes(final, buffer)
            for (index,row,titulo), p in zip(buffer,predictions):
                p = p or {"categoria_prevista":"", "segunda_opcao":"",
                          "margem_svm":"", "tipo_declarado":"", "revisar":1}
                writer.writerow({"id":row.get("id") or row.get("sha") or str(index),
                                 "titulo":titulo, **p})
                counts_pred[p["categoria_prevista"] or "sem_classificacao"] += 1
                total += 1
                revisao += int(p["revisar"])
        for number,row,title in _linhas(entrada):
            buffer.append((number,row,title))
            if len(buffer) >= tamanho_lote:
                gravar()
                buffer.clear()
        if buffer:
            gravar()
    summary = {
        "total_classificado":total,
        "treino_humano_assistido":len(train),
        "categorias_treino":dict(counts),
        "pseudo_rotulos_adicionados":len(pseudo),
        "pseudo_por_classe":dict(pseudo_counts),
        "descartes_pseudo":dict(descartados),
        "categorias_previstas":dict(counts_pred),
        "revisao_sugerida":revisao,
        "margem_pseudo_minima":margem,
        "modelo":"TF-IDF palavra 1-2gram + LinearSVC balanceada",
        "avaliacao":"NAO realizada neste comando. Previsoes e pseudo rotulos NAO sao gabarito.",
        "limites":[
            "Rótulos de treino anteriores podem ter sido assistidos por IA.",
            "Pseudo-rotulos podem conter erros e piorar o desempenho.",
            "Margens SVM nao sao probabilidades calibradas.",
            "Teste reservado e validacao nao foram lidos como rotulos de treino.",
            "Previsoes de todos os commits nao comprovam acuracia.",
        ],
        "modelo_salvo":str(saida/MODELO),
        "previsoes_csv":str(destino),
    }
    (saida/"resumo.json").write_text(json.dumps(summary, indent=2,
        ensure_ascii=False)+"\n",encoding="utf-8")
    return summary


def analisar(modelo, titulo):
    if not titulo.strip():
        raise ValueError("Titulo vazio")
    p = _batch_previsoes(modelo, [(1,{},titulo)])[0]
    return {"titulo":titulo, **(p or {"categoria_prevista":"",
                                    "motivo":"Sem conteudo apos prefixo"})}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="acao",required=True)
    run=sub.add_parser("executar",help="Treinar e classificar CSV em lotes")
    run.add_argument("--entrada",type=Path,required=True)
    run.add_argument("--saida",type=Path,default=Path("resultados/academico-simples-01"))
    run.add_argument("--preparado",type=Path,default=PREPARADO)
    run.add_argument("--banco",type=Path,default=BANCO)
    run.add_argument("--pseudo-max-por-classe",type=int,default=0)
    run.add_argument("--margem",type=float,default=1.5)
    run.add_argument("--lote",type=int,default=BATCH)
    single=sub.add_parser("analisar",help="Classificar um titulo")
    single.add_argument("--modelo",type=Path,required=True)
    single.add_argument("--titulo",required=True)
    a=p.parse_args(argv)
    try:
        if a.acao=="executar":
            result=executar(entrada=a.entrada,saida=a.saida,preparado=a.preparado,
                           banco=a.banco,pseudo_max_por_classe=a.pseudo_max_por_classe,
                           margem=a.margem,tamanho_lote=a.lote)
        else:
            path=a.modelo/MODELO if a.modelo.is_dir() else a.modelo
            if not path.is_file():
                raise FileNotFoundError(str(path))
            result=analisar(load(path), a.titulo)  # so carregar artefatos locais confiaveis
    except (OSError,ValueError,csv.Error) as err:
        p.error(str(err))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
