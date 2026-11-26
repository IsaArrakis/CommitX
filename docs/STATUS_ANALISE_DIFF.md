# Status da análise semântica de diffs

## Etapa concluída

Etapa 5 concluída na branch `feat/analise-diff-semantico`. A função `comparar_commit` recebe a saída de `analisar_modelo` da V12 e a de `analisar_diff`. O relatório traz o status, a categoria textual, as categorias indicadas pelo diff, uma explicação, as evidências e os avisos. A previsão original da V12 continua disponível ao chamador.

## Critérios de comparação

- `compativel` indica que a previsão textual coincide com o único indício de categoria do diff.
- `possivel_divergencia` indica que o único indício de categoria do diff difere da previsão textual.
- `inconclusivo` cobre abstenção da V12, ausência de indícios, mistura ou ambiguidade, prévia truncada, leitura parcial e evidência de implementação obtida com cobertura insuficiente. As categorias e evidências disponíveis continuam no relatório.

A comparação considera o campo `categoria_sugerida` da V12. A evidência vem do diff e de seus caminhos. Os indícios de documentação e testes dependem de convenções de caminhos. Os de implementação dependem dos trechos Python analisáveis na prévia. A intenção e a equivalência funcional exigem revisão.

## Arquivos e verificações

- `commitx/comparador_commit.py` implementa a comparação.
- `testes/test_comparador_commit.py` cobre concordância, possível divergência, ambiguidade, mistura, ausência de evidências, cobertura insuficiente e preservação das entradas.
- `docs/STATUS_ANALISE_DIFF.md` registra o contrato e os limites da etapa.
- `.venv/bin/python -B -m unittest testes.test_comparador_commit testes.test_analise_diff testes.test_leitor_diff` passou nos 48 testes. `git diff --check` passou.

## Próximo passo

Avaliar os resultados em exemplos revisados manualmente antes de uma futura integração ao site.
