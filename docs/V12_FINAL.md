# CommitX — versão final V12

Esta é a **configuração congelada** `v12_extra_030`, implementada em `commitx/v12_final.py` e separada da demonstração didática (`commits.py` sem as opções V12).

## Treinar e salvar o classificador definitivo

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

A pasta não é sobrescrita. Para uma execução adicional, passe `--saida resultados/modelo-final-v12-02`. Modelos `.joblib` podem executar código ao serem carregados; **carregue apenas artefatos locais que você mesmo treinou ou cuja procedência foi verificada**. O hash no manifesto é uma verificação de integridade, não de autenticidade.

## Classificar commits com a V12

```bash
.venv/bin/python commits.py analisar-v12 'fix: Correct pagination bug'
.venv/bin/python commits.py analisar-v12 'Extract helper method' --modo sem_prefixo --json
.venv/bin/python commits.py analisar-v12 'docs: Update README' --modo com_prefixo
```

O modo `auto` (padrão) usa o classificador com prefixo quando reconhece `fix`, `feat`, `docs`, `refactor` ou `test` no início da mensagem; sem esse prefixo utiliza o modelo sem prefixos. Isso não garante que o prefixo esteja correto. Uma mensagem como `ci: ...`, cujo tipo declarado está fora das cinco classes, recebe **abstenção**.

O classificador utiliza **somente o título**, sem descrição e sem diff. A margem da SVM não representa probabilidade calibrada. A revisão explicável de escrita permanece independente da previsão.

Para utilizar diretamente o pacote:

```bash
.venv/bin/python -m commitx.v12_final treinar
.venv/bin/python -m commitx.v12_final analisar 'refactor: Simplify method'
```

## Métricas registradas — contexto obrigatório

| Avaliação exploratória (397 exemplos / 310 grupos / 5 folds) | Acurácia | Macro-F1 | Recall `refactor` | Recall `docs` |
|---|---:|---:|---:|---:|
| V12 com prefixo | 84,6% | 0,847 | 70,4% | 97,0% |
| V12 sem prefixo | 71,3% | 0,721 | 63,0% | 78,8% |

Esses números vêm de validação cruzada **exploratória do conjunto de desenvolvimento** e foram influenciados por múltiplos experimentos anteriores. Não medem a acurácia do artefato final em produção nem comprovam generalização em novos repositórios. O modelo final é treinado com todos os 397 exemplos de treino depois da verificação de paridade; ele não foi avaliado em um novo teste cego.

Os 1.603 candidatos coletados posteriormente, propostas de IA, pseudo-rótulos e diffs não são incorporados como gabarito validado.

## Testes

```bash
.venv/bin/python -m unittest testes.test_v12_final -v
.venv/bin/python -m unittest discover -s testes -v
```

## Modelo e limites

- TF-IDF de palavras (1–2 gramas, `sublinear_tf=True`, 50.000 características máximas).
- Dois indicadores semânticos da V11 com peso 0,5.
- Nove sinais contextuais da V12 com peso 0,3.
- `LinearSVC(C=0.3, random_state=42)` com pesos balanceados e multiplicadores de 1,75 (`docs`) e 1,50 (`refactor`).
- O prefixo convencional é um sinal do autor, não um rótulo certificado.
- Pode errar classes ambíguas e não verifica a intenção real do diff.

Este é o encerramento técnico da V12. Para alegar desempenho em repositórios desconhecidos será necessário uma avaliação externa cega, definida antes de olhar seus rótulos.
