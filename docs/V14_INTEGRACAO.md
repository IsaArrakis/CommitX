# CommitX V14

A interface V14 usa o classificador oficial V12 (`v12_extra_030`) na
classificação manual, na comparação dos modos e na análise Git. O site
identifica as duas versões e usa o manifesto e os dois modelos V12 existentes.
Os formulários começam vazios, a importação do commit é opcional e o histórico
identifica a origem da análise. A prévia conserva 6.000 caracteres, a análise
do diff usa até 100.000 e a análise estrutural AST continua disponível.

## Iniciar

Use o comando na raiz do checkout V14 com o mesmo Python que já executa a V12.

```bash
"$HOME/CommitX-coleta/.venv/bin/python" commitx_site_git_v14.py \
  --repositorio "$HOME/CommitX-coleta" \
  --artefatos "$HOME/CommitX-coleta/resultados/modelo-final-v12-01" \
  --porta 8767
```

Abra [127.0.0.1:8767](http://127.0.0.1:8767). O site usa os artefatos
existentes diretamente. A ablação é um comando separado.

## Ablação sem prefixo

Usamos os 397 rótulos humanos nas mesmas cinco divisões históricas, verificadas
pelas referências V12. A previsão direta da SVM, sem abstenção, é a mesma nas
quatro condições. Usamos `novo_modelo_v12` com o mesmo pré-processamento e
hiperparâmetros. Os pesos balanceados originais foram calculados na base
humana elegível de cada fold e mantidos fixos nas quatro condições, sem pesos
por origem. Aplicamos as mesmas exclusões da V13 em A–D. Quatro exemplos
humanos com vínculos a partições reservadas saíram do treino quando presentes
e mantiveram seu lugar na avaliação. A referência histórica, que inclui esses
exemplos no treino de seus respectivos folds, é 71,28%.

| Condição cumulativa | Treino por fold | Acurácia | Macro-F1 | F1 fix | F1 feat | F1 docs | F1 refactor | F1 test |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A · Humanos | 313–316 | 71,03% | 0,7185 | 0,6692 | 0,7230 | 0,7647 | 0,6355 | 0,8000 |
| B · A + pseudo-rótulos em inglês | 801–807 | 70,28% | 0,7105 | 0,6390 | 0,7602 | 0,7879 | 0,5738 | 0,7917 |
| C · B + traduções | 1.114–1.123 | 71,28% | 0,7227 | 0,6444 | 0,7713 | 0,8125 | 0,5854 | 0,8000 |
| D · C + sintéticos | 1.183–1.192 | 71,28% | 0,7222 | 0,6555 | 0,7623 | 0,8125 | 0,5806 | 0,8000 |

B perdeu três acertos líquidos frente a A. C recuperou quatro frente a B.
D empatou com C em acurácia e teve macro-F1 ligeiramente menor. A expansão
completa ainda reduziu o F1 de `refactor` e melhorou o de `docs` frente a A.
Com o pipeline V12, a expansão completa não reproduziu a queda da V13 sem
abstenção (67,25%). O resultado aponta para o conjunto de mudanças no pipeline
V13 ou sua interação com os dados. Este desenho não separa o efeito dos
atributos, da regularização e dos pesos da V13.

Para reproduzir com os arquivos nos caminhos padrão, execute
`python -m commitx.ablacao_v14`. O JSON `resultados/ablacao-v14-01.json`
registra precisão, recall, matriz de confusão, pesos e totais por fold. A
ablação não grava modelos.

## Verificação

Passaram 329 testes automatizados e o fluxo no Chromium, incluindo
classificação, comparação, Git, importação e AST. Na integração, foram
usados artefatos de teste compatíveis com o formato oficial da V12 e a
resposta foi comparada com a inferência original.
