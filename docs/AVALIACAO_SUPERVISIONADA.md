# Avaliação supervisionada do CommitX

Este módulo avalia duas tarefas independentes: categoria (fix, feat, docs, refactor, test) e clareza (vago, parcial, claro), usando exclusivamente rótulos humanos do SQLite e mensagens da base preparada. Não usa pseudo-rótulos do Ollama.

## Executar no Fish do Arch Linux

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/avaliacao-supervisionada-humana
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.avaliacao_real status
```

Se uma tarefa estiver pronta, ela poderá ser avaliada com:

```bash
.venv/bin/python -m commitx.avaliacao_real avaliar --saida resultados/avaliacao-humana-01
```

A pasta de saída deve ser nova. Para repetir sem sobrescrever, escolha outro nome em `--saida`.

## Arquivos produzidos

- `resumo.md`: visão geral, métricas, motivos de bloqueio.
- `relatorio.json`: acurácia, macro-F1, métricas por classe e matriz de confusão.
- `previsoes_categoria.csv`, `previsoes_clareza.csv`: apenas predições na validação.
- `erros_categoria.csv`, `erros_clareza.csv`: divergências da validação.
- `matriz_categoria.csv`, `matriz_clareza.csv`: linhas = real, colunas = previsto.

Arquivos CSV por tarefa só são criados quando há rótulos suficientes para avaliação.

## Proteções metodológicas

O TF-IDF e a Regressão Logística são ajustados **somente no treino humano**, com repositórios distintos entre as partições. A partição de teste permanece reservada. Modelos existentes e bancos de dados não são alterados. Quando faltarem 5 exemplos de treino ou 2 de validação por classe, ou houver repositórios sobrepostos, a tarefa fica bloqueada, sem inventar métricas.

O baseline prevê sempre a classe mais frequente do treino; serve para comparação. Macro-F1 dá igual peso às classes; acurácia mede a fração total correta. Amostras pequenas geram resultados instáveis. Os limites acima são mínimos operacionais, não garantia estatística.

**Atenção:** alguns rótulos anteriores podem ter sido atribuídos com assistência de IA. Esses dados não são automaticamente um teste humano cego e independente. Valide a procedência antes de alegar desempenho real e não use a partição de teste para ajustar o modelo depois de observar resultados.

## Correção da auditoria dos 24 erros

A auditoria de `erros_categoria.csv` identificou 24 divergências na validação: 6 exemplos `fix` previstos como `docs` e nenhum acerto entre os 5 exemplos reais de `refactor`. Alguns rótulos humanos podem ser ambíguos sem inspeção do diff. Esse diagnóstico não fornece novos rótulos, e não autoriza utilizar o conjunto de validação como treinamento.

**Proteção adicional:** o CSV de preparação pode guardar vários repositórios separados por vírgula em `repositorio` (por exemplo, `equipe/projeto,equipe/projeto`). O avaliador agora compara as origens individualmente entre treino, validação e teste. Se aparecer sobreposição, a avaliação será bloqueada; não contorne o bloqueio usando dados de validação para treinar.

Execute `status` novamente depois de atualizar a branch, antes de reavaliar. Qualquer reavaliação deve utilizar uma pasta `--saida` nova; relatórios anteriores permanecem preservados.
