# CommitX V13 experimental

A avaliação cruzada reproduziu as 397 previsões históricas da V12 em cada modo.
A V12 continua sendo a versão recomendada. A configuração experimental de
palavras, caracteres e contexto foi a melhor V13 sem prefixo, mas ficou abaixo
da referência mesmo com a abstenção desativada.

## Problemas e correções

- O site preenchia uma mensagem de exemplo e HEAD na abertura. Agora título,
  descrição, referência, resultado e histórico começam vazios. O modo
  automático fica selecionado e os cinco exemplos são acionados por botão.
- A análise Git modificava o formulário e o resultado manual. A mensagem só
  entra no formulário pelo botão de importação. A tela mostra o repositório,
  explica HEAD e permite escolher um dos últimos 30 commits alcançáveis pelo
  HEAD ou informar uma referência. O histórico da sessão identifica a origem
  manual ou Git. Tipos fora do escopo, como `chore`, recebem uma mensagem explícita.
- O parser do diff recebia a mesma prévia de 6.000 caracteres da interface. A
  V13 analisa até 100.000 caracteres do patch e mantém os 6.000 para exibição.
  A leitura usa a captura limitada e os timeouts Git existentes. Quando falta
  cobertura, a comparação fica inconclusiva. A análise por arquivo exigiria
  repartir os limites de tempo e leitura entre os arquivos. A V13 preserva a
  análise AST opcional e sua cobertura por arquivo.
- Os dois títulos de AST motivaram uma verificação do vocabulário. Na V12
  retreinada, cada título reconheceu um de seus 11 termos TF-IDF distintos. A
  V12 reconheceu `api` no primeiro e `python` no segundo. Ambos receberam `fix`. A V13
  normaliza caixa e acentos pelo mesmo caminho no treino e no site. O primeiro
  exemplo passou a `feat`. O segundo ainda recebe `fix`. Ambos são exemplos de
  diagnóstico externos às métricas desta validação cruzada.

## Dados

A expansão tem 909 IDs únicos e 578 grupos declarados. As 331 traduções
coincidem com a mensagem de origem em ID de vínculo, grupo, repositório e
categoria. A comparação de títulos normalizados sem prefixo encontrou zero
duplicatas ou conflitos na união dos 1.306 candidatos.

A auditoria de grupos, repositórios e títulos excluiu nove candidatos do
treino V13 por relação com validação ou teste reservados. Entre eles estão
quatro registros humanos da V12, que seguiram nas mesmas divisões de avaliação.
A V12 foi reproduzida com as exclusões do seu protocolo histórico. A V13
excluiu de cada treino os componentes ligados aos registros avaliados no fold.
O SQLite e os arquivos de entrada foram confirmados pelos hashes do ZIP.

| Origem | Disponíveis | Usados | fix | feat | docs | refactor | test |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Humanos V12 | 397 | 393 | 130 | 104 | 30 | 54 | 75 |
| Reais em inglês, rótulo de IA | 509 | 505 | 128 | 164 | 36 | 59 | 118 |
| Traduções em português | 331 | 330 | 79 | 80 | 34 | 57 | 80 |
| Sintéticos em português | 69 | 69 | 0 | 0 | 46 | 23 | 0 |
| Total | 1.306 | 1.297 | 337 | 348 | 146 | 193 | 273 |

| Fold | Treino V12 | Treino V13 | Avaliação humana |
| --- | ---: | ---: | ---: |
| 1 | 317 | 1186 | 80 |
| 2 | 317 | 1183 | 80 |
| 3 | 317 | 1191 | 80 |
| 4 | 318 | 1189 | 79 |
| 5 | 319 | 1192 | 78 |

## Avaliação cruzada exploratória

