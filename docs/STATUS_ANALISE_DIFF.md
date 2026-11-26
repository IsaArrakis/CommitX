# Status da análise semântica de diffs

## Etapa concluída

Etapa 7 concluída na branch `feat/analise-diff-semantico`. Para abrir a nova interface, execute `python commitx_site_git_v12.py --repositorio .` e acesse `http://127.0.0.1:8765`. O arquivo da V10 permanece disponível como ponto de entrada separado. As duas versões usam o backend da V10.

A interface mantém a classificação por título, a descrição opcional, a comparação dos modelos e o histórico recolhível. Na seção Git, o relatório mostra a mensagem e a categoria prevista pela V12, as evidências e seus arquivos, o estado da comparação com uma explicação curta e a lista de arquivos alterados. O diff abre em uma seção recolhível e indica quando a prévia foi truncada.

Quando os artefatos locais estão ausentes, a leitura do commit e seus indícios continuam disponíveis. Os dados do Git entram na página como texto. O servidor segue restrito a `127.0.0.1` e ao repositório configurado na inicialização.

## Verificações

- `python -B -m unittest testes.test_api_git testes.test_comparador_commit testes.test_analise_diff testes.test_leitor_diff` passou nos 54 testes.
- Os testes no Chromium exercitaram a classificação, a comparação dos modelos, os três estados do relatório Git, o truncamento, a abertura e o fechamento das seções, o histórico e os erros de entrada. Usaram commits temporários reais, previsões simuladas e o cenário real de artefatos ausentes.
- O Chromium exibiu marcação HTML de um commit como texto no relatório, no histórico e no diff. Durante a verificação, todas as requisições ficaram no servidor local e o repositório temporário manteve a mesma referência e a árvore limpa.
- `git diff --check` e `git diff --cached --check` passaram.
