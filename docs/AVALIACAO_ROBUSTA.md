# CommitX — busca de modelos mais confiáveis

## Por que 64,1% não é uma medida definitiva?

O resultado atual é 25 acertos em 39 exemplos de validação de categoria. O mesmo conjunto já foi consultado repetidamente e parte dos rótulos foi assistida por IA. Os 2 exemplos de teste reservados não sustentam uma estimativa independente precisa.

Não existe uma transformação que garanta 90% de acurácia. Precisamos melhorar o modelo **e** medir sua generalização sem ficar otimizando com base nos mesmos exemplos.

## Etapa 1 — comparação com validação cruzada agrupada por repositório

Este módulo usa **apenas 397 registros da partição original de treino** (quantidade de referência antes de novas revisões) das cinco classes. Exclui todo o conjunto de validação e teste. Os grupos são formados conectando também registros que citam múltiplos repositórios, para prevenir vazamento do mesmo projeto para ambos os lados.

Compara usando os mesmos folds:
- Regressão logística TF-IDF de palavras (modelo atual);
- SVM linear com TF-IDF de palavras;
- SVM linear com TF-IDF de palavras e caracteres;
- Baseline majoritário.

Calcula acurácia, macro-F1, recall por classe e matriz de confusão, gerando arquivos de previsões em pasta nova.

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/avaliacao-robusta-modelos
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.avaliacao_robusta \
  --saida resultados/avaliacao-robusta-500-v1
```

Resultado resumido:

```bash
.venv/bin/python -c '
import json
p = "resultados/avaliacao-robusta-500-v1/resumo.json"
d = json.load(open(p, encoding="utf-8"))
print("Exemplos:", d["treino_elegivel"], "Grupos:", d["grupos_independentes"])
for nome, v in d["modelos"].items():
    print(nome, "acuracia", round(v["acuracia"], 3),
          "macro-F1", round(v["macro_f1"], 3),
          "recall", v["recall_por_classe"])
'
```

Se a análise encontrar menos de 5 grupos independentes, execute com `--folds 3`, desde que existam pelo menos três grupos. Em caso de classe ausente no treino de um fold, examine o aviso antes de interpretar as métricas. Não repita configurações indefinidamente escolhendo a que parece melhor.

## Etapa 2 — qualidade de rótulos e coleta de avaliação independente

Os 500 rótulos cadastrados foram úteis ao desenvolvimento, mas as sugestões assistidas por IA não formam automaticamente um gabarito independente. Audite uma amostra de casos ambíguos **sem mostrar as previsões** ao revisor, com orientações consistentes e dois revisores quando possível. Registre discordâncias, justificativas e correções sem apagar o histórico.

Para avaliar desempenho real, reúna uma nova amostra de **pelo menos 150–200 commits**, de repositórios que não tenham participado do desenvolvimento, rotulados independentemente, procurando representação de todas as cinco categorias. Defina esse protocolo **antes de ver as previsões**. O número é uma meta operacional, não garantia de precisão estatística; use intervalos de confiança, prevalência por classe e macro-F1.

## Etapa 3 — ampliar e congelar um modelo

Depois da comparação interna, escolha uma configuração sem olhar o conjunto independente, treine com os dados permitidos, e execute **uma única avaliação final**. Considere outras abordagens (embeddings, semântica de diff, LLMs) somente com o mesmo protocolo de comparação e orçamento computacional explícito.

O recurso atual não altera as bases SQLite nem cria rótulos. Os modelos desta etapa não são automaticamente implantados no classificador principal.
