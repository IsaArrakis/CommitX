# Rotulagem supervisionada — CommitX

O novo módulo permite que uma pessoa revise título e corpo de uma mensagem e informe **duas avaliações independentes**: tipo de mudança e clareza. Nunca trata o prefixo do commit como rótulo verdadeiro.

## Começar no Fish ou Bash

Na pasta `~/CommitX-coleta`, na branch `feat/rotulagem-assistida`:

```bash
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.rotulagem iniciar --limite 10
.venv/bin/python -m commitx.rotulagem status
```

O programa mostra uma mensagem de cada vez. Para cada uma, escolha um número de categoria e outro de clareza. Digite `s` para pular ou `q` para encerrar. Os registros confirmados são salvos individualmente no SQLite em `resultados/rotulagem/avaliacoes.sqlite3`. Ao executar novamente, o programa continua pelos exemplos ainda não classificados.

## Categorias

- `fix`: correção de defeito.
- `feat`: funcionalidade nova.
- `docs`: apenas documentação.
- `refactor`: reestruturação sem alterar o comportamento previsto.
- `test`: alterações voltadas a testes.
- `fora_escopo`: intenção conhecida, mas fora dessas cinco classes (ex.: somente manutenção de dependências).
- `indeterminado`: não é possível saber a intenção pela mensagem.

Não adivinhe a intenção. Prefira `indeterminado` se a mensagem não sustenta uma classificação.

## Clareza

- `vago`: não identifica com precisão a mudança.
- `parcial`: identifica parte da mudança, mas deixa informação essencial ambígua.
- `claro`: informa suficientemente o que mudou no contexto descrito.
- `indeterminado`: não há informações suficientes para julgar.

Uma mensagem sem corpo pode ser clara; o título pode conter tudo o que é necessário. Clareza avalia a **mensagem**, não se o código realmente implementou o que diz. Para confirmar essa correspondência, seria necessário ler o diff.

## Exportar depois de revisar

```bash
.venv/bin/python -m commitx.rotulagem exportar --saida resultados/rotulagem/rotulados.csv
```

O CSV tem apenas registros efetivamente revisados. Para gerar outra versão, escolha outro nome; o exportador recusa sobrescrever arquivos existentes. O CSV original e o SQLite de coleta nunca são modificados.

## Limitações e próximo passo

A amostra inicial tem até 300 exemplos (no último processamento, 284). A distribuição não garante um conjunto adequado para treinamento ou avaliação independente por repositório. Antes de treinar, confira qualidade, quantidade de rótulos por classe, repos e partições. Não coloque registros `indeterminado` ou `fora_escopo` dentro das cinco classes. Os modelos de categoria e de clareza deverão ser treinados e avaliados separadamente.
