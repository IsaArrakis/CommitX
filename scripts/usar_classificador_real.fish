#!/usr/bin/env fish
# Treina um classificador UTILIZAVEL e mostra uma previsao real.
# Nao sobrescreve o SQLite nem acessa as particoes validacao/teste.
cd (dirname (status filename))/..
or exit 1

echo "== Testes do classificador =="
.venv/bin/python -m unittest discover -s tests -p test_classificador_real.py -v
or exit $status

set -l saida resultados/classificador-real-01
if test -f $saida/modelo.joblib; and test -f $saida/manifesto.json
    echo "== Modelo ja treinado, reutilizando: $saida =="
else
    if test -e $saida
        set saida resultados/classificador-real-(date +%Y%m%d-%H%M%S)
    end
    echo "== Treinando SVM com rotulos humanos da particao treino =="
    .venv/bin/python -m commitx.classificador_real treinar --saida $saida
    or exit $status
end

echo "== Previsoes de exemplo =="
.venv/bin/python -m commitx.classificador_real analisar --modelo $saida --titulo "fix: Correct broken crash in runtime"
or exit $status
.venv/bin/python -m commitx.classificador_real analisar --modelo $saida --titulo "Add documentation for configuration guide"
or exit $status

echo "== Pronto =="
echo "Modelo salvo em: $saida"
echo "Para analisar qualquer titulo:"
echo ".venv/bin/python -m commitx.classificador_real analisar --modelo $saida --titulo 'Sua mensagem de commit'"
echo "Para analisar CSV inteiro:"
echo ".venv/bin/python -m commitx.classificador_real lote --modelo $saida --entrada /caminho/commits.csv --saida /caminho/previsoes.csv"
echo "Observacao: margem nao e probabilidade; o modelo nao verifica o diff."
