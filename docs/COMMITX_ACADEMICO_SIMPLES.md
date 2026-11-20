# CommitX: versao academica simples

Esta etapa entrega um fluxo executavel sem criar rotulos humanos falsos:

- Treina uma SVM TF-IDF com os rotulos ja existentes da particao treino.
- Opcionalmente usa pseudo-rotulos com margem elevada e limite por classe.
- Classifica CSV grande em blocos de 500 linhas sem carregar 97 mil linhas na memoria.
- Gera modelo.joblib, previsoes.csv e resumo.json na pasta escolhida.
- Nao escreve nos bancos originais, nem usa validacao/teste para treinar.

## 1. Descobrir o CSV grande

```fish
cd ~/CommitX-coleta
find . -path './.venv' -prune -o -iname '*.csv' -print | head -80
```

## 2. Executar a versao de referencia (sem pseudo-rotulos)

Substitua /CAMINHO/97mil.csv pelo CSV real. O arquivo precisa conter coluna
`titulo`, `title`, `mensagem`, `message` ou `commit_message`.

```fish
.venv/bin/python -m commitx.academico executar \
  --entrada /CAMINHO/97mil.csv \
  --saida resultados/academico-simples-01
```

## 3. Experimento de ampliacao opcional

O numero de pseudo-rotulos nao e 97 mil: serao selecionados somente aqueles
que passarem os filtros. Isso NAO comprova que estejam corretos.

```fish
.venv/bin/python -m commitx.academico executar \
  --entrada /CAMINHO/97mil.csv \
  --saida resultados/academico-pseudo-01 \
  --pseudo-max-por-classe 2000 \
  --margem 1.5
```

## 4. Usar modelo

```fish
.venv/bin/python -m commitx.academico analisar \
  --modelo resultados/academico-simples-01 \
  --titulo 'Fix unexpected login error'
```

## Interpretar

O script informa QUANTOS commits receberam previsoes, e nao acuracia.
Comparar basico e pseudo-rotulado exige avaliacao independente em repositorios
nao vistos. Nunca usar validacao conhecida para escolher parametros depois de
inspecionar resultados. O conjunto de 500 rotulos inclui revisoes assistidas
por IA, e deve ser descrito assim no relatorio academico. As 5 classes de treino
sao fix, feat, docs, refactor e test: outras categorias podem receber
previsao errada. O CSV de previsoes nao e um conjunto rotulado confiavel.

Arquivos joblib devem ser carregados somente se forem produzidos localmente
em um ambiente confiavel.
