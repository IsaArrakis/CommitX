# CommitX

Protótipo acadêmico em Python que classifica a intenção de mensagens de commit e recomenda melhorias de escrita. Recebe título e descrição e sugere uma de cinco categorias: `fix`, `feat`, `docs`, `refactor` ou `test`.

A classificação usa aprendizado supervisionado. A revisão de escrita usa regras explicáveis e não atribui nota de clareza. O programa não lê o diff para confirmar o que mudou no código.

## Começar no Linux

Você precisa de Python 3.10 ou superior, Git e acesso autorizado ao repositório privado. Autentique sua conta do GitHub no cliente Git que utiliza. Não coloque senhas ou tokens no código ou na URL do repositório.

No terminal, entre na pasta em que deseja guardar o projeto e clone em uma pasta nova:

```bash
git clone https://github.com/IsaArrakis/CommitX.git
cd CommitX
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python commits.py
```

Os comandos usam o Python do ambiente virtual diretamente e funcionam em Bash e Fish, sem ativação. Se o Git informar que o repositório não existe, confira a conta autenticada e seu acesso ao repositório privado. Se a pasta `CommitX` já existir, escolha outra pasta de destino para o clone; não sobrescreva seus arquivos.

Outra opção é abrir o repositório no GitHub, escolher **Code → Download ZIP**, extrair e abrir o terminal dentro da pasta que contém `commits.py`. Nesse caso, comece pelo comando `python3 -m venv .venv`. Para acompanhar novas versões com `git pull --ff-only`, use um clone autenticado; um ZIP não contém o histórico Git.

Uma pasta antiga chamada `commit-claro` não se torna um clone do CommitX automaticamente. Use a cópia clonada para executar estes comandos e acompanhar as alterações do repositório.

Sem argumentos, o programa abre o modo interativo. Digite um título e, opcionalmente, uma descrição de uma linha. Ele treina uma vez ao iniciar e reutiliza o modelo durante a sessão. Um título vazio ou `Ctrl+C` encerra.

## Analisar mensagens

```bash
.venv/bin/python commits.py analisar "fix(admin): bug no painel"
.venv/bin/python commits.py analisar "Corrigir paginação de usuários" --descricao "A segunda página repetia os registros da primeira."
.venv/bin/python commits.py analisar "docs: corrigir link de instalação no README" --json
.venv/bin/python commits.py interativo --modelo palavras
```

O modo `--json` imprime a mesma análise em formato estruturado. O modelo padrão é `misto`; `--modelo palavras` seleciona a alternativa baseada somente em palavras. Para usar outra base já rotulada:

```bash
.venv/bin/python commits.py analisar "Adicionar filtro por status" --dados dados/commits_revisados.csv --modelo misto
.venv/bin/python commits.py interativo --dados dados/commits_revisados.csv
```

A saída separa o tipo declarado no cabeçalho, a categoria sugerida e os alertas de escrita. Uma divergência entre tipo e previsão pede revisão humana; ela não prova que o autor errou. Tipos explicitamente declarados fora das cinco classes e textos sem características conhecidas não recebem sugestão automática. Isso não detecta todos os casos fora do escopo.

Os modelos para preencher contêm campos entre colchetes. O autor precisa completá-los com informações reais; o programa não inventa o bug ou a implementação. “Arrumar” não é uma palavra proibida. O problema de “arrumar bug no painel” é não identificar qual comportamento mudou.

## Avaliar e gerar relatórios

```bash
.venv/bin/python commits.py avaliar
.venv/bin/python commits.py avaliar --dados dados/commits_revisados.csv --folds 5 --saida resultados_reais
```

A avaliação compara três alternativas nas mesmas divisões dos dados:

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

## Dados e coleta de commits reais

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

## Organização e limites

`commits.py` é a entrada do terminal. O pacote `commitx/` separa o código em quatro módulos: `dados.py` para leitura e coleta, `escrita.py` para regras, `modelo.py` para aprendizado e avaliação, e `relatorios.py` para exportação. Para executar as verificações automatizadas:

```bash
.venv/bin/python -m unittest discover -s testes -v
```

A avaliação é exploratória e não possui teste externo independente. Resultados sintéticos não demonstram desempenho em repositórios reais. Ajustes escolhidos após observar os erros precisam de avaliação posterior em dados independentes. As métricas de classificação não avaliam clareza.

As regras de escrita são simples, em português, e não atribuem pontuação. Ausência de alertas não comprova clareza. O cabeçalho reconhecido não valida toda a especificação de Conventional Commits; uma mensagem curta pode ser suficiente, e o corpo é opcional quando o título explica a alteração.

Veja [o guia de estudo e entrega](docs/GUIA_DO_TRABALHO.md). Referências: [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/), [TF-IDF](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction) e [Regressão Logística](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression).
