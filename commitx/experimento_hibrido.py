"""Experimento exploratorio: mensagem vs mensagem + estatisticas de diff.

Executa validacao cruzada deixando um repositorio de treino por vez fora.
Nao utiliza as particoes validacao/teste, nem acessa os diffs completos.
"""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path

from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.dummy import DummyClassifier
from scipy.sparse import hstack

from .escrita import texto_modelo

ENTRADA = Path("resultados/fase2/base-local-treino-01.csv")
SAIDA = Path("resultados/fase2/experimento-hibrido-v1")
CLASSES = ("fix", "feat", "docs", "refactor", "test")


def _carregar(entrada):
    with Path(entrada).open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        obrigatorias = {
            "id", "repositorio", "particao", "titulo", "descricao",
            "categoria_humana", "arquivos_alterados", "linhas_adicionadas",
            "linhas_removidas", "proveniencia_diff", "diff_truncado",
        }
        ausentes = obrigatorias - set(leitor.fieldnames or [])
        if ausentes:
            raise ValueError("CSV incompleto: " + ", ".join(sorted(ausentes)))
        linhas = []
        ids = set()
        for linha in leitor:
            # Nunca usar particoes reservadas, mesmo se o CSV as contiver.
            if linha["particao"] != "treino":
                continue
            if linha["categoria_humana"] not in CLASSES:
                continue
            uid = linha["id"]
            if uid in ids:
                raise ValueError("ID duplicado no conjunto de treino")
            ids.add(uid)
            if linha["proveniencia_diff"] != "git_local_sha_confirmado":
                raise ValueError("Diff sem proveniencia Git verificada")
            if not linha["repositorio"].strip():
                raise ValueError("Repositorio vazio")
            try:
                texto = texto_modelo(linha["titulo"], linha["descricao"])
                adicionadas = int(linha["linhas_adicionadas"])
                removidas = int(linha["linhas_removidas"])
            except (ValueError, TypeError) as erro:
                raise ValueError("Texto ou estatistica numerica invalida") from erro
            if not texto.strip() or min(adicionadas, removidas) < 0:
                raise ValueError("Texto vazio ou contagem negativa")
            arquivos = [a for a in linha["arquivos_alterados"].split(";") if a.strip()]
            if not arquivos:
                raise ValueError("Registro sem arquivos alterados")
            # Extensoes sao categorizadas de maneira simples e limitada.
            extensoes = Counter(
                Path(a).suffix.lower() or "<sem_extensao>" for a in arquivos
            )
            atributos = {
                "log_linhas_adicionadas": math.log1p(adicionadas),
                "log_linhas_removidas": math.log1p(removidas),
                "log_total_alteracoes": math.log1p(adicionadas + removidas),
                "log_num_arquivos": math.log1p(len(arquivos)),
            }
            for extensao, n in extensoes.items():
                atributos["extensao=" + extensao] = n
            linhas.append({
                "id": uid,
                "repositorio": linha["repositorio"],
                "texto": texto,
                "categoria": linha["categoria_humana"],
                "atributos": atributos,
                "diff_truncado": linha["diff_truncado"],
            })
    return linhas


def _avaliar_fold(treino, validacao):
    textos_t = [r["texto"] for r in treino]
    textos_v = [r["texto"] for r in validacao]
    y = [r["categoria"] for r in treino]
    if len(set(y)) < 2:
        return None
    vet = TfidfVectorizer(strip_accents="unicode", ngram_range=(1, 2),
                          sublinear_tf=True, min_df=1)
    xt = vet.fit_transform(textos_t)
    xv = vet.transform(textos_v)
    model_a = LogisticRegression(
        max_iter=1000, random_state=42, class_weight="balanced"
    ).fit(xt, y)
    pred_a = model_a.predict(xv)

    # Transformadores ajustados APENAS nas amostras de treino do fold.
    met = DictVectorizer()
    dt = met.fit_transform([r["atributos"] for r in treino])
    dv = met.transform([r["atributos"] for r in validacao])
    # Rescala numericos, mas nao usa a validacao no ajuste.
    from sklearn.preprocessing import StandardScaler
    scale = StandardScaler(with_mean=False)
    dt = scale.fit_transform(dt)
    dv = scale.transform(dv)
    hb_t = hstack([xt, dt], format="csr")
    hb_v = hstack([xv, dv], format="csr")
    model_b = LogisticRegression(
        max_iter=1000, random_state=42, class_weight="balanced"
    ).fit(hb_t, y)
    pred_b = model_b.predict(hb_v)
    dummy = DummyClassifier(strategy="most_frequent").fit(xt, y)
    pred_dummy = dummy.predict(xv)
    return pred_a, pred_b, pred_dummy


