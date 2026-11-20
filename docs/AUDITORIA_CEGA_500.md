# CommitX — primeira auditoria dos 500 rótulos

Queremos melhorar a qualidade do modelo atual de **66% de acurácia na validação cruzada**. Antes de testar algoritmos maiores, precisamos conferir rótulos inconsistentes.

A auditoria usa apenas exemplos da partição **treino**, selecionando casos em que a SVM discordou dos rótulos e alguns controles em que concordou. Os 39 exemplos antigos de validação e os dois de teste continuam fora.

**Importante:** o revisor não deve consultar `previsoes_*.csv`, o banco antigo ou recomendações da IA durante a revisão. O novo CSV remove o prefixo convencional do título e não contém categoria antiga nem previsão do modelo. O corpo pode conter pistas e não há como garantir cegamento absoluto. Este procedimento mede discordância entre revisões, **não** fornece acurácia independente.

## 1. Atualizar e executar testes

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/auditoria-cega-rotulos
.venv/bin/python -m unittest discover -s testes -v
```

## 2. Preparar 40 casos de auditoria

```bash
.venv/bin/python -m commitx.auditoria_rotulos preparar \
  --quantidade 40 \
  --fila resultados/auditoria/fila-cega-01.csv \
  --resumo resultados/auditoria/fila-cega-01.json

cat resultados/auditoria/fila-cega-01.json
```

## 3. Fazer segunda classificação em BANCO SEPARADO

```bash
.venv/bin/python -m commitx.rotulagem \
  --amostra resultados/auditoria/fila-cega-01.csv \
  --banco resultados/auditoria/segunda-revisao-01.sqlite3 \
  lote --tamanho 20 --limite 40 --sem-sugestoes
```

Os comandos de revisão são os mesmos do CommitX (`1=1,3;2=4,2`). A segunda rodada não deve simplesmente reproduzir as sugestões anteriores. Utilize critérios fixos, consulte descrição e diff quando disponível e **não force categorias** quando não houver evidência suficiente. A primeira revisão de 40 itens é feita em duas páginas de 20 para permitir atenção cuidadosa.

## 4. Conferir divergências

Somente após concluir 40/40:

```bash
.venv/bin/python -m commitx.auditoria_rotulos conferir \
  --fila resultados/auditoria/fila-cega-01.csv \
  --banco-original resultados/rotulagem/avaliacoes.sqlite3 \
  --banco-segunda resultados/auditoria/segunda-revisao-01.sqlite3 \
  --saida resultados/auditoria/conferencia-01

cat resultados/auditoria/conferencia-01/resumo.json
```

Se existirem divergências, revise-as manualmente para chegar a um consenso **antes** de qualquer alteração do banco original. O módulo não grava nele. **Não** avalie o classificador nos dados selecionados por seus próprios erros como se fossem uma amostra aleatória.

## 5. Próximas etapas

Após examinar a auditoria, ampliar a revisão às classes difíceis, documentar as regras de rotulagem e só então comparar a SVM atual com representações semânticas pré-treinadas nos mesmos folds por repositório. A avaliação final exige novos projetos e rótulos independentes; não utilizar o pequeno teste reservado para escolher parâmetros.