A mesma divisão `StratifiedGroupKFold` de cinco folds, com 397 rótulos
humanos e 310 grupos históricos, foi usada nas duas versões. As configurações
V13 usaram `LinearSVC`, TF-IDF, pesos por origem de 1,00, 0,55, 0,35 e 0,25 na
ordem da tabela, e balanceamento da massa de treino por classe. A seleção foi
pela acurácia sem prefixo nos próprios folds, seguida pelo macro-F1 em caso de
empate. Esse procedimento tem viés de seleção. Os conjuntos independentes
foram preservados e não forneceram gabaritos para este experimento.

A acurácia sobre os 397 títulos conta abstenção como erro. A V12 da tabela usa
as previsões históricas sem política de abstenção. A abstenção V13 aplica
escopo, ausência de características ou diferença entre as duas maiores
pontuações abaixo de 0,15. A margem SVM mede a separação de pontuações.
Seu valor não representa uma probabilidade.

| Configuração | Prefixo | Acurácia | Macro-F1 | Cobertura | Abstenções | Acurácia nas sugestões | Acurácia sem abstenção |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V12 | Com | 84,63% | 0,8468 | 100,00% | 0 | 84,63% | 84,63% |
| V12 | Sem | 71,28% | 0,7205 | 100,00% | 0 | 71,28% | 71,28% |
| V13 palavras | Com | 75,82% | 0,7866 | 87,15% | 51 | 86,99% | 82,37% |
| V13 palavras | Sem | 58,19% | 0,6179 | 77,33% | 90 | 75,24% | 66,50% |
| V13 palavras e caracteres | Com | 76,32% | 0,7937 | 88,41% | 46 | 86,32% | 82,12% |
| V13 palavras e caracteres | Sem | 58,94% | 0,6249 | 78,34% | 86 | 75,24% | 66,75% |
| V13 palavras, caracteres e contexto | Com | 75,82% | 0,7832 | 88,16% | 47 | 86,00% | 82,12% |
| V13 palavras, caracteres e contexto | Sem | 60,20% | 0,6332 | 79,85% | 80 | 75,39% | 67,25% |

| Categoria | V12 com, precisão e recall | V13 com, precisão e recall | V12 sem, precisão e recall | V13 sem, precisão e recall |
| --- | ---: | ---: | ---: | ---: |
| fix | 88,33% / 80,92% | 92,52% / 75,57% | 66,67% / 68,70% | 76,53% / 57,25% |
| feat | 80,18% / 85,58% | 80,77% / 80,77% | 70,00% / 74,04% | 73,47% / 69,23% |
| docs | 84,21% / 96,97% | 95,45% / 63,64% | 74,29% / 78,79% | 80,00% / 36,36% |
| refactor | 77,55% / 70,37% | 74,36% / 53,70% | 65,38% / 62,96% | 57,50% / 42,59% |
| test | 89,87% / 94,67% | 87,18% / 90,67% | 86,15% / 74,67% | 86,36% / 76,00% |

### Matrizes de confusão

As linhas são os rótulos humanos. As colunas são as previsões.

**V12 · com prefixo**

| Real | fix | feat | docs | refactor | test | Abstenção |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fix | 106 | 12 | 3 | 6 | 4 | 0 |
| feat | 7 | 89 | 1 | 5 | 2 | 0 |
| docs | 0 | 0 | 32 | 0 | 1 | 0 |
| refactor | 6 | 8 | 1 | 38 | 1 | 0 |
| test | 1 | 2 | 1 | 0 | 71 | 0 |

**V13 palavras, caracteres e contexto · com prefixo**

| Real | fix | feat | docs | refactor | test | Abstenção |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fix | 99 | 7 | 1 | 6 | 3 | 15 |
| feat | 3 | 84 | 0 | 3 | 2 | 12 |
| docs | 2 | 4 | 21 | 1 | 0 | 5 |
| refactor | 3 | 6 | 0 | 29 | 5 | 11 |
| test | 0 | 3 | 0 | 0 | 68 | 4 |

**V12 · sem prefixo**

