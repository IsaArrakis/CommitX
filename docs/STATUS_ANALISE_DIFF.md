# Status da análise semântica de diffs

## Etapa concluída

Etapa 3 concluída na branch `feat/analise-diff-semantico`. O extrator `analisar_diff` acrescenta `indicios` ao resultado, com categoria sugerida pelos caminhos, estado, indicação de mistura, evidências por arquivo, arquivos relacionados e limites. O indício `docs` ou `test` exige que todos os arquivos tenham sinais exclusivos da mesma categoria. Casos mistos e sinais insuficientes retornam `estado: inconclusivo` e `categoria: null`.

## Arquivos alterados

- `commitx/analise_diff.py` reconhece convenções de documentação e de testes e avalia o conjunto de arquivos recebido do leitor.
- `testes/test_analise_diff.py` cobre README, documentação, testes Python e JavaScript, combinações com código, arquivos sem sinais, sobreposição de sinais, binários e prévia truncada.
- `docs/STATUS_ANALISE_DIFF.md` registra o contrato entregue, as verificações e o próximo passo.

## Testes e verificações

- `.venv/bin/python -m unittest testes.test_analise_diff testes.test_leitor_diff -v` passou nos 27 testes, incluindo 11 novos casos de indícios e os seis testes do leitor.
- `git diff --check` e `git diff --cached --check` passaram.

## Problemas conhecidos

- Os indícios usam convenções de nomes, extensões e diretórios. Caminhos que correspondem às duas categorias geram abstenção. Arquivos binários ficam sem indício de categoria. A intenção do commit exige revisão do conteúdo e do contexto.
- Os indícios por caminho usam a lista completa de arquivos do leitor, inclusive quando parte do patch fica fora da prévia. A avaliação ignora a mensagem do commit.
- Os sinais Python são léxicos e dependem do contexto visível por hunk. Uma declaração ou string que começa fora desse contexto pode escapar à análise. A cobertura sintática inicial abrange `.py` e `.pyi`. A indicação de testes usa convenções de caminho.
- Uma prévia truncada pode omitir arquivos ou linhas. O resultado sinaliza cobertura parcial, descarta a última linha quando interrompida e mantém os totais originais do leitor. Um hunk malformado é descartado, preservando as evidências dos demais hunks válidos.

## Próximo passo

Validar a integração opcional com o site, preservando o contrato atual das rotas e verificando a leitura Git quando os artefatos da V12 ou a análise do diff estiverem indisponíveis.
