# Etapa 1 — Entendendo git diff

O `git diff` mostra diferenças entre versões de um arquivo. Linhas com `-` foram removidas; linhas com `+` foram adicionadas.

Exemplo:

```diff
- idade = 18
+ idade = 20
```

O leitor abaixo mostra a mensagem do commit, os arquivos alterados, quantas linhas foram adicionadas e removidas e uma prévia do patch. Ele é **somente leitura**; não salva nem altera rótulos, não classifica intenção e não verifica que a mensagem esteja correta.

## Primeiro teste no Linux (Fish)

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/leitura-git-diff
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.leitor_diff --repositorio . --commit HEAD
```

A opção `--commit HEAD` indica o commit mais recente na branch atual. Se for um commit de merge, o leitor exibe as mudanças em relação ao primeiro pai (a linha principal de onde o merge foi feito). Para examinar o anterior, use `--commit 'HEAD~1'` (as aspas funcionam no Fish).

Para obter dados em JSON:

```bash
.venv/bin/python -m commitx.leitor_diff --repositorio . --commit HEAD --json
```

Para saber se o leitor passou nos testes, procure uma linha final semelhante a `Ran N tests ... OK`. Se aparecer `FAILED` ou `ERROR`, envie o resultado antes de avançarmos.

**Limitações da primeira versão:** somente repositórios Git locais, somente commits individuais e os metadados do patch; o conteúdo do diff pode ser truncado na visualização. Não trata mudanças não commitadas, não produz classificações e não vincula ainda os diffs aos quase 100 mil commits coletados. Para o estudo comparativo, será necessário ligar com segurança cada exemplo rotulado ao seu repositório e SHA de origem e garantir a separação entre treino e avaliação.
