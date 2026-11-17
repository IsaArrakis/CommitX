# Guia do trabalho de IA

## Objetivo e escopo

O CommitX classifica a intenção de mensagens de commit e oferece recomendações explicáveis de escrita. A classificação supervisionada usa TF-IDF e Regressão Logística nas classes `fix`, `feat`, `docs`, `refactor` e `test`. A revisão de clareza usa regras separadas, sem nota de qualidade validada.

A entrada é o título e o corpo da mensagem. O protótipo não analisa o diff, não confirma o que mudou no código e não inventa informações ausentes. Conventional Commits ajuda a organizar a mensagem, mas seu formato não garante clareza.

## Roteiro de sete dias

| Dia | Atividade | Resultado |
| --- | --- | --- |
| 1 | Clonar o projeto conforme o README, instalar dependências e experimentar o modo interativo. Ler os quatro módulos. | Saber localizar dados, regras, modelo e relatórios. |
| 2 | Escolher um repositório com histórico suficiente, coletar mensagens e definir a regra de rotulagem. | CSV com origem registrada e início da revisão humana. |
| 3 | Completar a revisão viável, tratar duplicatas e agrupar exemplos relacionados. Separar dados independentes para avaliação posterior, se possível. | Base documentada, sem copiar prefixos automaticamente como rótulos. |
| 4 | Executar a avaliação com os mesmos folds para palavras, misto e maioria. Ler o resumo e a matriz. | Métricas reproduzíveis e protocolo explicado. |
| 5 | Examinar erros e testar manualmente as regras de escrita. Registrar quais sugestões ajudam e quais falham. | Análise qualitativa e limitações concretas. |
| 6 | Preparar relatório e slides, se exigidos, usando somente resultados realmente obtidos. | Material com problema, método, dados, avaliação e limites. |
| 7 | Executar do início ao fim e ensaiar uma demonstração curta. | Entrega organizada e explicação com suas palavras. |

Confirme os formatos exigidos pelo professor. Se a base real ficar pequena, apresente isso como limitação. Os 50 exemplos fornecidos são sintéticos, criados com assistência de IA: não os descreva como uma amostra real. Não fabrique commits para preencher categorias ausentes.

## Como apresentar o experimento

Explique primeiro a origem dos dados e como foram rotulados. Depois mostre o fluxo: remover o prefixo inicial, transformar texto com TF-IDF, treinar Regressão Logística e prever a categoria. O modelo misto combina palavras e fragmentos de caracteres; o modelo de palavras e a previsão da maioria são referências de comparação.

Na validação cruzada, cada mensagem é prevista uma vez fora do treino. Os três modelos usam as mesmas divisões, e o TF-IDF aprende somente no treino de cada uma. Com grupos repetidos, os exemplos do mesmo grupo ficam juntos. Mostre macro-F1, acurácia, matriz de confusão e alguns erros.

O resultado antigo de `0,40` em dez mensagens de teste não é diretamente comparável à avaliação OOF das cinquenta mensagens. Também não prometa que o modelo misto vencerá: use os valores gerados pela execução. Ajustar o modelo com base nesses resultados exige uma avaliação independente posterior.

Para a demonstração, use uma mensagem vaga (`fix(admin): bug no painel`), uma específica (`docs: corrigir link de instalação no README`) e uma fora do escopo (`chore: atualizar dependências`). Mostre separadamente o tipo declarado, a sugestão do modelo e as regras de escrita. Um erro é material para discussão, não algo a ocultar.

## Perguntas para a defesa

- **Onde está a IA?** Na classificação supervisionada do texto. As recomendações de escrita são regras programadas.
- **Por que Regressão Logística?** É um classificador adequado como ponto de partida para características de texto e permite um experimento simples de reproduzir.
- **Como texto vira número?** O TF-IDF representa palavras ou fragmentos por pesos relacionados à sua frequência e distribuição na base de treino.
- **Por que remover o prefixo?** Para reduzir o atalho de copiar o tipo que o autor já declarou.
- **Por que comparar com a maioria?** Para verificar o ganho sobre uma estratégia simples que ignora o conteúdo.
- **O que significa OOF?** Cada previsão foi produzida em uma divisão em que aquela mensagem ficou fora do treino.
- **O que é macro-F1?** Uma média do F1 das classes que atribui o mesmo peso a cada categoria.
- **O sistema descobre qual bug foi corrigido?** Não. Ele só recebe a mensagem; seria necessário analisar o diff para investigar a alteração de código.
- **A clareza foi aprendida pelo modelo?** Não. As regras detectam alguns sinais de escrita vaga e não dão uma nota validada.
- **Os resultados valem para qualquer repositório?** Não. A base inicial é sintética e pequena; são necessários dados reais e avaliação independente.
- **Como evoluir?** Revisar rótulos com outra pessoa, ampliar a variedade dos dados, testar em outros repositórios e estudar clareza com avaliações humanas próprias.

## Conferência da entrega

- Código executa pelos comandos do README e as verificações automatizadas passam.
- Origem dos exemplos e uso de assistência de IA estão descritos com transparência.
- Regras de rotulagem, grupos, divisões e configuração do experimento estão registradas.
- Relatórios contêm resultados de execuções reais, separados por base utilizada.
- Exemplos de erro e limites aparecem junto das métricas.
- Você consegue explicar a diferença entre classificação, formato do cabeçalho e clareza.

Não há necessidade de acrescentar interface web ou integração remota antes de dominar o experimento. Este roteiro é uma sugestão de organização, não substitui os critérios do professor.
