# Primeiro experimento de melhoria do CommitX

Este experimento mede se adicionar TF-IDF de caracteres ao SVM linear existente
melhora as cinco categorias. **Nao altera os 97.001 commits ja processados.**

## Executar no Linux / Fish

```fish
cd ~/CommitX-coleta
git fetch origin
git switch feat/medicao-svm-palavras-caracteres
.venv/bin/python -m unittest tests.test_melhoria_svm -v
.venv/bin/python -m commitx.melhoria_svm --saida resultados/comparacao-svm-caracteres-01
cat resultados/comparacao-svm-caracteres-01/relatorio.md
```

A pasta `--saida` deve ser nova em cada execucao. A ausencia do banco SQLite
ou do CSV preparado interrompe o experimento: nao cria rotulos ficticios.

## O que e medido

- **original**: o mesmo pipeline TF-IDF palavras (1,2) + LinearSVC C=1.0 do
  `commitx.academico`.
- **palavras_caracteres**: mesmo classificador com TF-IDF de palavras e
  n-gramas de caracteres (`char_wb` de 3 a 5 caracteres).
- Ambas as configuracoes sao **fixas**, sem ajuste por resultados de teste.
- A validacao e `StratifiedGroupKFold` com agrupamento transitivo de
  repositorios e titulos repetidos.
- As previsoes OOF sao calculadas apenas com a particao `treino` do projeto.
- O conjunto de avaliacao externa Flask/Requests/HTTPX e o teste reservado V5
  **nao sao consultados**.

Resultados em `resultados/comparacao-svm-caracteres-01/`:

- `resumo.json`: acuracia, macro-F1, precisao/recall/F1 por classe, matrizes.
- `relatorio.md`: resumo legivel e tabela de recall.
- `previsoes_oof.csv`: previsoes dos dois modelos com os mesmos IDs.
- `casos_para_revisao.csv`: candidatos do proprio treino cujos rotulos
  divergem de pelo menos um modelo; **divergencia nao comprova erro do rotulo**.

## Interpretacao

O resultado OOF permite comparar as representacoes com menos risco de
vazamento entre repositorios, mas nao prova desempenho em projetos novos.
Alguns rotulos antigos receberam assistencia de IA. Nao se deve corrigir
os rotulos automaticamente com as previsoes geradas aqui.

**Se o novo modelo perder ou empatar**, manter o original ate haver evidencia
mais forte. Se ganhar, revisar erros por classe, obter exemplos melhores
de treino e validar a versao congelada em outros repositorios com avaliadores
independentes. Nao reutilizar a avaliacao externa de 45 commits para selecionar
hiperparametros ou anunciar 80% como resultado independente.
