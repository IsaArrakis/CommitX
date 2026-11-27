"""Compara V12/V13 nas cinco divisões históricas dos 397 exemplos originais."""
import argparse
from collections import Counter
import csv
from itertools import chain
import json
from pathlib import Path
import re
import tempfile

import joblib
import numpy as np
import sklearn
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold

from .dados_v13 import EXPANSAO, carregar
from .foco_docs_refactor_v10 import pesos_do_fold
from .modelo_v13 import (
    ARQUIVOS, CONFIGS, MARGEM_MINIMA, MODOS, PESOS_ORIGEM, SAIDA, VERSAO,
    escopo_titulo, normalizar, prever, sugestao, texto_classificador, treinar_modelo,
)
from .v12_final import (
    BANCO_PADRAO, CLASSES, ENTRADA_PADRAO, REF_COM_PADRAO, REF_SEM_PADRAO,
    SEMENTE, _ler_csv, _sha256, novo_modelo_v12,
)

SEM_SUGESTAO = "abstencao"
V12 = "v12_extra_030"
# Marcadores funcionais exclusivos dos dois cortes. O idioma é estimado
# somente para relatórios, sem acesso aos rótulos ou às previsões.
MARCADORES = {
    "en": set("the to and for of with when from this that should while without into which".split()),
    "pt": set("para que com quando uma dos das pelo pela apos nao tambem durante entre sobre ao aos".split()),
}


def idioma_estimado(titulo):
    palavras = set(re.findall(r"\b[a-z]+\b", normalizar(titulo)))
    pt, en = (len(palavras & MARCADORES[i]) for i in ("pt", "en"))
    if pt >= 2 and en == 0:
        return "pt"
    if en >= 2 and pt == 0:
        return "en"
    return "incerto"


def distribuicao(registros):
    return {origem: dict(Counter(r.categoria for r in registros if r.origem == origem))
            for origem in PESOS_ORIGEM}


def metricas(y, preds):
    y = np.asarray(y)
    preds = np.asarray([p or SEM_SUGESTAO for p in preds])
    cobertos = preds != SEM_SUGESTAO
    relatorio = classification_report(y, preds, labels=CLASSES, output_dict=True, zero_division=0)
    return {
        "n": len(y),
        "acuracia": float(np.mean(y == preds)),
        "macro_f1": relatorio["macro avg"]["f1-score"],
        "cobertura": float(np.mean(cobertos)),
        "abstencoes": int(sum(~cobertos)),
        "acuracia_nas_sugestoes": float(np.mean(y[cobertos] == preds[cobertos])) if any(cobertos) else None,
        "por_categoria": {c: relatorio[c] for c in CLASSES},
        "matriz_confusao": confusion_matrix(y, preds, labels=(*CLASSES, SEM_SUGESTAO))[:-1].tolist(),
    }


def _referencias(historico, ref_com, ref_sem, folds):
    ids, com, sem, y, grupos = historico
    referencias = []
    for caminho in (ref_com, ref_sem):
        linhas = _ler_csv(caminho)
        por_id = {r["id"]: r for r in linhas}
        if len(linhas) != len(ids) or set(ids) != por_id.keys():
            raise ValueError(f"Referência histórica com IDs ausentes ou duplicados: {caminho}")
        referencias.append(por_id)
    a, b = referencias
    for n, (_, iv) in enumerate(folds, 1):
        for i in iv:
            uid = ids[i]
            ac, bs = a[uid], b[uid]
            if ((com[i], y[i], grupos[i]) != (ac["titulo"], ac["rotulo_registrado"], ac["grupo"])
                    or (com[i], sem[i], y[i], grupos[i], str(n), ac[V12]) != (
                        bs["titulo_original"], bs["titulo_sem_prefixo"], bs["real"], bs["grupo"],
                        bs["fold"], bs["v12_com_prefixo"])):
                raise ValueError(f"Metadados/fold divergentes das referências históricas: {uid}")
    return {MODOS[0]: [a[uid][V12] for uid in ids],
            MODOS[1]: [b[uid]["v12_sem_prefixo"] for uid in ids]}


