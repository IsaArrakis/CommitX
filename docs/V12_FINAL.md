# CommitX — versão final V12

A versão oficial é a **configuração congelada** `v12_extra_030`, implementada em `commitx/v12_final.py`. Ela combina TF-IDF e sinais textuais com `LinearSVC`. Os experimentos didáticos de `commits.py avaliar` usam configurações históricas próprias.

## Verificar os artefatos e iniciar o site

Na raiz do projeto, com o ambiente virtual preparado:

```bash
.venv/bin/python commitx_site_git_v12.py --repositorio .
```

Abra [127.0.0.1:8765](http://127.0.0.1:8765). O servidor usa `resultados/modelo-final-v12-01/` por padrão. A pasta deve conter `manifesto.json`, `v12_com_prefixo.joblib` e `v12_sem_prefixo.joblib`. Para outra pasta confiável, use `--artefatos /caminho/dos/artefatos`.

O endpoint [`/api/status`](http://127.0.0.1:8765/api/status) verifica a versão `V12-final-v12_extra_030` do manifesto e os hashes SHA-256 dos dois modelos. A verificação lê os bytes e não desserializa os arquivos. Consulte o campo `estado`:

| Estado | Significado |
| --- | --- |
| `pronto` | Os três arquivos estão presentes e os hashes correspondem ao manifesto. |
| `artefatos_ausentes` | O manifesto ou pelo menos um modelo está ausente. |
| `manifesto_incompativel` | O manifesto está malformado ou indica outra versão. |
| `integridade_invalida` | Os hashes esperados estão ausentes, divergentes ou a leitura falhou. |

Carregue somente artefatos locais de procedência verificada, pois a desserialização de `.joblib` pode executar código. Os hashes confirmam a integridade em relação ao manifesto. A autenticidade depende da origem dos arquivos. Use as versões registradas em `ambiente` no manifesto para reproduzir a inferência.

Com o pacote indisponível, o site informa a falha da previsão textual. A leitura Git e a análise AST continuam disponíveis. A comparação com a V12 fica inconclusiva quando falta uma previsão.

## Classificar commits com a V12

```bash
.venv/bin/python commits.py analisar-v12 'fix: Correct pagination bug'
.venv/bin/python commits.py analisar-v12 'Extract helper method' --modo sem_prefixo --json
.venv/bin/python commits.py analisar-v12 'docs: Update README' --modo com_prefixo
```

O modo `auto` (padrão) usa o classificador com prefixo quando reconhece `fix`, `feat`, `docs`, `refactor` ou `test` no início da mensagem; sem esse prefixo utiliza o modelo sem prefixos. Isso não garante que o prefixo esteja correto. Uma mensagem como `ci: ...`, cujo tipo declarado está fora das cinco classes, recebe **abstenção**.

O classificador utiliza **somente o título**, sem descrição e sem diff. A margem da SVM não representa probabilidade calibrada. A revisão explicável de escrita permanece independente da previsão.

A mesma inferência está disponível por `.venv/bin/python -m commitx.v12_final analisar 'refactor: Simplify method'`.

## Git e AST no site

Em **Analisar um commit existente do Git**, o leitor retorna metadados e a prévia do diff do repositório configurado. A comparação existente usa a categoria textual e indícios de caminhos e do diff. Quando solicitado no formulário, o servidor lê as versões `.py` e `.pyi` diretamente dos objetos Git e extrai evidências estruturais com AST. Pela API, envie `"analise_estrutural": true` no corpo de `POST /api/git/analisar`. O resultado aparece separadamente em `analise_estrutural` e traz cobertura e limitações.

Evidências AST descrevem a estrutura sintática observada. O reconhecimento de uma condição modificada ou possível movimentação de função ajuda a localizar mudanças para revisão. Intenção, correção e equivalência de comportamento exigem avaliação adicional.

## Resultados históricos e avaliação externa

| Avaliação exploratória (397 exemplos / 310 grupos / 5 folds) | Acurácia | Macro-F1 | Recall `refactor` | Recall `docs` |
|---|---:|---:|---:|---:|
| V12 com prefixo | 84,6% | 0,847 | 70,4% | 97,0% |
| V12 sem prefixo | 71,3% | 0,721 | 63,0% | 78,8% |

Esses números vêm de validação cruzada **exploratória do conjunto de desenvolvimento** e foram influenciados por múltiplos experimentos anteriores. Não medem a acurácia do artefato final em produção nem comprovam generalização em novos repositórios. O modelo final é treinado com todos os 397 exemplos de treino depois da verificação de paridade; ele não foi avaliado em um novo teste cego.

Os 1.603 candidatos coletados posteriormente, propostas de IA, pseudo-rótulos e diffs não são incorporados como gabarito validado. A avaliação externa requer uma amostra real rotulada às cegas e ainda não tem resultados. [Protocolo externo da V12](AVALIACAO_EXTERNA_V12.md)

## Testes

```bash
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m unittest discover -s tests -v
```

O CI usa Python 3.12 e executa as duas suítes em jobs separados. Fixtures temporárias cobrem modelos ausentes e inválidos. A comparação com as previsões dos artefatos oficiais exige uma execução local com modelos confiáveis.

## Modelo e limites

- TF-IDF de palavras (1–2 gramas, `sublinear_tf=True`, 50.000 características máximas).
- Dois indicadores semânticos da V11 com peso 0,5.
- Nove sinais contextuais da V12 com peso 0,3.
- `LinearSVC(C=0.3, random_state=42)` com pesos balanceados e multiplicadores de 1,75 (`docs`) e 1,50 (`refactor`).
- O prefixo convencional é um sinal do autor, não um rótulo certificado.
- Pode errar classes ambíguas e não verifica a intenção real do diff.

## Reprodução histórica dos artefatos

Na raiz do projeto, no Fish ou Bash:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python commits.py treinar-v12
```

O comando utiliza **somente a partição de treino** de `resultados/preparacao-inicial/commits_preparados.csv`, com os 397 rótulos registrados em `resultados/rotulagem/avaliacoes.sqlite3` e 310 grupos relacionados. Antes de salvar, exige a reprodução exata dos resultados OOF de:

- `resultados/experimento-v12-paridade-corrigida-01/previsoes_oof.csv` (V12 com prefixos);
- `resultados/experimento-v12-sem-prefixos-01/previsoes_oof.csv` (V12 sem prefixos).

Sem esses relatórios, ou com dados diferentes, o treinamento **interrompe**. Nenhum rótulo, SQLite, arquivo de teste/validação ou modelo anterior é alterado.

Os artefatos são salvos na pasta nova `resultados/modelo-final-v12-01/`:

- `v12_com_prefixo.joblib`: classifica títulos originais;
- `v12_sem_prefixo.joblib`: classifica títulos após remover o prefixo e escopo iniciais;
- `manifesto.json`: configuração, hashes dos arquivos, versões do ambiente e métricas históricas OOF.

A pasta de saída é criada em cada execução. Para uma execução adicional, passe `--saida resultados/modelo-final-v12-02`.
