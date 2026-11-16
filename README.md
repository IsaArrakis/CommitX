# CommitX

Protótipo acadêmico em Python para classificar a intenção de mensagens de commit e oferecer recomendações de escrita. Esta é a versão inicial, em um único arquivo, para estudar o fluxo de aprendizado supervisionado.

## O que o projeto faz

- Classifica título e descrição em `fix`, `feat`, `docs`, `refactor` ou `test`.
- Usa **TF-IDF + Regressão Logística** para a classificação.
- Mostra o tipo declarado no cabeçalho separadamente da categoria prevista.
- Oferece recomendações de escrita por **regras**, sem uma nota de clareza validada.
- Gera relatório com métricas, matriz de confusão e previsões do teste.

## Instalação e execução

Requer Python 3.10 ou superior. No Linux, dentro da pasta que contém `commits.py`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python commits.py avaliar
.venv/bin/python commits.py analisar "fix(admin): bug no painel"
```

Os comandos funcionam em bash e fish sem precisar ativar o ambiente virtual. Para incluir a descrição:

```bash
.venv/bin/python commits.py analisar "fix(admin): corrigir paginação de usuários" --descricao "A segunda página repetia os registros da primeira. Corrige o deslocamento da consulta."
```

O código Python deve ser salvo em `commits.py`; os blocos acima são os comandos executados no terminal. O caminho `/workspace` usado no ambiente Cloud da conversa não corresponde a uma pasta no seu computador.

### Obter o projeto do GitHub

O repositório é privado. A conta usada para baixar ou clonar precisa ter acesso. Com o Git autenticado, escolha uma pasta onde guardar a cópia e execute:

```bash
git clone https://github.com/IsaArrakis/CommitX.git
cd CommitX
```

Também é possível usar **Code → Download ZIP** no GitHub e extrair os arquivos. A pasta local antiga `commit-claro` continua separada desta cópia; clonar o repositório não a altera.

## Dados e rótulos

A constante `DADOS`, em `commits.py`, contém **50 exemplos sintéticos em português**, dez por categoria. Os exemplos e os rótulos foram elaborados com assistência de IA, para demonstração. Não são commits coletados de repositórios e precisam de revisão humana.

Cada linha usa o formato `categoria|titulo|descricao`; a descrição pode estar vazia. As categorias representam a intenção descrita na mensagem:

| Categoria | Definição |
| --- | --- |
| `fix` | Corrigir um comportamento defeituoso existente |
| `feat` | Adicionar uma capacidade nova |
| `docs` | Alterar documentação |
| `refactor` | Reorganizar código preservando o comportamento |
| `test` | Adicionar ou alterar testes |

O prefixo convencional e seu escopo são removidos do título antes de alimentar o modelo. Assim, o classificador precisa usar o restante da mensagem em vez de apenas copiar o rótulo inicial.

## Avaliação

`avaliar` usa uma divisão estratificada com semente 42: **40 exemplos para treino e 10 para teste**, dois por classe no teste. O `Pipeline` aprende o vocabulário e os pesos do TF-IDF somente com o treino.

O comando salva `resultados/relatorio.json` com:

- Precisão, recall, F1 e suporte por classe.
- Macro-F1 do modelo e de uma referência que sempre prevê a classe mais comum do treino.
- Matriz de confusão: linhas = categoria de referência; colunas = previsão; ordem em `ordem_matriz`.
- Textos e previsões do teste, índices das linhas, semente e versão do scikit-learn.

Nesta base, uma execução com Python 3.12.14 e scikit-learn 1.8.0 produziu acurácia de **0,40**, macro-F1 de **0,413** e macro-F1 da referência de **0,067**. Esses números documentam uma execução didática; não demonstram desempenho em commits reais. Use os números gerados no seu ambiente no relatório do trabalho.

`analisar` treina com os 50 exemplos para demonstrar uma nova entrada. Um acerto nesse comando não altera a avaliação de teste e não constitui uma validação independente.

## Limites da versão inicial

- A base é pequena, artificial e pouco diversa. Não há promessa de precisão.
- O programa analisa a mensagem, não o diff. Não verifica se o código mudou como descrito ou se um bug foi resolvido.
- A categoria declarada é reconhecida por um padrão simples de cabeçalho, sem validar toda a especificação Conventional Commits.
- As recomendações de escrita são heurísticas: palavras como “bug” e ausência de corpo apenas sugerem revisão. Uma mensagem curta pode ser suficiente; “arrumar” não é uma palavra proibida.
- O classificador conhece cinco categorias. Tipos como `chore`, `ci`, `build` e mensagens com várias intenções exigem revisão. Uma entrada fora do escopo ainda pode receber uma das cinco classes.
- A única abstenção automática ocorre quando o texto não contém nenhum termo conhecido pelo vocabulário.

## Próximos passos para o trabalho

1. Revisar os rótulos e entender as previsões erradas antes de alterar o modelo.
2. Coletar commits reais e guardar origem, identificador, mensagem completa e categoria revisada. Não copiar o prefixo automaticamente como resposta correta.
3. Separar exemplos sintéticos e reais nos resultados. Remover duplicatas e manter paráfrases ou mensagens relacionadas no mesmo conjunto; com uma base ampliada, considerar uma divisão por repositório ou grupos. A divisão atual é por linha, sem agrupamento.
4. Reservar um teste independente antes de ajustar parâmetros. Não mudar a semente repetidamente para escolher a melhor métrica.
5. Avaliar as recomendações de escrita com revisão humana. Para aprender clareza com ML, será necessário outro conjunto de rótulos e outro experimento.

A `.gitignore` exclui `.venv/`, caches e `resultados/`. Os relatórios podem ser gerados novamente; o ambiente virtual deve ser instalado em cada computador.

## Referências

- [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/)
- [TF-IDF no scikit-learn](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction)
- [Regressão Logística no scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)
