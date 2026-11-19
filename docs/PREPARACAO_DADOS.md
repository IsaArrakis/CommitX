# Preparação inicial de dados — CommitX

A coleta concluída contém 100.000 registros em SQLite no computador do usuário. Este módulo **não modifica o banco**, não treina modelos e não atribui rótulos de verdade.

## Executar

Na pasta do projeto, na branch `feat/preparacao-100k`:

```bash
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.preparacao --amostra 300
```

O programa lê `resultados/coleta/commits.sqlite3` em modo somente leitura e grava em `resultados/preparacao-inicial/`:

- `commits_preparados.csv`: mensagens normalizadas, com marcações para revisão, candidatos de categoria e partição provisória por repositório.
- `amostra_para_rotular.csv`: até 300 exemplos para revisão humana, amostrados de forma determinística em até 12 estratos (fonte HF/Git × cinco tipos convencionais/sem tipo).
- `resumo.json`: quantidades lidas, mensagens únicas após deduplicação exata de texto, distribuição de origem e linguagem, contagem de prefixos e alertas.

Os campos `categoria` ficam vazios. `categoria_candidata` reflete somente o prefixo Conventional Commits. Não trate esse campo como gabarito. Alertas como `sem_corpo` e `resumo_muito_curto` não demonstram clareza ruim por si só.

O programa não sobrescreve resultados anteriores: se a pasta de saída já contiver arquivos, informe outra pasta (`--saida resultados/preparacao-v2`). Preserve o SQLite original.

## Cuidados metodológicos

- O split 80/10/10 é **provisório**: cada repositório vai para uma partição determinística, mas proporções reais, categorias e fontes não estão garantidas em todas as partições. Identificadores diferentes para o mesmo repositório e forks podem causar vazamentos.
- O algoritmo remove textos exatamente iguais após normalização de caixa, Unicode e espaços, mas não reconhece textos parafraseados. Registre o volume removido antes de decidir exclusões adicionais.
- A amostra é destinada a inspeção, não representa necessariamente o conjunto original nem uma amostra balanceada de qualidade.
- O banco mistura fonte filtrada CommitPackFT e históricos Git. Não rotule automaticamente clareza como boa porque o exemplo veio do CommitPackFT.
- Antes de distribuir ou treinar sobre os dados, verifique licenças e dados sensíveis nas mensagens.
- O treinamento depende de um conjunto revisado humanamente e de avaliação independente, sem usar os rótulos candidatos como verdade.

Depois de executar, veja `resumo.json` e inspecione manualmente `amostra_para_rotular.csv`. O próximo passo é definir um protocolo de rotulagem de categoria e clareza.