def _avaliar(originais, extras, historico, componentes, descartes, ref_com, ref_sem):
    ids, com, sem, y, grupos = historico
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMENTE)
                 .split(np.zeros(len(ids)), y, grupos))
    refs = _referencias(historico, ref_com, ref_sem, folds)
    pred = {(nome, modo): [None] * len(y) for nome in (V12, *CONFIGS) for modo in MODOS}
    bruto = {chave: destino.copy() for chave, destino in pred.items() if chave[0] != V12}
    motivos_escopo = [escopo_titulo(titulo)[1] for titulo in com]
    linhas_oof = []
    tamanho_treino = []
    for fold, (it, iv) in enumerate(folds, 1):
        if set(grupos[it]) & set(grupos[iv]) or set(y[it]) != set(CLASSES) or set(y[iv]) != set(CLASSES):
            raise ValueError("Divisão incompatível com o protocolo da V12.")
        bloqueados = {componentes[ids[i]] for i in iv}
        treino = [r for r in chain((originais[i] for i in it), extras) if r.id not in descartes and componentes[r.id] not in bloqueados]
        if {r.categoria for r in treino} != set(CLASSES):
            raise ValueError(f"Fold {fold} da V13 sem todas as classes de treino.")
        tamanho_treino.append({"fold": fold, "v12": len(it), "v13": len(treino), "avaliacao": len(iv),
                               "v13_por_origem_e_categoria": distribuicao(treino)})
        pesos = pesos_do_fold(y[it], 1.75, 1.50)
        for modo, titulos in zip(MODOS, (com, sem)):
            base = novo_modelo_v12(pesos).fit([titulos[i] for i in it], y[it])
            # A referência histórica é a previsão SVM sem abstenção.
            for i, p in zip(iv, base.predict([titulos[i] for i in iv])):
                if p != refs[modo][i]:
                    raise ValueError(f"Previsão V12 divergente da referência: fold {fold}, {modo}, {ids[i]}.")
                pred[V12, modo][i] = str(p)
            textos = [texto_classificador(com[i], modo) for i in iv]
            for config in CONFIGS:
                modelo = treinar_modelo(config, treino, modo)
                for i, (categoria, margem) in zip(iv, prever(modelo, textos)):
                    aceito = None if motivos_escopo[i] else sugestao(categoria, margem)
                    bruto[config, modo][i] = categoria
                    pred[config, modo][i] = aceito
                    linhas_oof.append({
                        "id": ids[i], "fold": fold, "modo": modo, "modelo": config,
                        "real": str(y[i]), "v12": refs[modo][i], "v13_sem_abstencao": categoria,
                        "v13": aceito or SEM_SUGESTAO, "margem_svm": margem,
                        "motivo_escopo": motivos_escopo[i],
                    })
        print(f"Fold {fold}/5: treino V12={len(it)}, V13={len(treino)}.", flush=True)

    idiomas = [r.idioma if r.idioma in {"en", "pt"} else idioma_estimado(r.titulo) for r in originais]
    cortes = {idioma: [i for i, v in enumerate(idiomas) if v == idioma] for idioma in ("pt", "en", "incerto")}
    resultados = {}
    for (nome, modo), estimativas in pred.items():
        res = metricas(y, estimativas)
        if nome != V12:
            res["sem_abstencao"] = metricas(y, bruto[nome, modo])
        res["por_idioma"] = {}
        for idioma, idx in cortes.items():
            co = Counter(y[idx])
            n_grupos = len(set(grupos[idx]))
            suporte = (idioma != "incerto" and len(idx) >= 30 and n_grupos >= 5
                       and min(co.get(c, 0) for c in CLASSES) >= 3)
            corte = {"n": len(idx), "grupos_v12": n_grupos, "classes": dict(co), "suporte": suporte}
            if suporte:
                corte["metricas"] = metricas(y[idx], [estimativas[i] for i in idx])
            res["por_idioma"][idioma] = corte
        resultados.setdefault(nome, {})[modo] = res
    return resultados, tamanho_treino, linhas_oof


