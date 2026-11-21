"""Comparacao CEGA em validacao V5, sem alterar bancos ou modelos.

Exige rotulos humanos previamente registrados na particao validacao V5.
Os resultados sao exploratorios se houver sobreposicao de repositorios/titulos
com treino antigo; nunca utiliza particao teste V5.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sqlite3

from joblib import load
from sklearn.metrics import accuracy_score, f1_score, classification_report

from .classificador_hibrido import carregar_modelo, prever_lote
from .escrita import texto_modelo
from .experimento_v3 import carregar_treino
from .revisao_git_v5 import abrir, ENTRADA, PLANO, BANCO
from .treino_real import ENTRADA as PREPARADO, BANCO as BANCO_ANTIGO

CLASSES = ("fix", "feat", "docs", "refactor", "test")


def _nome_repo(s):
    s = str(s).strip().rstrip("/")
    if s.startswith("git:"):
        s = s[4:]
    return s.split("/")[-1].casefold()


def avaliar(*, entrada=ENTRADA, plano=PLANO, banco=BANCO,
            preparado=PREPARADO, banco_antigo=BANCO_ANTIGO,
            original=Path("resultados/academico-simples-01/modelo.joblib"),
            hibrido=Path("resultados/classificador-hibrido-v4"),
            saida=Path("resultados/comparacao-cega-v7-01")):
    saida = Path(saida)
    if saida.exists():
        raise FileExistsError("Saida existente: " + str(saida))
    rows, plan = abrir(entrada=entrada, plano=plano, banco=banco)
    with sqlite3.connect("file:" + Path(banco).resolve().as_posix() + "?mode=ro", uri=True) as con:
        gold = dict(con.execute("SELECT id,categoria FROM avaliacoes"))
    candidatos = [r for r in rows
                  if plan["repositorios"][r["repositorio"]] == "validacao"
                  and gold.get(r["id"]) in CLASSES]
    if not candidatos:
        raise ValueError("Ainda nao existem rotulos V5 de validacao. "
                         "Execute revisao_git_v5 revisar --particao validacao.")
    treino = carregar_treino(preparado, banco_antigo)
    titulos_treino = {" ".join(r["titulo"].casefold().split()) for r in treino}
    repos_treino = {_nome_repo(repo) for r in treino for repo in r["repositorios"]}
    linhas = []
    for r in candidatos:
        texto = texto_modelo(r["titulo"], "")
        if not texto:
            continue
        colisao_repo = _nome_repo(r["repositorio"]) in repos_treino
        colisao_titulo = " ".join(texto.casefold().split()) in titulos_treino
        linhas.append((r, texto, colisao_repo, colisao_titulo))
    seguros = [(r,t) for r,t,cr,ct in linhas if not cr and not ct]
    if not seguros:
        raise ValueError("Nenhum exemplo elegivel apos filtrar repositorios e titulos repetidos")
    x = [t for r,t in seguros]
    y = [gold[r["id"]] for r,t in seguros]
    bas = load(original)  # Somente joblib local e confiavel.
    pred_bas = [str(v) for v in bas.predict(x)]
    art = carregar_modelo(hibrido)
    pred_hib = [p["categoria_prevista"] for p in prever_lote(art,[r["titulo"] for r,t in seguros])]
    resultados = {}
    for nome, pred in (("svm_original", pred_bas), ("hibrido_v4", pred_hib)):
        resultados[nome] = {
            "acuracia":round(float(accuracy_score(y,pred)),4),
            "macro_f1":round(float(f1_score(y,pred,labels=list(CLASSES),average="macro",zero_division=0)),4),
            "por_classe":classification_report(y,pred,labels=list(CLASSES),output_dict=True,zero_division=0),
            "acertos":sum(a==b for a,b in zip(y,pred)),
        }
    saida.mkdir(parents=True, exist_ok=False)
    with (saida/"previsoes.csv").open("x",encoding="utf-8",newline="") as f:
        campos=["id","titulo","categoria_real","original","hibrido","acerto_original","acerto_hibrido"]
        writer=csv.DictWriter(f,fieldnames=campos)
        writer.writeheader()
        for (r,t),a,b,real in zip(seguros,pred_bas,pred_hib,y):
            writer.writerow({"id":r["id"],"titulo":r["titulo"],"categoria_real":real,
                             "original":a,"hibrido":b,
                             "acerto_original":int(a==real),"acerto_hibrido":int(b==real)})
    resumo={
       "protocolo":"comparacao-V5-validacao-cega-modelos-congelados",
       "rotulos_validacao_v5":len(candidatos),
       "avaliados":len(seguros),
       "excluidos_por_overlap":len(linhas)-len(seguros),
       "distribuicao_reais":dict(Counter(y)),
       "modelos":resultados,
       "modelo_hibrido_melhorou":resultados["hibrido_v4"]["acertos"]>resultados["svm_original"]["acertos"],
       "nota":"Validacao exploratoria pequena. Repositorios comparados por nome base e titulos; "
              "isso NAO garante ausencia de vazamento indireto. "
              "Base V5 pode ter sido assistida por IA; testar futuramente em projetos novos e rotulos independentes. "
              "Particao teste V5 nao foi acessada.",
    }
    (saida/"resumo.json").write_text(json.dumps(resumo,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return resumo


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--saida",type=Path,default=Path("resultados/comparacao-cega-v7-01"))
    p.add_argument("--original",type=Path,default=Path("resultados/academico-simples-01/modelo.joblib"))
    p.add_argument("--hibrido",type=Path,default=Path("resultados/classificador-hibrido-v4"))
    args=p.parse_args()
    try:
        resumo=avaliar(saida=args.saida,original=args.original,hibrido=args.hibrido)
    except (OSError,ValueError,sqlite3.Error) as e:
        p.error(str(e))
    for nome,dados in resumo["modelos"].items():
        print(f"{nome}: {dados['acertos']}/{resumo['avaliados']} | acuracia {dados['acuracia']:.1%} | macro-F1 {dados['macro_f1']:.3f}")
    print("Resumo:",args.saida/"resumo.json")


if __name__=="__main__":
    main()
