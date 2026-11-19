# Rotulagem automática com IA local (sem revisão commit por commit)

O comando usa **Ollama rodando no próprio computador** para gerar propostas de categoria e clareza. Não exige API paga e não envia os commits para uma API de LLM externa; o endereço usado é `127.0.0.1:11434`. O modelo ainda precisa ser baixado previamente, e o download exige internet.

As classificações da IA são **rótulos prata (pseudo-rótulos)**, nunca rótulos humanos. Não há garantia de precisão; a confiança declarada pelo LLM não é probabilidade calibrada. A execução atual NÃO treina automaticamente o classificador `treino_real` com essas previsões.

## 1. Instalar o Ollama no Arch Linux

Siga as instruções oficiais de https://ollama.com/download/linux. Em sistemas com pacote disponível, pode-se instalar o Ollama pelo gerenciador de pacotes. Inicie o serviço (`sudo systemctl start ollama`), ou abra `ollama serve` em outro terminal.

Baixe o modelo local:

```bash
ollama pull qwen2.5-coder:3b
ollama list
```

## 2. Usar a branch

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/rotulagem-ia-local
.venv/bin/python -m unittest discover -s testes -v
```

## 3. Testar apenas 100 commits (recomendado)

```bash
.venv/bin/python -m commitx.rotulagem_ia classificar --limite 100
.venv/bin/python -m commitx.rotulagem_ia status
```

O SQLite criado em `resultados/rotulagem-ia/sugestoes.sqlite3` contém categoria, clareza, justificativa, confiança subjetiva, modelo e versão do prompt de cada resposta. Ele não modifica `resultados/coleta/commits.sqlite3` nem `resultados/rotulagem/avaliacoes.sqlite3`.

## 4. Executar para todos os commits ainda elegíveis

```bash
.venv/bin/python -m commitx.rotulagem_ia classificar --limite 0
```

A execução pula registros que já foram classificados e continua após interrupção. Limite zero significa **toda a partição de treinamento**, não a validação nem o teste reservado. Mensagens com rótulos humanos são puladas por padrão.

Se o modelo falhar ou devolver formato inválido, o erro fica registrado; use `--retentar-erros` para tentar novamente.

**Atenção ao tempo e aos recursos:** processar dezenas de milhares de mensagens com um LLM local pode consumir muitas horas ou dias, dependendo da CPU/GPU e do tamanho das mensagens. Comece com o piloto de 100. O processo funciona na sessão do terminal; não é uma tarefa na nuvem que continue depois de desligar a máquina.

## 5. Exportar resultados

```bash
.venv/bin/python -m commitx.rotulagem_ia exportar --saida resultados/rotulagem-ia/resultado-prata-v1.csv
```

O comando não sobrescreve CSV existente. A exportação contém somente os rótulos e metadados automáticos e pode ser juntada à base de treino por `id`, com auditoria prévia.

## Limites metodológicos

1. O modelo local não verificou o diff. Ele avalia apenas a mensagem.
2. Mensagens externas podem conter instruções maliciosas (prompt injection). O prompt informa que o texto é não confiável, mas essa proteção não é perfeita.
3. Rótulos automáticos não devem ser usados como gabarito de validação/teste; são apenas hipóteses para treino semi-supervisionado após auditoria.
4. As 50 avaliações de validação existentes foram feitas com assistência de IA; não representam um teste humano totalmente independente.
5. Se quiser treinar com rótulos prata, implemente um experimento à parte, versionado e com limites; preserve os rótulos humanos como referência, um teste independente e uma estimativa da taxa real de erro em amostra auditada.
6. Nomes de modelos/prompts e logs de erros devem permanecer registrados; use um banco novo para cada modelo ou versão.

## Próximos passos

Aferir no piloto a concordância em amostra revisada humana, identificar erros especialmente de clareza, e só depois decidir se ampliaremos o conjunto de pseudo-rótulos para treinamento experimental.

## Corrigir respostas inválidas do Ollama

O modelo local pode retornar nomes em inglês como `bugfix`, `clear`, `high`. A versão atual normaliza apenas sinônimos inequívocos, rejeita valores desconhecidos e repete automaticamente até **3 solicitações** quando o retorno não tem o formato esperado. As respostas que continuam inválidas ficam com status `erro`, sem virar pseudo-rótulo.

Se já executou uma versão anterior com erros:

```bash
cd ~/CommitX-coleta
git pull --ff-only
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.rotulagem_ia classificar --limite 100 --retentar-erros
.venv/bin/python -m commitx.rotulagem_ia status
```

O parâmetro `--retentar-erros` recupera os commits registrados anteriormente com falha; commits com status `prata` não são processados novamente. O limite 100 corresponde a **até 100 tentativas na nova execução**, não ao total acumulado no banco.

Se houver erros repetidos de comunicação ou indisponibilidade, examine `ollama list` e `sudo systemctl status ollama` antes de tentar novamente.


## Piloto de qualidade v2 — auditoria dos 42 commits

A auditoria `docs/auditoria/commitx_relatorio_auditoria.md` mostrou divergências entre
um segundo parecer assistido por IA e as previsões do Ollama, especialmente na clareza.
A amostra foi direcionada e NÃO é um benchmark humano independente.

A rubrica v2:
- Não considera a ausência de descrição motivo suficiente para `vago` ou `parcial`.
- Compara ação, alvo e especificidade da mensagem, inclusive em títulos isolados.
- Diferencia documentação, correção, funcionalidade, refatoração e teste por intenção;
  o prefixo é apenas pista.
- Quando uma justificativa de baixa clareza cita a ausência de corpo, solicita
  uma segunda avaliação do Ollama sem aplicar promoção automática para `claro`.
- Preserva rótulos humanos e todas as previsões v1 no banco antigo.

**Mudança de versão:** o banco padrão v2 é
`resultados/rotulagem-ia/sugestoes_v2.sqlite3`, diferente do v1
`resultados/rotulagem-ia/sugestoes.sqlite3`.
Não mova nem renomeie o arquivo SQLite antigo.

Para experimentar a versão nova sem alterar a anterior:

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/qualidade-rotulagem-ia-v2
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.rotulagem_ia classificar --limite 100
.venv/bin/python -m commitx.rotulagem_ia status
.venv/bin/python -m commitx.rotulagem_ia exportar --saida resultados/rotulagem-ia/piloto_v2_100.csv
```

**Revisão e métricas:** compare distribuições v1/v2 e auditórias de casos 
selecionados sem tratar pareceres gerados por IA como verdade. Use rótulos humanos
independentes para estimar erro e macro-F1; o modelo não foi avaliado em máquina
com Ollama durante a implementação. Comparações pareadas dependem de os mesmos
commits serem processados; duas execuções `--limite 100` não garantem isso,
pois a v1 ignora itens já processados. O status `prata` não significa acerto.
