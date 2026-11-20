"""Avalie SOMENTE a particao validacao ja rotulada, sem treinar modelos.

Uma unica comparacao descritiva entre SVM titulo e hibrido V4 congelados.
Nao acessa ou calcula metricas na particao 'teste'. Nao edita SQLite, rotulos
ou artefatos treinados. Validação nao substitui teste externo independente.
"""
import argparse
from collections import Counter
import csv
import json
from math import sqrt
from pathlib import Path
import sqlite3

from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, classification_report

from .classificador_hibrido import carregar_modelo as carregar_hibrido
from .classificador_hibrido import prever_lote as prever_hibrido
from .classificador_real import carregar_modelo as carregar_simples
from .classificador_real import prever as prever_simples
from .classificador_real import _hash_arquivo
from .escrita import texto_modelo
from .experimento_v3 import CLASSES
from .treino_real import ENTRADA, BANCO, repositorios_da_linha


def ler_validacao(entrada=ENTRADA, banco=BANCO):
    """Carrega somente commits rotulados de validacao; teste e ignorado."""
    entrada, banco = Path(entrada), Path(banco)
    if not entrada.is_file() or not banco.is_file():
        raise ValueError("CSV preparado ou SQLite nao encontrado")
    treino, validacao, ids = [], [], set()
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"id", "titulo", "repositorio", "particao"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV sem id, titulo, repositorio ou particao")
        for r in reader:
            if r["particao"] not in ("treino", "validacao"):
                continue  # O teste reservado nao entra nem nos metadados lidos.
            if not r["id"] or r["id"] in ids:
                raise ValueError("ID vazio ou duplicado nas particoes de trabalho")
            ids.add(r["id"])
            if r["particao"] == "treino":
                treino.append(r)
            else:
                validacao.append(r)
    if not validacao:
        raise ValueError("Nenhum registro na particao validacao")

    with sqlite3.connect("file:" + banco.resolve().as_posix() + "?mode=ro", uri=True) as con:
        # Consultamos apenas a existencia do ID no treino; rótulos de teste nunca sao consultados.
        rotulados = {uid for (uid,) in con.execute("SELECT id FROM avaliacoes")}
        validos = []
        for r in validacao:
            if r["id"] not in rotulados:
                continue
            c = con.execute("SELECT categoria FROM avaliacoes WHERE id=?", (r["id"],)).fetchone()
            if c is None or c[0] not in CLASSES:
                continue
            if not r["titulo"].strip() or not r["repositorio"].strip():
                raise ValueError("Commit de validacao sem titulo ou repositorio")
            validos.append({
                "id": r["id"], "titulo": r["titulo"].strip(),
                "repositorio": r["repositorio"].strip(), "real": c[0],
            })
    treino_rotulado = [r for r in treino if r["id"] in rotulados]
    if not validos:
        raise ValueError("Nenhum rotulo valido encontrado em validacao")

    # Protecao: nao avaliar em repositórios usados durante o treino.
    repo_treino = set().union(*(repositorios_da_linha(r["repositorio"]) for r in treino_rotulado))
    repo_val = set().union(*(repositorios_da_linha(r["repositorio"]) for r in validos))
    sobreposicoes = sorted(repo_treino & repo_val)
    if sobreposicoes:
        raise ValueError(
            "Vazamento: repositorios de treino e validacao se repetem "
            f"({len(sobreposicoes)}). Nao avalie sem corrigir particoes."
        )

    # Titulos literalmente iguais apos retirar prefixos: uma segunda forma de vazamento.
    titulos_treino = {texto_modelo(r["titulo"], "").casefold().strip()
                     for r in treino_rotulado if r["titulo"].strip()}
    duplicados = [r["id"] for r in validos
                  if texto_modelo(r["titulo"], "").casefold().strip() in titulos_treino]
    if duplicados:
        raise ValueError(
            f"Vazamento: {len(duplicados)} titulos identicos entre treino e validacao. "
            "Precisa rever a particao; nenhum resultado foi gravado."
        )
    return validos