def executar(entrada, banco, expansao, ref_com, ref_sem, saida):
    if saida.exists() or saida.is_symlink():
        raise FileExistsError(f"A pasta de saída já existe: {saida}")
    originais, extras, historico, componentes, auditoria = carregar(entrada, banco, expansao)
    descartes = auditoria["descartes"]
    resultados, treino_cv, linhas = _avaliar(originais, extras, historico, componentes, descartes, ref_com, ref_sem)
    # As mesmas divisões servem para comparar e escolher a configuração. O
    # resultado da escolhida permanece exploratório e sujeito a viés de seleção.
    escolhido = max(CONFIGS, key=lambda c: (
        resultados[c]["sem_prefixo"]["acuracia"], resultados[c]["sem_prefixo"]["macro_f1"],
        resultados[c]["com_prefixo"]["acuracia"],
    ))
    treino = [r for r in originais if r.id not in descartes] + extras
    auditoria.update({"total_potencial": 1306, "total_treino_final": len(treino),
                      "treino_final_por_origem_e_categoria": distribuicao(treino),
                      "treino_por_fold": treino_cv})
    diagnostico = []
    for titulo in ("integrar analise AST opcional a API Git", "comparar estruturas AST de arquivos Python"):
        historico_ids = [r.id for r in treino if texto_classificador(r.titulo, MODOS[1]) == normalizar(titulo)]
        diagnostico.append({"titulo": titulo, "ids_com_titulo_no_treino": historico_ids})

    _, _, sem, y, _ = historico
    baseline = novo_modelo_v12(pesos_do_fold(y, 1.75, 1.50)).fit(sem, y)
    vetores_v12 = baseline.named_steps["tfidf"]
    tfidf_v12 = dict(vetores_v12.transformer_list)["palavras"]
    textos_v12 = [r["titulo"] for r in diagnostico]
    for linha, (categoria, margem) in zip(diagnostico, prever(baseline, textos_v12)):
        termos = tfidf_v12.build_analyzer()(linha["titulo"])
        linha["v12_retreinada"] = {
            "classe_svm": categoria, "margem_svm": margem,
            "termos_tfidf_reconhecidos": sorted({t for t in termos if t in tfidf_v12.vocabulary_}),
            "total_termos_tfidf_distintos": len(set(termos)),
        }

    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v13-", dir=saida.parent) as temporario:
        pasta = Path(temporario)
        hashes = {}
        for modo, arquivo in ARQUIVOS.items():
            modelo = treinar_modelo(escolhido, treino, modo)
            joblib.dump(modelo, pasta / arquivo, compress=3)
            hashes[arquivo] = _sha256(pasta / arquivo)
            if modo == "sem_prefixo":
                textos = [texto_classificador(r["titulo"], modo) for r in diagnostico]
                for linha, (categoria, margem) in zip(diagnostico, prever(modelo, textos)):
                    linha.update({"classe_svm": categoria, "margem_svm": margem,
                                  "sugestao": sugestao(categoria, margem)})
        relatorio = {
            "avaliacao": "Validação cruzada exploratória no conjunto de desenvolvimento V12.",
            "idioma": "Cortes estimados por marcadores linguísticos, somente onde há suporte.",
            "ordem_classes_matriz": list(CLASSES),
            "colunas_matriz": [*CLASSES, SEM_SUGESTAO],
            "paridade_historica_v12": True,
            "pesos_por_origem": PESOS_ORIGEM,
            "margem_minima": MARGEM_MINIMA,
            "configuracao": escolhido,
            "dados": auditoria,
            "resultados": resultados,
            "diagnostico": diagnostico,
        }
        manifesto = {
            "versao": VERSAO, "configuracao": escolhido, "margem_minima": MARGEM_MINIMA,
            "artefatos_sha256": hashes, "scikit_learn": sklearn.__version__,
            "numpy": np.__version__, "joblib": joblib.__version__,
            "entradas_sha256": {nome: _sha256(path) for nome, path in (
                ("preparada", entrada), ("avaliacoes", banco), ("expansao", expansao),
                ("referencia_com_prefixo", ref_com), ("referencia_sem_prefixo", ref_sem),
            )},
        }
        with (pasta / "previsoes_oof.csv").open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(linhas[0]))
            escritor.writeheader()
            escritor.writerows(linhas)
        (pasta / "avaliacao.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
        (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
        saida.mkdir()
        for arquivo in (*ARQUIVOS.values(), "previsoes_oof.csv", "avaliacao.json", "manifesto.json"):
            (pasta / arquivo).rename(saida / arquivo)
    print(f"Experimento V13 salvo em {saida}. Configuração selecionada: {escolhido}.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA_PADRAO)
    parser.add_argument("--banco", type=Path, default=BANCO_PADRAO)
    parser.add_argument("--expansao", type=Path, default=EXPANSAO)
    parser.add_argument("--ref-com", type=Path, default=REF_COM_PADRAO)
    parser.add_argument("--ref-sem", type=Path, default=REF_SEM_PADRAO)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args(argv)
    try:
        executar(args.entrada, args.banco, args.expansao, args.ref_com, args.ref_sem, args.saida)
    except (ValueError, OSError) as erro:
        parser.error(str(erro))


if __name__ == "__main__":
    main()