| Real | fix | feat | docs | refactor | test | Abstenção |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fix | 90 | 22 | 4 | 11 | 4 | 0 |
| feat | 22 | 77 | 2 | 3 | 0 | 0 |
| docs | 4 | 0 | 26 | 2 | 1 | 0 |
| refactor | 11 | 4 | 1 | 34 | 4 | 0 |
| test | 8 | 7 | 2 | 2 | 56 | 0 |

**V13 palavras, caracteres e contexto · sem prefixo**

| Real | fix | feat | docs | refactor | test | Abstenção |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fix | 75 | 12 | 1 | 11 | 2 | 30 |
| feat | 10 | 72 | 1 | 2 | 0 | 19 |
| docs | 5 | 2 | 12 | 4 | 0 | 10 |
| refactor | 4 | 6 | 0 | 23 | 7 | 14 |
| test | 4 | 6 | 1 | 0 | 57 | 7 |

### Idiomas

O conjunto humano preparado não traz idioma da mensagem. A heurística por
marcadores funcionais identificou um recorte de 70 títulos provavelmente em
inglês, com 67 grupos. Os 327 títulos sem evidência suficiente ficaram
indeterminados. Nenhum título atingiu o critério heurístico para o corte em português. A estimativa favorece textos com mais contexto e não descreve todos
os títulos em inglês.

| Modelo | Prefixo | Acurácia no recorte inglês | Macro-F1 | Cobertura |
| --- | --- | ---: | ---: | ---: |
| V12 | Com | 87,14% | 0,8470 | 100,00% |
| V13 palavras, caracteres e contexto | Com | 78,57% | 0,7134 | 91,43% |
| V12 | Sem | 74,29% | 0,7163 | 100,00% |
| V13 palavras, caracteres e contexto | Sem | 68,57% | 0,6378 | 84,29% |

## Arquivos e execução

- `commitx/dados_v13.py` valida os registros, as origens e os vínculos.
- `commitx/modelo_v13.py` implementa o pré-processamento, o treino e a inferência.
- `commitx/experimento_v13.py` reproduz a V12, avalia as variantes V13 e salva artefatos.
- `commitx_site_git_v13.py` e `commitx/site_v13.html` servem a interface experimental.
- `commitx/comparador_commit.py` recebe o nome da versão e da fonte dos indícios.
  Os valores padrão conservam o comportamento da V12.
- `tests/test_v13.py` cobre escopo, normalização, abstenção, vínculos, lista recente,
  limites do diff e AST.

Na raiz do projeto, com as dependências de `requirements.txt`:

```bash
python commitx_site_git_v13.py --repositorio . --artefatos resultados/modelo-experimental-v13-01
```

Abra 127.0.0.1:8765. Para reproduzir o treino com as entradas nas pastas já
usadas pelo projeto, execute `python -m commitx.experimento_v13`. Para repetir
com um diretório de saída novo, use `--saida`. O diretório experimental
contém os dois modelos, o manifesto de hashes, `avaliacao.json` e
`previsoes_oof.csv`. Carregue artefatos joblib locais de origem conhecida.

## Testes e limitações

Passaram as suítes `python -m unittest discover -s testes` (242 testes) e
`python -m unittest discover -s tests` (86 testes). O Playwright em Chromium
verificou a abertura vazia, o seletor, HEAD/SHA, exemplos, campos obrigatórios,
categoria fora do escopo, independência dos painéis, importação, histórico e
AST. Também foram verificados os hashes das entradas e dos modelos.

A V13 ficou abaixo da meta de 80% sem prefixo. Mesmo sem o limiar de abstenção
e as restrições de escopo, a SVM experimental atingiu 67,25% nessa tarefa,
contra 71,28% da V12. Este desenho não isola o efeito da expansão do efeito
das mudanças de atributos e pesos. O corte em português precisa de exemplos
reais rotulados de forma independente. As conclusões sobre intenção do commit
continuam dependentes de revisão humana.
