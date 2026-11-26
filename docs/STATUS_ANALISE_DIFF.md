# Status da análise semântica de diffs

## Etapa concluída

Planejamento da integração a partir do estado de `main` em `4866673`. O ambiente começou sem checkout e a referência `feat/analise-diff-semantico` não foi encontrada no remoto consultado. A branch de trabalho foi criada localmente a partir dessa base, com a árvore de trabalho limpa. A entrega desta etapa contém somente documentação.

## Arquivos alterados

- `docs/PLANO_ANALISE_DIFF.md` registra o fluxo atual, as interfaces propostas, os riscos e os critérios de aceite.
- `docs/STATUS_ANALISE_DIFF.md` registra o escopo, as verificações, as limitações e o próximo passo.

## Testes e verificações

- `python -B -m unittest discover -s testes -p test_leitor_diff.py -v` passou nos seis testes do leitor Git.
- `python -B -m unittest -v testes.test_v12_final.V12FinalTests.test_sem_artefato_nao_finge_classificacao testes.test_v12_final.V12FinalTests.test_tipo_fora_escopo_abstem_sem_abrir_artefato` passou nos dois testes de inferência sem treinamento.
- A verificação HTTP em loopback usou um repositório temporário com um commit de documentação e um diretório vazio de artefatos. Passaram as três consultas a `GET /api/status` e `POST /api/git/analisar`, cobrindo status indisponível, leitura válida com `analise: null` e indício `docs`, e referência inválida com HTTP 400.
- `git diff --check` e a checagem equivalente do conteúdo preparado para commit (`git diff --cached --check`) passaram sem apontamentos.

## Problemas conhecidos

- `diff_previa` é uma amostra. A truncagem após a captura não limita o volume lido do Git e pode esconder mudanças necessárias à análise.
- A heurística atual usa caminhos e não distingue mudanças de comportamento de reorganizações internas. A comparação com o primeiro pai resume apenas uma perspectiva de um merge.
- A suíte completa inclui testes com ajuste de modelos. A verificação foi direcionada às rotinas de leitura e de inferência sem treinamento. A verificação HTTP usou o cenário sem artefatos, então a previsão com os modelos locais ficou fora do teste.

## Próximo passo

Definir os registros de entrada e saída e os limites da leitura de arquivos. Em seguida, preparar casos de referência com commits temporários e validar o extrator isoladamente antes da integração com o site.
