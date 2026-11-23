# Plano de coleta humana e avaliação — CommitX

## Objetivo

Primeira meta: **500 commits com rótulos revisados**, com checkpoints em **150 e 250** e eventual expansão para 1.000. A quantidade não garante desempenho: é necessário medir acurácia e macro-F1 em validação independente, comparar com baseline e verificar precisão por classe. O arquivo SQLite contém avaliações registradas como humanas, mas algumas podem ter contado com auxílio de IA; registrar essa procedência é necessário antes de alegar qualidade independente.

## Primeira execução no Arch Linux / Fish

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/marcos-rotulagem-500
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.plano_rotulagem status
```

Também existe `--json` **antes** de `status`:

```bash
.venv/bin/python -m commitx.plano_rotulagem --json status
```

O módulo apenas lê a base preparada e o SQLite humano. Informa total, falta para os marcos, partições, contagem de exemplos de cada classe e bloqueios de categoria/clareza. Não altera os rótulos nem executa Ollama.

## A revisão deve ser curta e encerrável

**Não comece outro lote antes de encerrar o anterior.** No terminal `Lote>`, digite `q` para sair. Os rótulos já confirmados são preservados. Não copie exemplos de formato `1=C,K` literalmente: as letras são apenas marcadores e o programa aceita números.

Como a fila `fila-inteligente-01.csv` já foi concluída, gere uma rodada **nova** com exclusão dos IDs anteriores. Use nomes de arquivos inéditos:

```bash
.venv/bin/python -m commitx.fila_inteligente \
  --quantidade 10 \
  --saida resultados/amostras/fila-inteligente-02.csv \
  --resumo resultados/amostras/fila-inteligente-02.json \
  --excluir resultados/amostras/fila-inteligente-01.csv
.venv/bin/python -m commitx.rotulagem \
  --amostra resultados/amostras/fila-inteligente-02.csv \
  lote --tamanho 10 --limite 10 --sem-sugestoes
```

Este é **um lote opcional por rodada**, não uma obrigação diária. Exemplos ambíguos podem receber `indeterminado` ou `fora_escopo` quando couber, em vez de inventar um gabarito. Não force `vago` só para preencher mínimos.

## Validação e avaliação

- `treino`: fila ativa prioriza exemplos variados e incertos; inclui exploração aleatória
- `validacao`: amostragem cega independente; nunca é usada para ajustar o modelo
- `teste`: permanece reservado para avaliação final pré-definida
- Não selecione hiperparâmetros repetidamente pelos mesmos 39 exemplos de validação já examinados. Para comparar alternativas, use validação cruzada **apenas no treino**, preferencialmente agrupada por repositório. A validação externa fica como confirmação, não como instrumento de busca.
- Não trate amostras selecionadas por incerteza como representativas da distribuição dos quase 100 mil commits.

Em cada checkpoint, execute primeiro:

```bash
.venv/bin/python -m commitx.plano_rotulagem status
```

Para avaliação externa com novo diretório:

```bash
.venv/bin/python -m commitx.avaliacao_real \
  --saida resultados/avaliacao-humana-marco150 avaliar
```

Atenção: o exemplo acima é para o checkpoint de 150 rótulos. Use uma nova saída por avaliação. Quando a clareza estiver bloqueada por exemplos vagos insuficientes, não apresente métricas inventadas.

## Estado inicial

Na última tela do usuário havia **107 rótulos** registrados (55 exemplos de clareza no treino, 50 na validação, 2 em teste; categorias válidas 49/39/2). Esses números são fotografia do momento e serão recalculados pelo comando `status`; podem mudar após mais revisões. A acurácia de categorias com a base anterior foi 38,5% e macro-F1 de 0,297 em 39 exemplos de validação. Não é resultado garantido das próximas rodadas.

## Regras de parada

Revisar apenas quando os rótulos humanos estiverem aumentando e a revisão tiver utilidade. Parar nos checkpoints caso a distribuição por classe esteja distorcida, a procedência dos rótulos não seja confiável ou o classificador não apresente ganho consistente em validação cruzada no treino. Não gastar horas em lotes indefinidos.

## Revisão de 30 mensagens na mesma tela

A opção `--tamanho 30` agora permite que a sessão apresente todos os 30 commits de uma amostra de uma vez. `--limite 30` controla quantas confirmações são permitidas nesta sessão; não é um limite de página. Digite `dN` para detalhes da mensagem N e `q` para interromper sem excluir registros já confirmados. Com 30 mensagens, pode ser necessário rolar a tela do terminal.

**A amostra `fila-inteligente-03.csv` já foi revisada:** para mais 30 novos commits, use caminhos inéditos e exclua amostras anteriores:

```bash
.venv/bin/python -m commitx.fila_inteligente \\
  --quantidade 30 \\
  --saida resultados/amostras/fila-inteligente-04.csv \\
  --resumo resultados/amostras/fila-inteligente-04.json \\
  --excluir resultados/amostras/fila-inteligente-01.csv \\
  --excluir resultados/amostras/fila-inteligente-02.csv \\
  --excluir resultados/amostras/fila-inteligente-03.csv

.venv/bin/python -m commitx.rotulagem \\
  --amostra resultados/amostras/fila-inteligente-04.csv \\
  lote --tamanho 30 --limite 30 --sem-sugestoes
```

Registre apenas classificações conferidas; exemplos assistidos por IA não são validação cega. Não force clareza `vago` para atingir o mínimo.

## Marco 250: lote de 43 em página única

A revisão em lote agora suporta `--tamanho` de 1 a 50. Uma única página com 43 commits pode ser longa; o terminal permite rolagem. O parâmetro `--limite 43` conta **novas confirmações**, enquanto `--tamanho 43` define a quantidade mostrada simultaneamente.

Antes, confirme que `.venv/bin/python -m commitx.plano_rotulagem status` informa **207** registros. Se o total for diferente, calcule `250 - total`, e ajuste `--quantidade`, `--tamanho` e `--limite` para esse valor, sempre respeitando o máximo de 50 por página. Para total acima de 250, não crie o lote.

```bash
cd ~/CommitX-coleta
.venv/bin/python -m commitx.fila_inteligente \\
  --quantidade 43 \\
  --saida resultados/amostras/fila-inteligente-06.csv \\
  --resumo resultados/amostras/fila-inteligente-06.json \\
  --excluir resultados/amostras/fila-inteligente-01.csv \\
  --excluir resultados/amostras/fila-inteligente-02.csv \\
  --excluir resultados/amostras/fila-inteligente-03.csv \\
  --excluir resultados/amostras/fila-inteligente-04.csv \\
  --excluir resultados/amostras/fila-inteligente-05.csv

.venv/bin/python -m commitx.rotulagem \\
  --amostra resultados/amostras/fila-inteligente-06.csv \\
  lote --tamanho 43 --limite 43 --sem-sugestoes
```

Os exemplos do treino podem ser escolhidos por incerteza e diversidade, portanto não representam amostragem aleatória da população. Não force rótulos; consulte `dN` para visualizar descrições completas e confira os casos ambíguos com os diffs se existirem. Se receber auxílio da IA para atribuir rótulos, registre essa procedência para não descrevê-los como validação cega independente. Com o marco alcançado, avalie a categoria pelo protocolo existente sem tocar na partição de teste, em uma pasta de saída inédita.
