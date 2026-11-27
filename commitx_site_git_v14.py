#!/usr/bin/env python3
"""Interface CommitX V14 com os artefatos oficiais e a inferência original da V12."""

from commitx.v12_final import SAIDA_PADRAO, analisar_modelo
from commitx_site_git_v10 import situacao
from commitx_site_git_v13 import Classificador, servir


def classificar_v12(artefatos, titulo, modo):
    resultado = analisar_modelo(artefatos, titulo, modo)
    if resultado["categoria_sugerida"] is None:
        # A V12 registra o motivo da abstenção no último aviso.
        return {**resultado, "motivo": resultado["avisos"][-1]}
    return resultado


CLASSIFICADOR_V12 = Classificador("V12", classificar_v12, situacao)


def main(argv=None):
    servir(argv, descricao=__doc__, interface="V14", classificador=CLASSIFICADOR_V12,
           artefatos_padrao=SAIDA_PADRAO, porta_padrao=8767)


if __name__ == "__main__":
    main()
