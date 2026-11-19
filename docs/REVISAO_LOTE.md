# Revisão rápida em lote no CommitX

O comando mostra cinco mensagens por vez e permite confirmar/corrigir várias avaliações em uma única linha de entrada. **Nenhum rótulo é salvo automaticamente.** Todas as respostas continuam registradas no mesmo SQLite de avaliações humanas.

## Executar (Fish ou Bash)

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/revisao-lote-rapida
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.rotulagem --amostra resultados/amostras/rodada1.csv lote --tamanho 5 --limite 20
```

Se já houver avaliações humanas, a tela pula esses commits sem perder dados. A amostra de 300 commits e o banco de 100 mil commits não são alterados.

## Como responder

A tela mostra títulos, um resumo do corpo e sugestões de categoria e clareza. Digite a resposta conforme os números apresentados:

- `1=,3` — para mensagem 1, aceitar a **categoria sugerida** e definir clareza `3 = claro`.
- `2=4,2` — para mensagem 2, definir `4 = refactor` e `2 = parcial`.
- `1=,3;2=4,2` — avaliar duas mensagens em um único comando.
- `1=ok` — aceitar **as duas sugestões**, apenas quando existem categoria e clareza sugeridas.
- `d2` — abrir detalhes completos da mensagem 2.
- `p` — pular os itens ainda pendentes da página e continuar.
- `q` — sair e preservar o que já foi confirmado.

Depois de uma resposta válida, os itens salvos saem da página atual. Os ainda pendentes continuam visíveis, renumerados a partir de 1. **Leia a nova numeração antes de responder novamente.**

O programa valida **toda a linha** antes de salvar. Se uma opção for inválida, a linha inteira é rejeitada. Uma vez validada, cada decisão humana é registrada imediatamente.

Não é necessário digitar resposta para cada mensagem: você pode revisar as relevantes e usar `p` para passar adiante. Os itens pulados não são rotulados.

## Importante sobre sugestão e treino

- Categorias automáticas vêm de um modelo didático com 50 exemplos sintéticos ou do prefixo declarado.
- A clareza não possui modelo validado, logo na maioria dos casos **não existe uma sugestão para confirmar**. Digite um número.
- Rótulos sugeridos não viram automaticamente rótulos humanos.
- Para validação e teste reservados, o programa **não apresenta sugestões**, mesmo quando a opção está ativada; avalie às cegas.
- Para rotular tudo sem sugestões, acrescente `--sem-sugestoes`.
- A opção `--limite` limita avaliações confirmadas nesta sessão e `--tamanho` limita mensagens exibidas por página (1–20).
- O progresso pode ser conferido com:

```bash
.venv/bin/python -m commitx.rotulagem --amostra resultados/amostras/rodada1.csv status
.venv/bin/python -m commitx.treino_real status
```

O modo em lote facilita a revisão, mas não elimina a necessidade de rótulos humanos variados e avaliação independente do modelo.
