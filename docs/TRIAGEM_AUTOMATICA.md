# Triagem automática em lote — CommitX

Este processo **não precisa que você classifique um commit por vez**. Ele gera propostas provisórias em um CSV, preserva avaliações humanas anteriores e destaca mensagens que exigem atenção.

## Executar no Linux (Fish ou Bash)

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/rotulagem-automatica-lote
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.rotulagem_automatica
```

Esse comando processa a amostra inicial (284 mensagens do último relatório), gerando:
- `resultados/triagem/amostra_sugerida.csv`
- `resultados/triagem/resumo_amostra.json`

Para consultar o resumo:

```bash
.venv/bin/python -m json.tool resultados/triagem/resumo_amostra.json
```

O CSV contém **previsões provisórias** e campos separados para os rótulos humanos já confirmados. Uma categoria de prefixo (`fix:`, `docs:`, etc.) é apenas declaração do autor, não gabarito. Para prefixos não convencionais, o campo categoria_sugerida fica vazio; o modelo didático ainda aparece em coluna própria. Para clareza, só mensagens com expressão genericamente vaga e sem corpo recebem uma proposta explícita, não um rótulo de IA.

## Processar até 97 mil mensagens

```bash
.venv/bin/python -m commitx.rotulagem_automatica   --entrada resultados/preparacao-inicial/commits_preparados.csv   --saida resultados/triagem/todos_sugeridos.csv   --resumo resultados/triagem/resumo_todos.json   --lote 256
```

O programa treina o modelo didático uma única vez e faz as previsões em blocos. O banco original de 100 mil commits, o CSV preparado e o SQLite com avaliações humanas permanecem intocados.

O processo não sobrescreve saídas anteriores; escolha nomes de arquivos diferentes para novas execuções.

## Limites e próxima etapa

- A categoria prevista usa o modelo de **50 exemplos sintéticos**. Não há validação independente para os 97 mil commits.
- A clareza não é automaticamente resolvida para a maioria das mensagens; sem um modelo supervisionado validado, fica em branco. Isso é deliberado para não transformar suposições em rótulos falsos.
- A saída serve para **triagem e priorização de revisão**. Não deve ser importada como verdade para treinar sem revisão humana.
- Verifique licenças, informações pessoais e eventuais segredos antes de compartilhar os CSVs.
- O próximo passo é aproveitar as avaliações humanas para treinar, calibrar e avaliar modelos separados de categoria e clareza, mantendo um conjunto de teste independente por repositório.
