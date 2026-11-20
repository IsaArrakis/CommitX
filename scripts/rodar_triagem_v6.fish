#!/usr/bin/env fish
cd (dirname (status filename))/..
or exit 1

echo "== V6: testes offline, antes de rodar a triagem =="
.venv/bin/python -m unittest discover -s tests -p test_triagem_automatica_v6.py -v
or exit $status

echo "== Verificando base V5 sem modificar os rótulos =="
.venv/bin/python -m commitx.revisao_git_v5 status
or exit $status

set -l modelo qwen2.5:3b-instruct
set -l n 60

if not command -sq ollama
    echo "Aviso: Ollama nao esta instalado. Executando a triagem SVM local SEM Ollama."
    .venv/bin/python -m commitx.triagem_automatica_v6 --sem-ollama
    or exit $status
else
    echo "== Modelos Ollama locais =="
    ollama list
    if not ollama list | string match -rq '^qwen2\.5:3b-instruct\s'
        echo "Modelo '$modelo' nao instalado. Nao faremos download automatico."
        echo "Para instalar depois: ollama pull $modelo"
        echo "Executando por enquanto a triagem SVM, sem chamar Ollama."
        .venv/bin/python -m commitx.triagem_automatica_v6 --sem-ollama
        or exit $status
    else
        echo "== Triagem SVM + Ollama local (ate $n novos commits nesta rodada) =="
        .venv/bin/python -m commitx.triagem_automatica_v6 \
            --modelo-ollama $modelo --quantidade-ollama $n
        or exit $status
    end
end

echo "== Resumo V6 =="
.venv/bin/python -c '
import json
from pathlib import Path
p=Path("resultados/triagem-automatica-v6-01/resumo.json")
d=json.loads(p.read_text(encoding="utf-8"))
for k in ("treino_v5_assistido_reutilizado","pendentes_treino","svm_previsoes_provisorias","ollama_palpite_armazenado","ollama_novos_nesta_execucao"):
 print(k+":", d[k])
print("Pontos para revisar:", d["triagem_por_prioridade"])
print("Arquivo local:", d["saida"])
print("Nenhuma acuracia medida nesta etapa.")
'
or exit $status

echo "== Pronto. 500 rotulos antigos, 120 da V5 e teste reservado nao alterados. =="
