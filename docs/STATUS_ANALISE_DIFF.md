# Status da análise semântica de diffs

## Etapa concluída

Etapa 6 concluída na branch `feat/analise-diff-semantico`. A rota `POST /api/git/analisar` mantém os campos `git`, `analise` e `sinais`. O novo campo `analise_codigo` contém `diff`, com o resultado de `analisar_diff`, e `comparacao`, com o relatório de `comparar_commit`.

A V12 classifica a partir do título. A descrição alimenta a revisão de escrita. O analisador do diff usa a leitura Git mesmo quando a previsão textual está indisponível. Nesse caso, a API retorna `analise: null`, os indícios disponíveis e uma comparação inconclusiva com aviso. Uma falha na extração semântica retorna `analise_codigo.diff: null` e uma explicação. Referências inválidas ou ilegíveis retornam HTTP 400 com erro em JSON.

## Limites da análise

O backend consulta o repositório configurado na inicialização, por meio do leitor Git existente. O servidor escuta em `127.0.0.1`. O limite para o corpo JSON é de 8.192 bytes e a prévia do patch tem até 6.000 caracteres. Ausência de indícios, ambiguidade e truncamento podem tornar a comparação inconclusiva. A equivalência funcional exige revisão.

## Arquivos e verificações

- `commitx_site_git_v10.py` integra a análise semântica à rota Git.
- `testes/test_api_git.py` verifica a rota em loopback com commits temporários. O teste de compatibilidade simula a previsão V12 e verifica que a chamada ao modelo recebe apenas o título como conteúdo. O teste de modelos ausentes usa a chamada real a um diretório vazio.
- `docs/STATUS_ANALISE_DIFF.md` registra o contrato e as verificações.
- `python -B -m unittest testes.test_api_git testes.test_comparador_commit testes.test_analise_diff testes.test_leitor_diff` passou nos 54 testes. `git diff --check` passou.
