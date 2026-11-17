# Resultados da demonstração

Esta execução usa os mesmos 50 exemplos sintéticos da versão inicial, com dez por categoria. Nenhum exemplo foi acrescentado para melhorar a métrica. Os rótulos foram definidos com assistência de IA e precisam de revisão humana.

## Protocolo

- Cinco divisões estratificadas, semente 42; os três modelos usam as mesmas partições.
- Cada mensagem recebe uma previsão fora do treino (OOF); o TF-IDF aprende somente no treino de cada divisão.
- Não houve busca de parâmetros nem escolha de semente pelos resultados. O modelo misto foi definido antes desta execução.
- Os grupos da base didática são unitários. A separação por grupos relacionados precisa ser preparada na base real.
- Ambiente: Python 3.12.14; scikit-learn 1.8.0.

| Configuração | Acertos em 50 | Acurácia OOF | Macro-F1 OOF | Desvio F1 entre divisões |
| --- | ---: | ---: | ---: | ---: |
| palavras | 23 | 0.460 | 0.466 | 0.143 |
| misto | 31 | 0.620 | 0.624 | 0.064 |
| maioria | 10 | 0.200 | 0.067 | 0.000 |

O modelo misto acertou 31 mensagens e errou 19. Superou a configuração original de palavras nesta comparação exploratória. Isso não comprova ganho em repositórios reais nem significância estatística. A configuração mista também muda a frequência para sublinear e o peso das classes para balanced; o experimento não isola o efeito dos caracteres.

O resultado antigo de 40% usava apenas um holdout de dez mensagens. Ele não deve ser comparado diretamente com os 62% desta validação cruzada. A comparação adequada nesta execução é 46% (palavras) e 62% (misto), nos mesmos folds.

## Como reproduzir

```bash
.venv/bin/python commits.py avaliar --folds 5 --saida resultados
```

Leia `resultados/resumo.md` e `resultados/erros.csv`. O JSON guarda os IDs de treino/teste, as configurações e as versões. Os arquivos gerados não são versionados; são recriados pelo comando.

SHA-256 do CSV fornecido: `e7a3380c8d968e1f8c9ea43d88741310a15675c3dfbad0b3e2f7fcd53d640c08`.

SHA-256 da base canônica processada: `8dd21cdf712e54edef1b2cd375b57c00e09e930b532a170af6e881dee098b231`. A definição da serialização está em `metadados.formato_hash` no JSON.

## O que ainda falta validar

É necessário coletar e revisar mensagens reais, manter famílias de exemplos separadas entre treino e teste e usar dados independentes para avaliar escolhas motivadas por estes resultados. As métricas medem classificação de intenção, não clareza, veracidade da descrição ou correção do código.

As verificações de software cobrem isolamento dos grupos e vocabulário, leitura de CSV, coleta Git sem sobrescrever rótulos, preservação de mensagens e fluxos do terminal. Elas verificam funcionamento; não substituem a validação do modelo.
