# Fila inteligente de revisão humana

Complementa a seleção estratificada existente: escolhe novos commits para **rotulagem humana**, sem transformar classificações de IA em verdade e sem alterar o SQLite de rótulos. A saída é compatível com `commitx.rotulagem lote`.

## Primeira rodada (10 commits de treino)

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/fila-inteligente-revisao
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.fila_inteligente --quantidade 10
.venv/bin/python -m commitx.rotulagem \
  --amostra resultados/amostras/fila-inteligente-01.csv \
  lote --tamanho 10 --limite 10 --sem-sugestoes
.venv/bin/python -m commitx.avaliacao_real status
```

O comando gerador produz `resultados/amostras/fila-inteligente-01.csv` e `resultados/amostras/fila-inteligente-01.json`. Os rótulos são preenchidos **somente após sua resposta** na revisão. Não confunda a coluna `hipotese_categoria` com gabarito. O limite de dois commits por repositório ajuda na diversidade.

O sistema usa TF-IDF + Regressão Logística treinados somente em commits humanos de **treino**, se houver exemplos mínimos das cinco classes. Ele prioriza incerteza e novidade do texto e reserva uma parte da seleção para exploração aleatória. Com poucos dados, utiliza diversidade por prefixo e amostragem determinística; o prefixo não vira rótulo.

Para a segunda rodada, escolha saídas novas e exclua a amostra anterior:

```bash
.venv/bin/python -m commitx.fila_inteligente \
 --quantidade 10 \
 --saida resultados/amostras/fila-inteligente-02.csv \
 --resumo resultados/amostras/fila-inteligente-02.json \
 --excluir resultados/amostras/fila-inteligente-01.csv
```

## Validação independente

Uma amostra de validação é sorteada de maneira determinística sem usar modelo, previsão nem incerteza. Ela permanece separada do treino e do teste.

```bash
.venv/bin/python -m commitx.fila_inteligente \
 --particao validacao --quantidade 10 \
 --saida resultados/amostras/validacao-cega-02.csv \
 --resumo resultados/amostras/validacao-cega-02.json
.venv/bin/python -m commitx.rotulagem \
 --amostra resultados/amostras/validacao-cega-02.csv \
 lote --tamanho 10 --limite 10 --sem-sugestoes
```

Use rótulos de validação apenas para avaliação, nunca para ajuste do TF-IDF ou seleção de hiperparâmetros. A partição `teste` é deliberadamente recusada por este comando.

## Cuidados

- Valide os rótulos manualmente, incluindo quando o prefixo parece correto; `fora_escopo` e `indeterminado` não entram nas cinco classes de treino supervisionado.
- A fila exclui IDs já revisados no SQLite e arquivos extras passados por `--excluir`; não regrava arquivos existentes.
- Probabilidades do modelo não são calibradas. Uma amostra de 10 é apenas uma rodada de coleta, não uma medida de desempenho.
- Se a base do CSV tiver repositórios aparecendo em múltiplas partições, esses registros não entram na fila.
- Para medir mudança em acurácia, use os relatórios independentes de `commitx.avaliacao_real`, sem usar a validação como fonte de treinamento.
