#!/usr/bin/env fish
cd (dirname (status filename))/..
or exit 1

echo "== Testes do classificador híbrido =="
.venv/bin/python -m unittest discover -s tests -p test_classificador_hibrido.py -v
or exit $status

if not command -sq ollama
    echo "Ollama não encontrado; instale-o antes de continuar."
    exit 2
end

if not curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1
    echo "Ollama precisa estar rodando. Em outro terminal: ollama serve"
    exit 2
end

set -l dir resultados/classificador-hibrido-v4
if test -f $dir/modelo_hibrido.joblib; and test -f $dir/manifesto.json
    echo "== Reutilizando classificador híbrido já treinado =="
else
    if test -e $dir
        set dir resultados/classificador-hibrido-v4-(date +%Y%m%d-%H%M%S)
    end
    echo "== Treinando híbrido com 397 exemplos: cache existente de embeddings =="
    .venv/bin/python -m commitx.classificador_hibrido treinar --saida $dir
    or exit $status
end

echo "== Exemplos de classificação =="
.venv/bin/python -m commitx.classificador_hibrido analisar --modelo $dir --titulo "docs: Update documentation for installation"
or exit $status
.venv/bin/python -m commitx.classificador_hibrido analisar --modelo $dir --titulo "fix: Correct authentication error"
or exit $status

echo "== Pronto: classificador híbrido treinado =="
echo "Diretório do modelo: $dir"
echo "Exemplo:"
echo ".venv/bin/python -m commitx.classificador_hibrido analisar --modelo $dir --titulo 'Sua mensagem de commit'"
echo "Para um CSV com coluna titulo:"
echo ".venv/bin/python -m commitx.classificador_hibrido lote --modelo $dir --entrada /caminho/novos.csv --saida /caminho/previsoes.csv"
echo "Não alteramos os rótulos nem as partições de validação/teste."
