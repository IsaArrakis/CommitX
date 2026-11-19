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
