# Status da análise semântica de diffs

## Etapa concluída

Etapa 4 concluída na branch `feat/analise-diff-semantico`. O campo `indicios_codigo` de `analisar_diff` descreve padrões em hunks Python de implementação. Cada evidência aponta para arquivo e linha. Uma mudança de condição inclui a linha anterior. O resultado admite múltiplas candidatas e fica inconclusivo em caso de ambiguidade, ausência de sinais ou cobertura parcial.

## Arquivos alterados

- `commitx/analise_diff.py` compara a estrutura sintática dos lados do hunk com a biblioteca padrão. A análise usa apenas o diff.
- `testes/test_analise_diff.py` verifica tratamento de exceções, declarações, arquivos novos, endpoints, condições, verificações de nulos, validação, extração de função, mudanças cosméticas, ambiguidade e truncamento.
- `docs/STATUS_ANALISE_DIFF.md` registra os critérios e a cobertura desta etapa.

## Testes e verificações

Os 34 testes de `testes.test_analise_diff` e `testes.test_leitor_diff` passaram. A verificação `git diff --check` passou.

## Limites da conclusão

Os padrões de correção abrangem cláusulas de exceção, asserções, comparações com `None` em condicionais e substituições de condições identificáveis no mesmo hunk. Declarações novas no trecho, arquivos Python criados e decoradores com método de rota e caminho literal fornecem indícios de funcionalidade.

Para movimentações, a regra procura funções de mesmo nome e estrutura visível em arquivos diferentes. Para extrações, procura uma expressão de retorno transferida para uma função auxiliar chamada pela função original. Mesmo uma coincidência estrutural exige revisão do contexto, dos argumentos e dos efeitos em execução. A equivalência funcional permanece em aberto.

A cobertura abrange fragmentos Python que podem ser analisados isoladamente. Hunks podem omitir escopos ou partes de funções. `diff_truncado` e `previa_insuficiente` registram os limites da prévia. As candidatas observadas continuam disponíveis para revisão.

## Próximo passo

Avaliar os indícios em exemplos revisados manualmente antes de uma futura integração ao site.
