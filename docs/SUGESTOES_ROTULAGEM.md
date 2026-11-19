# Sugestões automáticas na rotulagem

O módulo `commitx.sugestoes` acrescenta sugestões, **sem substituir a decisão humana**, ao comando já existente de rotulagem.

## Uso

```bash
cd ~/CommitX-coleta
git fetch origin
git switch feat/sugestoes-rotulagem
.venv/bin/python -m unittest discover -s testes -v
.venv/bin/python -m commitx.rotulagem iniciar --limite 10
```

- Quando houver sugestão, **Enter** a confirma, mas a categoria e a clareza só são salvas depois de confirmar ambas as etapas.
- Um número **substitui** a sugestão.
- `s` pula; `q` sai. Na próxima execução são mostrados apenas itens pendentes.
- Se não houver sugestão, o Enter sozinho é inválido: selecione uma opção.
- `--sem-sugestoes` desativa todas as sugestões e mantém a interface anterior.
- `--revisar` permite reavaliar os registros já revisados (use com cuidado).
- `status` e `exportar` continuam funcionando sem alterações.

## Origem e limites das sugestões

**Categoria**: o modelo já existente (TF-IDF + Regressão Logística) é treinado sobre **50 exemplos sintéticos**, em memória, no início da sessão. Ele não foi treinado nem validado com os 100 mil registros coletados. Se o prefixo for uma das cinco categorias, ele será exibido como **sugestão declarada**, com aviso explícito caso o modelo discorde. Quando não houver prefixo, usa-se a previsão do modelo didático. Para prefixos fora das cinco classes não força uma categoria.

**Clareza**: enquanto não existirem pelo menos 30 rótulos humanos entre `vago`, `parcial` e `claro` (pelo menos cinco de cada), não treina classificador de clareza. Antes disso, apenas a regra explícita para títulos genéricos sem corpo pode sugerir `vago`, e outros casos permanecem sem sugestão. Ao alcançar o limiar, usa-se um modelo experimental TF-IDF + Regressão Logística com os rótulos já confirmados; **não há validação independente**, logo são propostas para revisão, não conclusões de qualidade.

**Importante:** a categoria humana e a clareza humana nunca são preenchidas por sugestões automáticas no SQLite. Rótulos `indeterminado` e `fora_escopo` não são incluídos nas cinco categorias.

O SQLite da coleta (100 mil registros), a amostra CSV e o banco de avaliações existente são preservados. Não é necessária uma nova coleta.

## Próximas etapas

Rotular mais exemplos (com distribuição real entre classes), separar repositórios de treino e teste, avaliar macro-F1, e só então passar a confiar mais em sugestões supervisionadas. Este módulo facilita a rotulagem, **não é ainda uma IA de clareza validada**.
