# Fase 2 — Auditar a origem dos commits e extrair diffs reais

Este é o **primeiro passo da Fase 2**, não um novo treinamento. O CommitX já classifica mensagens. Agora queremos preparar uma pequena base de commits com o código alterado, para depois comparar modelos com e sem diff.

## 1. Executar os testes

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/fase2-auditoria-diffs
.venv/bin/python -m unittest discover -s testes -v
```

## 2. Auditar o conjunto existente (sem mudar o SQLite)

```bash
.venv/bin/python -m commitx.fase2_dados auditar \
  --saida resultados/fase2/auditoria-01.json
```

O arquivo registra quantos IDs parecem SHAs completos de 40 dígitos, quantos têm um campo de repositório e quantos rótulos do SQLite correspondem a IDs do CSV. **Um ID em formato de SHA não prova que podemos recuperar o diff.** Esta etapa não busca nada na internet, não presume endereços de GitHub e não conecta exemplos por título semelhante.

## 3. Gerar uma pequena amostra com diffs reais

```bash
.venv/bin/python -m commitx.fase2_dados piloto \
  --repositorio . \
  --quantidade 10 \
  --max-caracteres 1500 \
  --saida resultados/fase2/piloto-local-01.csv \
  --resumo resultados/fase2/piloto-local-01.json
```

Cada linha tem SHA completo, mensagem, repositório Git local, lista de arquivos e um trecho do patch. A categoria e a clareza ficam vazias; a partição é `nao_atribuida`. **Não use o piloto diretamente para treinar ou avaliar IA.** Ele serve para validar a estrutura de dados e permitir revisão metodológica. Pode haver diffs truncados, e o histórico mais recente não representa todos os projetos.

## 4. Ver os resultados

```bash
cat resultados/fase2/auditoria-01.json
cat resultados/fase2/piloto-local-01.json
```

Para evitar sobrescrita, a ferramenta recusa saídas já existentes: use `-02` no nome para uma nova execução.

## Próximas tarefas da Fase 2

1. Definir como localizar, **com certeza**, o repositório remoto e o SHA de cada commit da base coletada; não assumir que `id` contém o SHA.
2. Montar uma amostra de pesquisa com diffs de origem verificável e revisão humana específica, preservando a separação entre treino, validação e teste.
3. Registrar explicitamente a assistência por IA na classificação, quando houver, antes de alegar rótulos independentes.

**Segurança:** A auditoria lê o banco SQLite em modo somente leitura e não altera nenhuma avaliação. O piloto lê apenas o histórico Git local e cria arquivos novos na pasta `resultados/fase2`.


## 5. Recuperar o SHA original dos IDs de 64 caracteres

O codigo em `commitx/coleta_massa.py` confirma que o coletor criou cada `id` com SHA-256 de `repositorio.casefold() + NUL + sha.lower()`. O SHA original permaneceu salvo na coluna `sha` do banco `resultados/coleta/commits.sqlite3`.

Assim, nao precisamos tentar adivinhar o SHA a partir do ID. Recuperamos os dados por `id` em uma consulta SQLite de somente leitura, e recalculamos o hash para verificar a integridade.

```bash
.venv/bin/python -m commitx.fase2_vinculos \
  --saida resultados/fase2/vinculos-rotulados-01.csv \
  --resumo resultados/fase2/vinculos-rotulados-01.json

cat resultados/fase2/vinculos-rotulados-01.json
```

Por padrao, somente os IDs com rotulos existentes sao auditados. A opcao `--todos` inclui todos os registros da base. O arquivo resultante nao contem diffs nem e uma base de treinamento: um SHA recuperado precisa ser verificado no repositorio original, sobretudo para registros do Hugging Face ou com multiplos nomes de repositorio. Os arquivos CSV e SQLite existentes nunca sao modificados. Use nomes novos para repetir o experimento.
