#!/usr/bin/env fish
cd (dirname (status filename))/..
or exit 1

echo "== Testes V5: particoes, persistencia, diff =="
.venv/bin/python -m unittest discover -s tests -p test_revisao_git_v5.py -v
or exit $status

if not test -f resultados/revisao-git-v5-01/plano.json
    echo "== Separando 8 repositorios antes de rotular =="
    .venv/bin/python -m commitx.revisao_git_v5 preparar
    or exit $status
else
    echo "== Reutilizando plano V5 existente =="
end

echo "== Conferindo progresso =="
.venv/bin/python -m commitx.revisao_git_v5 status
or exit $status

echo "== Revisao de 120 commits (4 telas de 30) =="
echo "Em cada tela: 1=1,3;2=2,2;... para rotular, d3 para ver diff, q para sair."
.venv/bin/python -m commitx.revisao_git_v5 revisar \
    --particao treino --tamanho 30 --limite 120
or exit $status

echo "== Progresso final =="
.venv/bin/python -m commitx.revisao_git_v5 status
