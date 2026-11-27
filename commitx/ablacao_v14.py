"""Mede o efeito incremental da expansão com a configuração original da V12."""
import argparse
from collections import Counter
from itertools import chain
import json
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from .dados_v13 import EXPANSAO, ORIGENS, carregar
from .escrita import texto_modelo
from .experimento_v13 import _referencias, metricas
from .foco_docs_refactor_v10 import pesos_do_fold
from .v12_final import (
    BANCO_PADRAO, CLASSES, ENTRADA_PADRAO, REF_COM_PADRAO, REF_SEM_PADRAO, SEMENTE,
    novo_modelo_v12,
)

SAIDA = Path("resultados/ablacao-v14-01.json")
ORDEM = ("humano_v12", *ORIGENS.values())
CONDICOES = {nome: ORDEM[:n] for n, nome in enumerate("ABCD", 1)}


def avaliar(entrada, banco, expansao, ref_com, ref_sem):
    humanos, extras, historico, componentes, auditoria = carregar(entrada, banco, expansao)
    ids, _, titulos, y, grupos = historico
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMENTE)
                 .split(np.zeros(len(ids)), y, grupos))
    referencia = _referencias(historico, ref_com, ref_sem, folds)["sem_prefixo"]
    descartes = auditoria["descartes"]
    previsoes = {nome: [None] * len(y) for nome in CONDICOES}
    treinos = []
    for numero, (it, iv) in enumerate(folds, 1):
        bloqueados = {componentes[ids[i]] for i in iv}
        aptos = [
            r for r in chain((humanos[i] for i in it), extras)
            if r.id not in descartes and componentes[r.id] not in bloqueados
        ]
        excluidos = len(it) - sum(r.origem == "humano_v12" for r in aptos)
        # Calcula na base humana elegível e fixa o mesmo vetor nos quatro ajustes.
        pesos = pesos_do_fold([r.categoria for r in aptos if r.origem == "humano_v12"], 1.75, 1.50)
        teste = [titulos[i] for i in iv]
        tamanho = {}
        for nome, origens in CONDICOES.items():
            treino = [r for r in aptos if r.origem in origens]
            modelo = novo_modelo_v12(pesos).fit(
                [texto_modelo(r.titulo) for r in treino], [r.categoria for r in treino],
            )
            for i, p in zip(iv, modelo.predict(teste), strict=True):
                previsoes[nome][i] = str(p)
            tamanho[nome] = dict(Counter(r.origem for r in treino))
        treinos.append({"fold": numero, "avaliacao": len(iv), "humanos_excluidos": excluidos,
                        "pesos_classe": pesos, "treino_por_origem": tamanho})
        print(f"Fold {numero}/5 concluído.", flush=True)

    for p in previsoes.values():
        if None in p:
            raise ValueError("Previsões históricas incompletas.")
    return {
        "classes": CLASSES,
        "politica": "V12 sem prefixo, previsão direta da SVM, avaliação somente humana.",
        "acuracia_historica_v12": float(np.mean(y == referencia)),
        "descartes_por_origem": auditoria["descartes_por_origem"],
        "folds": treinos,
        "condicoes": {nome: {"origens": origens, **metricas(y, previsoes[nome])}
                      for nome, origens in CONDICOES.items()},
    }


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
        if args.saida.exists() or args.saida.is_symlink():
            raise FileExistsError(f"A saída já existe: {args.saida}")
        res = avaliar(args.entrada, args.banco, args.expansao, args.ref_com, args.ref_sem)
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        with args.saida.open("x", encoding="utf-8") as arquivo:
            json.dump(res, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
    except (OSError, ValueError) as erro:
        parser.error(str(erro))
    print(f"Ablação salva em {args.saida}.")


if __name__ == "__main__":
    main()
