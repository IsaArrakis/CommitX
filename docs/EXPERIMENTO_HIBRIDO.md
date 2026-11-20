# CommitX — Experimento exploratório do Modelo B

## O que descobrimos na Fase 2?

A base experimental contém 38 commits locais de treino, mas apenas 37 pertencem às cinco categorias do classificador: docs=8, feat=8, fix=8, refactor=7, test=6. O outro é `fora_escopo`. Há **somente cinco repositórios**. Isso permite um experimento piloto, não uma avaliação conclusiva.

## Dois modelos e uma mesma comparação

- **Modelo A:** TF-IDF do texto da mensagem, removendo prefixos como `fix:`, seguido de regressão logística.
- **Modelo B:** o mesmo TF-IDF, mais contagens de linhas adicionadas, removidas, número de arquivos e extensões dos arquivos alterados. Nesta versão não é utilizado o conteúdo completo do patch.
- **Baseline:** prevê a categoria mais comum no treino daquele fold.

O experimento faz **leave-one-repository-out**: cada um dos cinco repositórios é mantido fora do treino em uma rodada. O vocabulário TF-IDF e as transformações numéricas são ajustados somente nos outros repositórios. As previsões são reunidas para calcular a acurácia e macro-F1.

Esse experimento utiliza exclusivamente a **partição de treino**. As partições de validação e teste são ignoradas; o teste reservado não é consultado.

## Como executar no Linux (Fish)

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/experimento-hibrido-diff-v1

.venv/bin/python -m unittest discover -s testes -v

.venv/bin/python -m commitx.experimento_hibrido \
  --entrada resultados/fase2/base-local-treino-01.csv \
  --saida resultados/fase2/experimento-hibrido-v1

cat resultados/fase2/experimento-hibrido-v1/resumo.json
```

Escolha outro nome em `--saida` caso a pasta já exista, porque os resultados anteriores não são sobrescritos.

## Limitações acadêmicas obrigatórias

1. Somente 37 commits e cinco repositórios: a variância pode ser alta e faltar alguma classe no treino de um fold.
2. Parte dos rótulos foi atribuída com auxílio de IA e ainda não passou por auditoria humana independente.
3. Features simples de tamanho e extensão não equivalem a compreender a semântica de um diff.
4. Um conjunto de treino limitado e selecionado ativamente não representa todos os commits.
5. Acurácia desse piloto não é comparável diretamente à acurácia de **53,8%** obtida em 39 exemplos de validação no modelo textual anterior; são amostras diferentes.
6. Não usar o conjunto reservado de teste para selecionar modelos. Qualquer decisão de ampliação deve ser posteriormente avaliada por procedimento independente e previamente fixado.