def executar(entrada=ENTRADA, saida=SAIDA):
    entrada, saida = Path(entrada), Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Pasta de resultados ja existe: " + str(saida))
    registros = _carregar(entrada)
    repos = sorted({r["repositorio"] for r in registros})
    if len(repos) < 3:
        raise ValueError("Pelo menos tres repositorios de treino sao necessarios")
    saidas = []
    folds = []
    for repo in repos:
        treino = [r for r in registros if r["repositorio"] != repo]
        val = [r for r in registros if r["repositorio"] == repo]
        resposta = _avaliar_fold(treino, val)
        if resposta is None:
            folds.append({"repositorio": repo, "avaliado": False,
                          "motivo": "menos de duas classes no treino do fold"})
            continue
        a, b, dummy = resposta
        folds.append({
            "repositorio": repo, "avaliado": True,
            "quantidade": len(val),
            "classes_treino": dict(Counter(r["categoria"] for r in treino)),
            "classes_verificacao": dict(Counter(r["categoria"] for r in val)),
        })
        for r, pa, pb, pd in zip(val, a, b, dummy):
            saidas.append({
                "id": r["id"], "repositorio": repo, "real": r["categoria"],
                "modelo_a": str(pa), "modelo_b": str(pb), "baseline": str(pd),
            })
    if not saidas:
        raise ValueError("Nenhum fold pode ser avaliado")
    reais = [r["real"] for r in saidas]
    metricas = {}
    for campo in ("modelo_a", "modelo_b", "baseline"):
        previstos = [r[campo] for r in saidas]
        metricas[campo] = {
            "acuracia": float(accuracy_score(reais, previstos)),
            "macro_f1": float(f1_score(reais, previstos, labels=list(CLASSES),
                                       average="macro", zero_division=0)),
            "acertos": sum(r == p for r, p in zip(reais, previstos)),
        }
    relatorio = {
        "protocolo": "leave-one-repository-out-treino-exploratorio-v1",
        "total_entrada_elegivel": len(registros),
        "total_avaliado": len(saidas),
        "repositorios": len(repos),
        "distribuicao": dict(Counter(reais)),
        "metricas": metricas,
        "folds": folds,
        "restricoes": [
            "Somente particao treino; validacao formal e teste reservados intocados.",
            "Rotulos foram em parte assistidos por IA; nao sao gabarito independente.",
            "Apenas cinco repositorios e amostra pequena; resultado exploratorio.",
            "O modelo B usa estatisticas de linhas e extensoes, NAO conteudo do diff.",
            "Os modelos sao treinados do zero a cada fold, sem vazamento de vocabulario.",
            "A comparacao usa exatamente os mesmos exemplos para os dois modelos.",
            "Ausencia de alguma classe no treino de um fold torna suas previsoes limitadas.",
            "Nao comparar esta acuracia diretamente com os 53,8% da validacao anterior.",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    with (saida / "resumo.json").open("x", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with (saida / "previsoes.csv").open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "id", "repositorio", "real", "modelo_a", "modelo_b", "baseline"
        ])
        w.writeheader()
        w.writerows(saidas)
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(executar(args.entrada, args.saida),
                         ensure_ascii=False, indent=2))
    except (ValueError, OSError, csv.Error) as erro:
        parser.error(str(erro))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
