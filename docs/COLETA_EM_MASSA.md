# Coleta em massa — Etapa 1

O coletor prepara dados reais para posterior rotulagem e treinamento. **Não treina a IA**, não atribui rótulos automaticamente nem confirma que uma mensagem é clara.

## Instalar no Linux

Dentro da pasta CommitX:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install 'datasets>=3,<5'
```

A biblioteca `datasets` só é necessária para a importação do Hugging Face.

## Importar CommitPackFT (meta inicial: 70 mil)

Piloto:

```bash
.venv/bin/python -m commitx.coleta_massa hf --limite 100
.venv/bin/python -m commitx.coleta_massa status
```

Aumentar depois:

```bash
.venv/bin/python -m commitx.coleta_massa hf --limite 70000 --splits python javascript java markdown
```

O streaming evita baixar toda a base para a memória. Os registros armazenados preservam a mensagem, SHA, repositório, linguagem, licença e fonte, sem armazenar o diff. Cada par repositório/SHA é armazenado uma vez, inclusive quando o dataset possui várias linhas do mesmo commit. A meta pode não ser atingida se faltarem exemplos únicos nos splits selecionados.

## Importar Git local (meta inicial: 30 mil)

Clone projetos públicos cujos históricos você possa consultar. Os projetos devem ser escolhidos e revisados; o coletor não escolhe repositórios automaticamente.

Crie `repositorios.txt` com um caminho por linha:

```text
repos/projeto1
repos/projeto2
```

Execute:

```bash
.venv/bin/python -m commitx.coleta_massa git --repos repositorios.txt --limite 100
.venv/bin/python -m commitx.coleta_massa git --repos repositorios.txt --limite 30000 --max-por-repo 3000
```

O limite por repositório determina quantos commits do histórico local são examinados. Commits de merge são ignorados.

## Status e exportação para revisão humana

```bash
.venv/bin/python -m commitx.coleta_massa status
.venv/bin/python -m commitx.coleta_massa exportar --saida resultados/coleta/commits_para_rotular.csv
```

A coluna `categoria` sai vazia de propósito. A coluna `tipo_declarado` contém apenas o prefixo, quando presente, e **não** deve ser considerada rótulo verdadeiro. O CSV exportado não está pronto para treino supervisionado.

Os arquivos ficam em `resultados/coleta/`, já excluídos do Git pelo .gitignore existente. A exportação nunca sobrescreve um arquivo. A inserção confirma lotes de até 500 registros e é idempotente; se interrompida, a coleta pode ser repetida sem criar duplicatas. No entanto, **não há cursor remoto**: ao retomar, as linhas antigas são relidas.

## Cuidados

- Antes de usar ou compartilhar dados, audite mensagens potencialmente sensíveis, dados pessoais, segredos ou credenciais.
- Verifique as licenças e condições de uso das fontes.
- Mensagens similares e repositórios derivados podem causar vazamento entre treino e teste. Separe os conjuntos por repositório e examine a duplicação semântica.
- O CommitPackFT possui filtragem de qualidade e não fornece amostra equilibrada de mensagens vagas. Para aprender clareza serão necessários rótulos humanos e exemplos reais negativos.
- Um milhão de linhas não equivale a um milhão de commits únicos nem a um milhão de exemplos corretamente rotulados.
