# CommitX

O CommitX é um protótipo acadêmico para classificar mensagens de commit e inspecionar alterações em repositórios Git locais. A versão oficial do site é a **V14**, com o classificador **V12 congelado**, que usa TF-IDF, sinais textuais e `LinearSVC`.

## Começar no Linux

Clone o repositório e execute o site na raiz do projeto. Se já usa a V12, reutilize o ambiente Python e a pasta de modelos existentes. Para criar um ambiente, os comandos abaixo usam Python 3.12, a versão do CI em Linux.

```bash
git clone https://github.com/IsaArrakis/CommitX.git
cd CommitX
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python commitx_site_git_v14.py --repositorio .
```

Abra o site em [127.0.0.1:8767](http://127.0.0.1:8767). Passe `--repositorio /caminho/de/outro/clone` para analisar commits de outro repositório local. Os caminhos usados pelo servidor são definidos na inicialização.

## Classificação textual V12

A V12 aprende com títulos rotulados e sugere `fix`, `feat`, `docs`, `refactor` ou `test`. A descrição opcional alimenta apenas a revisão de escrita por regras. Escolha o modo automático, com prefixo ou sem prefixo no site, ou use a CLI:

```bash
.venv/bin/python commits.py analisar-v12 'docs: Atualizar guia de instalação' --modo sem_prefixo --json
```

O site procura `manifesto.json`, `v12_com_prefixo.joblib` e `v12_sem_prefixo.joblib` em `resultados/modelo-final-v12-01/`. Use `--artefatos /caminho/dos/artefatos` para indicar outra pasta de origem confiável. Com o servidor aberto, consulte [o estado dos modelos](http://127.0.0.1:8767/api/status). O campo `pronto` indica que a versão do manifesto e os dois hashes foram verificados. Com os modelos ausentes, a previsão textual fica indisponível, e a leitura Git e a AST continuam utilizáveis. A comparação com a previsão fica inconclusiva. [Artefatos e estados da V12](docs/V12_FINAL.md#verificar-os-artefatos-e-iniciar-o-site)

## Leitura Git e análise estrutural

1. **Leitura Git.** Expanda **Analisar um commit existente do Git** e escolha um dos últimos 30 commits ou informe `HEAD` ou um SHA. O relatório apresenta mensagem, arquivos, contagens e uma prévia de até 6.000 caracteres. A comparação heurística analisa até 100.000 caracteres do diff. O leitor compara merges com o primeiro pai. Use **Importar mensagem para o formulário** para copiar a mensagem ao painel manual.
2. **Análise AST opcional.** Marque **Incluir análise estrutural de arquivos Python** antes de analisar. O leitor obtém as versões anterior e posterior de arquivos `.py` e `.pyi` a partir do Git local. O painel **Evidências estruturais** mostra mudanças observadas na árvore sintática, como funções, assinaturas e condições, com os locais disponíveis. Limites de leitura ou código inválido podem reduzir a cobertura. A análise é estática.
3. **Comparação existente.** O relatório coloca a previsão textual ao lado das heurísticas de caminhos e do diff. Os fatos da AST ficam em uma seção separada. Compatibilidade indica concordância entre os sinais disponíveis. O comportamento em execução e a intenção pedem revisão humana.

Para consultar metadados e prévia no terminal:

```bash
.venv/bin/python -m commitx.leitor_diff --repositorio . --commit HEAD --json
```

## Resultados e ablação

Os resultados históricos de validação cruzada são exploratórios e descrevem o conjunto de desenvolvimento. A avaliação externa cega tem protocolo e ferramentas de preparação. A amostra revisada e as métricas externas da V12 seguem pendentes. [Resultados históricos e limitações](docs/V12_FINAL.md#resultados-históricos-e-avaliação-externa) · [Protocolo externo](docs/AVALIACAO_EXTERNA_V12.md) · [Integração V14 e resultados da ablação](docs/V14_INTEGRACAO.md)

## Testes

```bash
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m unittest discover -s tests -v
```

O GitHub Actions roda as duas descobertas separadamente em pushes e pull requests. As suítes usam fixtures, modelos de teste pequenos e repositórios Git temporários. Uma falha ou erro reportado pelo `unittest` reprova a suíte. Casos declarados como `skipped` são listados pelo próprio `unittest`, com o motivo. A inferência com os modelos oficiais e a avaliação externa exigem artefatos e dados locais.

## Demonstrações e experimentos anteriores

Os comandos históricos abaixo continuam disponíveis em `commits.py`. `analisar` e `avaliar` exercitam a demonstração acadêmica. `analisar-v12` utiliza a configuração congelada da V12.

### Avaliar os modelos da demonstração

```bash
.venv/bin/python commits.py avaliar
.venv/bin/python commits.py avaliar --dados dados/commits_revisados.csv --folds 5 --saida resultados_reais
```

A demonstração compara estas três alternativas nas mesmas divisões dos dados:

| Alternativa | Características e classificador |
| --- | --- |
| `palavras` | TF-IDF de palavras isoladas e pares de palavras + Regressão Logística |
| `misto` | As características anteriores + fragmentos de 3 a 5 caracteres dentro das palavras + Regressão Logística |
| `maioria` | Prevê sempre a categoria mais frequente do treino |

O modelo `palavras` preserva os parâmetros da versão inicial. Além de caracteres, o `misto` usa frequência sublinear e balanceamento de classes. A comparação é entre essas configurações completas; não isola o efeito de adicionar caracteres. Os parâmetros foram definidos antes de observar esta avaliação.

O padrão são cinco divisões de validação cruzada. Com um grupo distinto por mensagem, usa-se `StratifiedKFold`; com grupos repetidos, usa-se `StratifiedGroupKFold`, mantendo cada grupo inteiro de um lado da divisão. Cada classe precisa de grupos suficientes; a avaliação recusa divisões sem alguma classe.

O TF-IDF é ajustado somente no treino de cada divisão. Cada mensagem recebe uma previsão *out of fold* (OOF): produzida por um modelo que não a utilizou no treino. A acurácia e o macro-F1 OOF são calculados sobre essas previsões reunidas. A macro-F1 dá o mesmo peso às cinco classes; o desvio entre divisões descreve variação, não um intervalo de confiança.

Por padrão, os arquivos são escritos em `resultados/`:

| Arquivo | Conteúdo |
| --- | --- |
| `resumo.md` | Comparação das métricas e limites do experimento |
| `relatorio.json` | Métricas por classe, divisões, identificadores e configuração |
| `previsoes.csv` | Todas as mensagens, rótulos e previsões dos três modelos |
| `erros.csv` | Mensagens que o modelo misto classificou incorretamente |
| `matriz_confusao.csv` | Matriz do modelo misto: linhas reais, colunas previstas |

Escolha outra pasta em `--saida` para preservar uma execução anterior. Comece a leitura por `resumo.md` e depois examine `erros.csv`.

Não compare diretamente o antigo resultado de `0,40`, obtido com um teste de dez mensagens, com a nova validação cruzada sobre cinquenta mensagens: o protocolo mudou. A comparação válida entre `palavras`, `misto` e `maioria` é a feita nas mesmas divisões desta execução. Adicionar caracteres não garante melhorar o resultado.

Os resultados verificados desta base estão em [Resultados da demonstração](docs/RESULTADOS_DEMONSTRACAO.md).

### Dados e coleta de commits reais

`dados/commits_exemplo.csv` mantém os 50 exemplos sintéticos da base inicial, dez por categoria, criados com assistência de IA e identificados como `sintetico_didatico`. Eles servem para aprender e demonstrar o fluxo. Não são commits coletados de projetos reais.

O CSV de treinamento usa estas colunas:

| Campo | Significado |
| --- | --- |
| `id` | Identificador único do exemplo |
| `titulo` | Primeira linha da mensagem |
| `descricao` | Corpo da mensagem, que pode estar vazio |
| `categoria` | Rótulo revisado: `fix`, `feat`, `docs`, `refactor` ou `test` |
| `grupo` | Identificador compartilhado por exemplos relacionados ou paráfrases |
| `origem` | Procedência explícita, como a identificação do repositório |

O carregamento valida campos, identificadores, rótulos e duplicatas. Mensagens relacionadas devem compartilhar `grupo`; não distribua paráfrases do mesmo exemplo entre treino e teste. O tipo e o escopo do prefixo inicial são removidos da entrada do classificador para reduzir o atalho de copiar o rótulo declarado.

Para exportar um histórico Git local que você tenha disponível:

```bash
.venv/bin/python commits.py coletar /caminho/do/repositorio --limite 200 --saida dados/commits_para_rotular.csv
```

Substitua o caminho por um repositório real. O coletor lê o histórico local sem commits de merge, com limite padrão de 100 e máximo de 1.000 mensagens. Não altera o repositório e recusa sobrescrever um arquivo de saída existente.

A exportação deixa `categoria` vazia e acrescenta `tipo_declarado` como informação auxiliar. Ela não transforma automaticamente o prefixo em rótulo nem treina um modelo. Antes de usar o arquivo:

1. Leia cada mensagem e atribua a categoria pela intenção descrita.
2. Revise mensagens vazias, vagas, duplicadas e com várias intenções; agrupe exemplos relacionados. Mensagens vazias são preservadas na coleta para revisão, mas não são aceitas no treinamento.
3. Para tipos fora das cinco classes, exclua-os justificadamente do recorte ou defina um tratamento metodológico antes de ampliar o modelo. Não force uma categoria apenas para completar a tabela.
4. Salve uma cópia revisada, por exemplo `dados/commits_revisados.csv`, e use `--dados` para treiná-la ou avaliá-la.

O histórico de um CommitX recém-criado tende a ser pequeno e pouco variado. Escolha um repositório com histórico suficiente para seu experimento, registre a origem e não apresente exemplos inventados como dados reais.

Veja também o [guia de estudo e entrega](docs/GUIA_DO_TRABALHO.md).
