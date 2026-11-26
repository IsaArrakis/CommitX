# Status da análise semântica de diffs

## Etapa concluída

Etapa 2 concluída na branch `feat/analise-diff-semantico`. O extrator `analisar_diff` recebe o dicionário de `analisar_commit` e devolve dados estruturados e evidências por arquivo, lado e número de linha. As contagens totais do leitor e as contagens observadas na prévia são distintas. A extração usa apenas a biblioteca padrão, sem executar o conteúdo do patch ou atribuir uma categoria.

## Arquivos alterados

- `commitx/analise_diff.py` extrai evidências de funções, classes, imports, condições, exceções e comentários em Python. Identifica linhas de teste por caminho e binários pelos metadados do leitor.
- `testes/test_analise_diff.py` cobre diffs reais em repositórios temporários e a recuperação após um hunk malformado.
- `docs/STATUS_ANALISE_DIFF.md` registra o contrato entregue, as verificações e o próximo passo.

## Testes e verificações

- `.venv/bin/python -m unittest testes.test_analise_diff -v` passou nos 10 testes, cobrindo diff vazio, Python, múltiplos arquivos, funções adicionadas e removidas, exceções, truncamento, binário, hunk malformado e distinção entre cabeçalhos e linhas de código.
- `.venv/bin/python -m unittest testes.test_leitor_diff -v` passou nos seis testes do leitor. O ambiente virtual foi criado sem pip para executar as verificações.
- `git diff --check` e `git diff --cached --check` passaram.

## Problemas conhecidos

- Os sinais Python são léxicos e dependem do contexto visível por hunk. Uma declaração ou string que começa fora desse contexto pode escapar à análise. A cobertura sintática inicial abrange `.py` e `.pyi`. A indicação de testes usa convenções de caminho.
- Uma prévia truncada pode omitir arquivos ou linhas. O resultado sinaliza cobertura parcial, descarta a última linha quando interrompida e mantém os totais originais do leitor. Um hunk malformado é descartado, preservando as evidências dos demais hunks válidos.

## Próximo passo

Validar a integração opcional com o site, preservando o contrato atual das rotas e verificando a leitura Git quando os artefatos da V12 ou a análise do diff estiverem indisponíveis.