def _conferir_manifestos(entrada, banco, modelo_hibrido, modelo_simples):
    esperados = {
        "sha256_csv_preparado": _hash_arquivo(entrada),
        "sha256_banco_labels": _hash_arquivo(banco),
    }
    pasta_h = Path(modelo_hibrido)
    pasta_s = Path(modelo_simples)
    if not pasta_h.is_dir() or not pasta_s.is_dir():
        raise ValueError("Informe pastas de modelos treinados (nao caminhos joblib)")
    m_h = json.loads((pasta_h / "manifesto.json").read_text(encoding="utf-8"))
    m_s = json.loads((pasta_s / "manifesto.json").read_text(encoding="utf-8"))
    pares = (
        (m_h, "sha256_csv_preparado", esperados["sha256_csv_preparado"]),
        (m_h, "sha256_banco_labels", esperados["sha256_banco_labels"]),
        (m_s, "sha256_csv_preparado", esperados["sha256_csv_preparado"]),
        (m_s, "sha256_sqlite_rotulos", esperados["sha256_banco_labels"]),
    )
    if any(m.get(chave) != valor for m, chave, valor in pares):
        raise ValueError(
            "Banco ou CSV mudou desde o treinamento. Modelos e rotulos "
            "precisam pertencer ao mesmo snapshot. Nao avalie modelos antigos."
        )
    return {"csv_sha256": esperados["sha256_csv_preparado"],
            "banco_sha256": esperados["sha256_banco_labels"]}


def _wilson(acertos, total):
    """Intervalo Wilson aproximado de 95%, apenas indicativo em amostra pequena."""
    z = 1.96
    p = acertos / total
    d = 1 + z*z/total
    center = (p + z*z/(2*total)) / d
    spread = z*sqrt((p*(1-p) + z*z/(4*total))/total)/d
    return [max(0.0, center-spread), min(1.0, center+spread)]


def _metricas(reais, previstos):
    if len(reais) != len(previstos) or not reais:
        raise ValueError("Previsoes de validacao incompletas")
    acertos = sum(a == b for a, b in zip(reais, previstos))
    return {
        "acertos": acertos,
        "total": len(reais),
        "acuracia": float(accuracy_score(reais, previstos)),
        "intervalo_95_wilson_aproximado": _wilson(acertos, len(reais)),
        "macro_f1": float(f1_score(
            reais, previstos, labels=list(CLASSES), average="macro", zero_division=0
        )),
        "matriz_classes": list(CLASSES),
        "matriz_confusao": confusion_matrix(reais, previstos, labels=list(CLASSES)).tolist(),
        "por_classe": {
            k: {"precisao": float(v["precision"]),
                "recall": float(v["recall"]), "f1": float(v["f1-score"]),
                "suporte": int(v["support"])}
            for k, v in classification_report(
                reais, previstos, labels=list(CLASSES),
                output_dict=True, zero_division=0
            ).items() if k in CLASSES
        },
    }


