# Status da análise semântica de diffs

## Etapa concluída

Etapa 8 concluída na branch `feat/analise-diff-semantico`. A apresentação usa `.venv/bin/python commitx_site_git_v12.py --repositorio .` e o endereço local `http://127.0.0.1:8765`. O README explica como iniciar o site, selecionar o repositório e usar artefatos V12 locais.

## Validação

| Verificação | Aprovados | Reprovados |
| --- | ---: | ---: |
| `.venv/bin/python -m unittest discover -s testes -v` | 189 | 0 |
| `.venv/bin/python -m unittest discover -s tests -v` | 75 | 0 |
| `.venv/bin/python -m unittest -v testes.test_leitor_diff testes.test_analise_diff testes.test_comparador_commit testes.test_api_git` | 57 | 0 |

A execução focada repete parte da suíte `testes/`. A primeira execução dessa suíte encontrou 4 falhas e 16 erros de ambiente porque a `.venv` não acessava o scikit-learn disponível no sistema. O ambiente virtual passou a usar os pacotes já instalados e a nova execução passou. O código da aplicação permaneceu intacto nesta etapa.

- Os commits temporários cobriram documentação, testes, tratamento de erro, funcionalidade nova, possível refatoração, alterações mistas e código ambíguo. A API também foi verificada com prévia truncada, referência inválida, commit vazio, repositório sem commits e modelos ausentes.
- A validação HTTP e no Chromium cobriu `GET /api/status` e `POST /api/classificar`, `POST /api/comparar` e `POST /api/git/analisar`. Um teste verifica que as rotas repassam as previsões da V12 e seus modos. A comparação Git entre a base `4866673` e esta etapa confirmou a integridade de `commitx/v12_final.py` e dos arquivos rastreados de dados e modelos.
- Um teste HTTP analisou um commit contendo uma instrução Python que criaria um arquivo. A API retornou os indícios e o arquivo não foi criado. A referência e a árvore do repositório temporário permaneceram intactas.
- O Chromium foi verificado com larguras de 390 e 1.440 pixels. A interface manteve fundo branco, texto legível e seções recolhíveis. Marcação presente em um commit apareceu como texto no relatório, no histórico e no diff.
- `git diff --check` e `git diff --cached --check` passaram.

## Limites da validação

Os artefatos finais da V12 estavam ausentes neste ambiente. Os testes de integração usaram respostas simuladas para verificar a passagem da previsão e a resposta real da aplicação para artefatos ausentes. Os testes próprios da V12 também passaram. A validação da apresentação não mediu a acurácia do analisador. As verificações de indícios se basearam nas alterações conhecidas dos commits temporários.

Documentação e testes dependem de convenções de caminho. Os indícios de implementação dependem da cobertura dos trechos Python analisáveis. Um diff truncado, alterações ambíguas ou indícios insuficientes podem deixar a comparação inconclusiva. A equivalência funcional, inclusive em refatorações, exige revisão.
