# Aprendizado ativo e treinamento supervisionado real — CommitX

## O que foi implementado

- Seleção determinística de exemplos difíceis e comuns, misturando fontes Hugging Face e Git, com teto por repositório; a categoria é deixada vazia e exige **revisão humana**.
- Treinamento de dois classificadores **separados**, um de tipo de commit e outro de clareza, usando **somente avaliações humanas** já salvas no SQLite.
- Diagnóstico de rótulos necessários por classe e validação separada por repositório. Os testes reservados permanecem intocados; não se usa o modelo anterior para criar gabaritos.

**Atenção:** a seleção atual é *heurística de desacordo e diversidade*, e não uma medida calibrada de incerteza. O modelo didático existente tem apenas 50 exemplos sintéticos. Não é correto afirmar que os 97 mil commits já estão rotulados.

## 1. Atualizar a branch

No terminal Fish:

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/aprendizado-ativo-treino-real
.venv/bin/python -m unittest discover -s testes -v
```

O SQLite com os 100 mil commits e os seis rótulos humanos permanece em `resultados/` e não é modificado pelos novos comandos de seleção e treinamento.

## 2. Selecionar uma nova rodada de 300 commits

```bash
.venv/bin/python -m commitx.selecao_ativa   --entrada resultados/triagem/todos_sugeridos.csv   --quantidade 300   --por-repo 35
```

Arquivos gerados:

- `resultados/amostras/rodada1.csv` — ID, título, corpo, repositório, partição e candidatos, com `categoria` **vazia**.
- `resultados/amostras/rodada1.json` — distribuição por prioridade, classe e fonte.

O comando não seleciona registros que já estejam no banco de avaliações e usa somente a partição `treino` por padrão. O conjunto de teste não é usado para selecionar exemplos de treinamento.

## 3. Revisar algumas mensagens

```bash
.venv/bin/python -m commitx.rotulagem   --amostra resultados/amostras/rodada1.csv iniciar --limite 10
```

As avaliações são salvas no mesmo banco de rótulos humanos, evitando reavaliar commits antigos. **Enter** confirma apenas propostas existentes; números permitem corrigir as sugestões. Para maior rigor, pode usar `--sem-sugestoes`.

A partição de validação merece uma rodada **separada** de rotulagem sem sugestões. Se desejar prepará-la, use novos caminhos de saída e `--particao validacao`, mas não ajuste o modelo com as respostas da validação.

## 4. Consultar a prontidão do treinamento

```bash
.venv/bin/python -m commitx.treino_real status
```

O status identifica quantos **rótulos humanos** foram encontrados nas cinco classes de categoria e nas três classes de clareza, por partição, e quantos ainda faltam.

Limiares técnicos provisórios:
- Treino: pelo menos cinco exemplos por classe.
- Validação: pelo menos dois exemplos por classe, em repositórios separados dos de treino.

Esses mínimos apenas permitem que um experimento inicial rode; **não garantem desempenho, calibração ou representatividade**.

## 5. Treinar quando houver dados suficientes

```bash
.venv/bin/python -m commitx.treino_real treinar
```

Resultados, quando os mínimos forem satisfeitos:
- `resultados/modelos-reais/categoria.joblib`
- `resultados/modelos-reais/clareza.joblib`
- `resultados/modelos-reais/relatorio_treinamento.json`

O sistema treina as tarefas de modo independente. Se faltar rótulo, gera um relatório explicando a ausência e **não cria o modelo** correspondente. Se houver validação suficiente, o relatório inclui acurácia, macro-F1 e matriz de confusão. O conjunto de teste fica reservado para uma avaliação final posterior.

Para repetir o treinamento, escolha uma pasta nova com `--saida`; o programa não sobrescreve artefatos anteriores.

## Limites e segurança dos dados

- Seis rótulos humanos ainda são insuficientes para treinar modelos válidos.
- Amostras compostas principalmente de divergências têm viés de seleção. Use uma parte de casos aleatórios, comuns e difíceis, e avalie em uma amostra independente.
- A partição atual agrupa pelo identificador do repositório recebido; forks e aliases ainda precisam de auditoria antes de declarar independência definitiva.
- Mensagens claras não exigem necessariamente corpo.
- Classificações de texto não confirmam se a mensagem corresponde ao diff.
- É necessário revisar licenças, dados pessoais e eventuais segredos antes de distribuir datasets ou modelos.
- Este fluxo é uma **primeira implementação** de treinamento experimental, não um classificador de produção.
