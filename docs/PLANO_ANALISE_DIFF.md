# Plano de integração da análise semântica de diffs

A camada de análise do diff deve produzir indícios explicáveis sobre alterações em commits Git locais. A etapa atual documenta o desenho e os critérios de integração. A categoria sugerida ao usuário continua sendo a previsão textual da V12, incluindo suas abstenções.

## Fluxo observado

| Componente | Comportamento atual |
| --- | --- |
| `commitx/leitor_diff.py` | `analisar_commit(repositorio, commit="HEAD", *, max_chars=8000)` resolve a referência para SHA e devolve título, descrição, contagens, arquivos, SHA de comparação, indicador de merge e prévia com `diff_truncado`. Commits com pais, inclusive merges, são comparados ao primeiro pai. Commits raiz são lidos como adições iniciais. |
| `commitx/v12_final.py` | `analisar_modelo(artefatos, titulo, modo)` classifica pelo título. O retorno inclui categoria, modo, tipo declarado, margem SVM e avisos. O site usa a descrição na revisão de escrita. |
| `commitx_site_git_v10.py` | O servidor usa `ThreadingHTTPServer` em `127.0.0.1`, com repositório escolhido na inicialização. `POST /api/git/analisar` aceita `HEAD`, `HEAD~N` com até três dígitos ou SHA hexadecimal de 7 a 40 caracteres. A rota solicita uma prévia de 6.000 caracteres e retorna `git`, `analise` e `sinais`. |
| Heurística da V10 | `classificar_alteracoes` usa caminhos para sinalizar alterações exclusivamente de documentação ou de testes. Mudanças mistas ou em código ficam inconclusivas. A rota pode retornar a leitura Git com `analise: null` se a V12 estiver indisponível. |
| Referência V11 | `commitx/sinais_semanticos_v11.py` extrai indicadores de `docs` e `refactor` a partir do texto da mensagem, usados pela V12. A ideia de indícios é pertinente para o desenho, mas as expressões regulares do título têm outro domínio de entrada. |

## Arquitetura e interfaces propostas

1. **Leitura Git.** Preservar `analisar_commit` e seu contrato. Acrescentar, em etapa futura, uma entrada interna para obter arquivos alterados e versões anterior e posterior, usando os SHAs resolvidos e a mesma base de comparação do leitor. A entrada deve registrar status do arquivo, caminhos anterior e posterior, intervalos alterados e motivo explícito para cada versão omitida. Adição e remoção têm um dos lados ausente por definição. Manter `diff_previa` para exibição.
2. **Extração de evidências.** Criar um módulo separado em `commitx/`. A interface de trabalho `analisar_diff(alteracoes)` receberá registros normalizados com versões textuais e metadados de cobertura. A extração deve ser determinística e operar em memória, sem acesso ao Git, à V12 ou aos artefatos. Usar inicialmente caminhos e estrutura de código Python por meio de `ast` da biblioteca padrão. Comparar árvores dos arquivos completos e localizar as evidências nos trechos alterados. Preservar a heurística atual de caminhos para documentação e testes e começar a avaliação de código com sinais observáveis, como alteração em docstring, inclusão ou remoção de função e mudança em assinatura.
3. **Resultado estruturado.** A saída interna proposta traz `versao`, `estado` (`completo`, `parcial` ou `indisponivel`), `evidencias` (tipo, caminho, lado e intervalo de linhas quando aplicável) e `limitacoes`. Um resultado completo com lista vazia significa que as regras implementadas encontraram zero evidências. Lacunas de cobertura devem acompanhar resultados parciais. Uma assinatura nova ou modificada admite várias intenções. Casos ambíguos ficam sem sugestão semântica.
4. **Integração opcional.** Validar primeiro o módulo isolado. Em etapa posterior, avaliar expor a saída sob a chave adicional `analise_diff` da rota Git, inicialmente por opção explícita. Preservar códigos HTTP e o significado de `git`, `analise` e `sinais`, bem como os contratos de `/api/classificar` e `/api/comparar`. Falhas da nova camada deixam a leitura Git e a previsão textual disponíveis nas condições atuais. Apresentar a categoria da V12 ao lado dos indícios, mantendo a extração de evidências independente do título e da previsão.

## Riscos e tratamento

| Risco | Tratamento proposto |
| --- | --- |
| Prévia truncada e patch por trechos | Analisar versões completas dos arquivos elegíveis. Fixar limites de arquivos, bytes e tempo, inclusive durante a leitura. A prévia atual limita o retorno após capturar o patch. Registrar orçamento excedido como cobertura parcial. |
| Merges, commit raiz e renomeações | Preservar a comparação com o primeiro pai e tratar raiz e versões ausentes explicitamente. O leitor usa `--no-renames`, portanto um movimento pode aparecer como adição e remoção. Se houver detecção de renomeações mais adiante, definir sua política e testar seu efeito na comparação. |
| Binários, codificação, caminhos citados e sintaxe incompatível | Usar saída Git delimitada por NUL para os novos metadados de caminho. Registrar binários e falhas de decodificação ou de análise sintática com motivos próprios. Para linguagens sem analisador, limitar os indícios ao que os metadados permitem. |
| Ambiguidade entre `fix`, `feat` e `refactor` | Retornar fatos verificáveis, registrar sinais mistos e encaminhar casos ambíguos à revisão humana. Uma diferença entre as evidências e a categoria textual é um motivo para investigar. A margem SVM continua sendo uma medida do classificador textual. |
| Conteúdo local sensível e consumo de recursos | Ler apenas objetos do repositório configurado, por SHA, sem executar o conteúdo e sem usar a rede. Retornar evidências mínimas, como localização e tipo, e evitar patches integrais ou segredos em logs. |

## Etapas e critérios de aceite

1. **Fixar o contrato.** Definir os registros de entrada e saída, a unidade e os limites de cobertura e a taxonomia inicial. Especificar casos de referência em repositórios temporários.
2. **Validar leitura e extração isoladas.** Cobrir commit raiz, merge, ausência de alterações textuais, adição, remoção, possível renomeação, binário, caminho incomum, erro de sintaxe, truncamento da prévia e estouro de orçamento. Conferir tipo e localização de evidências em exemplos Python, documentação e testes, com resultados determinísticos e estados explícitos para lacunas.
3. **Validar integração opcional.** Comparar as respostas HTTP com a opção desligada e ligada. Cobrir a ausência de artefatos V12 e a falha isolada do extrator. Conferir que Git, revisão de escrita, previsão textual e abstenções continuam funcionando nos mesmos casos.
4. **Avaliar os indícios antes de ampliar a cobertura.** Usar exemplos revisados manualmente e reservados para a avaliação, identificados por repositório e SHA. Medir cobertura, abstenções e concordância por tipo de evidência. Registrar protocolo e resultados da nova camada em separado das métricas históricas da V12.
