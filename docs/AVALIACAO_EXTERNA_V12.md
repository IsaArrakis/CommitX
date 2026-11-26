# Protocolo de avaliação externa da V12

A proposta é revisar **180 commits reais**, com faixa de 150 a 200, em pelo menos cinco repositórios públicos independentes. Para intervalos por agrupamento, prefira dez ou mais projetos. Escolha projetos com históricos próprios, sem forks, espelhos ou linhagens compartilhadas com o desenvolvimento do CommitX. Registre os critérios de inclusão e os HEADs antes de ver os rótulos ou as previsões. Busque projetos com mensagens em português e inglês. A seleção em rodízio usa semente 42 e até os 500 commits não merge mais recentes de cada HEAD. A distribuição das cinco classes será conhecida após a revisão. Preserve os casos difíceis e reporte a distribuição observada.

## Preparação e revisão

1. Reúna inventários CSV com `id,repositorio,titulo` para o treino da V12 e as origens conhecidas de validações e auditorias anteriores. Use SHAs completos de 40 caracteres e repositórios separados por vírgula quando houver várias origens. Use registros de proveniência já exportados, sem abrir testes reservados para selecionar parâmetros ou ajustar modelos. Se o inventário estiver indisponível ou incompleto, registre a lacuna e suspenda a alegação de independência.
2. Execute o preparo em uma nova pasta. Ele exclui projetos conhecidos, SHAs iguais e títulos normalizados iguais, inclusive quando os prefixos diferem. `exclusoes.csv` conserva os SHAs, repositórios e hashes dos títulos normalizados. O manifesto registra os hashes dos inventários fornecidos, da amostra e das exclusões, além dos HEADs de origem. A exclusão por nome curto é conservadora, por isso projetos homônimos também são descartados. Revise manualmente possíveis forks e mensagens quase duplicadas.
3. Entregue aos revisores somente `amostra.csv`, os repositórios para consulta e uma cópia do formulário `rotulos.csv`. Inspecione o diff quando necessário. O título original pode conter um prefixo do autor. Fundamente o rótulo nas evidências da alteração, registrando a justificativa em texto livre e o idioma do título (`pt`, `en`, `outro`, `misto` ou `incerto`).
4. Use `fix` para correção de comportamento, `feat` para funcionalidade, `docs` para documentação, `refactor` para reorganização e `test` para testes. Use `indeterminado` para intenções mistas ou evidência insuficiente e `fora_escopo` para mudanças fora das cinco classes. Faça duas revisões independentes e registre consensos ou desacordos antes de congelar o gabarito. Preserve as fichas individuais. Durante a revisão, mantenha previsões da V12 e sugestões de IA fora das fichas.
5. Valide o formulário final. Prossiga com a avaliação global apenas com revisão completa, pelo menos 120 exemplos elegíveis, 15 por classe e cinco repositórios entre os elegíveis. A validação calcula suporte e integridade dos arquivos. A confirmação da origem e da independência dos rótulos cabe aos responsáveis pela revisão.

```bash
.venv/bin/python -m commitx.avaliacao_externa preparar-v12 \
  --repos /caminho/repo1 /caminho/repo2 /caminho/repo3 /caminho/repo4 /caminho/repo5 \
  --historicos treino-v12.csv origens-desenvolvimento.csv --quantidade 180
.venv/bin/python -m commitx.avaliacao_externa validar-v12
```

## Avaliação após o congelamento

- Compare `analisar_modelo` nos modos `com_prefixo` e `sem_prefixo` com os títulos originais dos mesmos exemplos elegíveis. Use os artefatos V12 locais confiáveis e a verificação de integridade existente. A baseline prevê sempre a classe majoritária dos rótulos usados no treino V12, determinada antes de abrir o gabarito externo. Resolva empates pela ordem fixa `fix, feat, docs, refactor, test`.
- Reporte acurácia, macro-F1 das cinco classes e precisão, recall, F1 e suporte por classe. Conte abstenções como erros na acurácia e como falsos negativos no recall da classe real. Use uma matriz com as classes reais nas linhas e as cinco previsões mais a coluna de abstenção. Informe cobertura de previsão, número e taxa de abstenções, quantidade total, quantidade elegível e exclusões por motivo. Eventuais métricas apenas sobre respondidos devem incluir seu denominador.
- Para incerteza, use IC exploratório de 95% por bootstrap de repositórios, com 2.000 reamostragens e semente 42. Reamostre projetos completos com reposição e use os mesmos sorteios para diferenças entre modelos. Informe o número de projetos. Com menos de dez grupos elegíveis, reporte estimativas pontuais e marque o intervalo como insuficientemente sustentado.
- Apresente cortes em português e inglês somente com 30 exemplos elegíveis, cinco repositórios e três exemplos de cada classe no idioma. Registre a cobertura e o tamanho de cada corte, inclusive dos idiomas sem suporte suficiente.
- No relatório futuro, inclua o protocolo, origens e HEADs, distribuição, hashes da amostra e do gabarito, SHA do código do avaliador, versão e hashes dos artefatos V12, versões de Python e dependências, semente e método de intervalo. Conserve a V12 congelada e mantenha essa amostra fora de futuros ajustes de treinamento.

A avaliação está pendente de uma amostra real, gabarito humano independente e artefatos V12. Os comandos acima preparam e validam os insumos. O comando histórico `avaliar` pertence aos modelos acadêmicos anteriores.