def avaliar(*, entrada=ENTRADA, banco=BANCO,
           pasta_hibrido=Path("resultados/classificador-hibrido-v4"),
           pasta_simples=Path("resultados/classificador-real-01"),
           cache=Path("resultados/cache-embeddings-ollama-v4.json"),
           saida=Path("resultados/validacao-hibrido-v4-01")):
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("Nao sobrescrever resultados: " + str(saida))
    hashes = _conferir_manifestos(entrada, banco, pasta_hibrido, pasta_simples)
    validacao = ler_validacao(entrada, banco)
    modelo_h = carregar_hibrido(pasta_hibrido)
    modelo_s = carregar_simples(pasta_simples)
    titulos = [r["titulo"] for r in validacao]
    pred_h = prever_hibrido(modelo_h, titulos, cache=cache)
    pred_s = [prever_simples(modelo_s, titulo) for titulo in titulos]
    reais = [r["real"] for r in validacao]
    ph = [r["categoria_prevista"] for r in pred_h]
    ps = [r["categoria_prevista"] for r in pred_s]
    if any(x not in CLASSES for x in ph + ps):
        raise ValueError("Modelo produziu categoria fora das cinco classes")
    relatorio = {
        "protocolo": "validacao-v4-congelada-comparacao-pareada",
        "particao": "validacao",
        "validacao_quantidade": len(validacao),
        "distribuicao": dict(Counter(reais)),
        "snapshot": hashes,
        "svm_titulo": _metricas(reais, ps),
        "hibrido_v4": _metricas(reais, ph),
        "melhoria_absoluta_acuracia_pontos_percentuais":
            round(100 * (accuracy_score(reais, ph) - accuracy_score(reais, ps)), 2),
        "melhoria_absoluta_macro_f1":
            round(f1_score(reais, ph, labels=list(CLASSES), average="macro", zero_division=0)
                  - f1_score(reais, ps, labels=list(CLASSES), average="macro", zero_division=0), 4),
        "pareado": {
            "hibrido_certo_svm_errada": sum(h == y and s != y for h, s, y in zip(ph, ps, reais)),
            "svm_certa_hibrido_errado": sum(s == y and h != y for h, s, y in zip(ph, ps, reais)),
            "ambos_errados": sum(h != y and s != y for h, s, y in zip(ph, ps, reais)),
        },
        "limites": [
            "Validação previamente usada no projeto; nao equivale a um teste final cego.",
            "Amostra pequena; intervalos Wilson sao aproximacoes, nao previsao de desempenho futuro.",
            "Rótulos tiveram assistencia por IA e podem conter erros.",
            "Nao selecionar novos hiperparametros a partir deste resultado sem nova validacao.",
            "Particao teste nao utilizada nem prevista.",
            "Os dois modelos foram treinados previamente; nenhuma base foi modificada.",
        ],
    }
    previsoes = [{
        "id": r["id"], "repositorio": r["repositorio"], "titulo": r["titulo"],
        "real": r["real"], "svm_titulo": s, "hibrido": h,
        "acerto_svm": int(s == r["real"]), "acerto_hibrido": int(h == r["real"]),
        "divergencia_modelos": int(s != h),
    } for r, s, h in zip(validacao, ps, ph)]
    saida.mkdir(parents=True, exist_ok=False)
    (saida / "resumo.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for nome, linhas in (("previsoes.csv", previsoes),
                         ("erros_hibrido.csv", [p for p in previsoes if not p["acerto_hibrido"]])):
        with (saida / nome).open("x", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(previsoes[0]))
            writer.writeheader()
            writer.writerows(linhas)
    txt = [
        "# Validação do CommitX V4 (modelos congelados)", "",
        f"- Exemplos de validação: **{len(validacao)}**",
        f"- SVM título: **{relatorio['svm_titulo']['acuracia']:.1%}** de acurácia, macro-F1 **{relatorio['svm_titulo']['macro_f1']:.3f}**",
        f"- Híbrido V4: **{relatorio['hibrido_v4']['acuracia']:.1%}** de acurácia, macro-F1 **{relatorio['hibrido_v4']['macro_f1']:.3f}**",
        f"- Diferença absoluta: **{relatorio['melhoria_absoluta_acuracia_pontos_percentuais']:+.2f} pontos percentuais**",
        f"- Híbrido acerta onde SVM erra: {relatorio['pareado']['hibrido_certo_svm_errada']}",
        f"- SVM acerta onde híbrido erra: {relatorio['pareado']['svm_certa_hibrido_errado']}",
        "", "## Limitações", "",
    ] + ["- " + msg for msg in relatorio["limites"]]
    (saida / "resumo.md").write_text("\n".join(txt) + "\n", encoding="utf-8")
    return relatorio


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--banco", type=Path, default=BANCO)
    p.add_argument("--modelo-hibrido", type=Path, default=Path("resultados/classificador-hibrido-v4"))
    p.add_argument("--modelo-simples", type=Path, default=Path("resultados/classificador-real-01"))
    p.add_argument("--cache", type=Path, default=Path("resultados/cache-embeddings-ollama-v4.json"))
    p.add_argument("--saida", type=Path, default=Path("resultados/validacao-hibrido-v4-01"))
    args = p.parse_args(argv)
    try:
        resultado = avaliar(entrada=args.entrada, banco=args.banco,
                           pasta_hibrido=args.modelo_hibrido, pasta_simples=args.modelo_simples,
                           cache=args.cache, saida=args.saida)
    except (OSError, ValueError, sqlite3.Error, csv.Error) as e:
        p.error(str(e))
    for key in ("svm_titulo", "hibrido_v4"):
        m = resultado[key]
        print(f"{key}: {m['acertos']}/{m['total']} = {m['acuracia']:.1%} | macro-F1 {m['macro_f1']:.3f}")
        print("Por classe:", {c: round(s["recall"], 3) for c, s in m["por_classe"].items()})
    print("Diferenca em pontos percentuais:", resultado["melhoria_absoluta_acuracia_pontos_percentuais"])
    print("Relatorio:", args.saida / "resumo.md")


if __name__ == "__main__":
    main()
