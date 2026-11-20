#!/usr/bin/env fish
cd (dirname (status filename))/..
or exit 1
echo "== Testes V4 (sem precisar de Ollama) =="
.venv/bin/python -m unittest discover -s tests -p test_semantica_v4.py -v
or exit $status

if not command -sq ollama
    echo "ERRO: Ollama nao encontrado. Instale Ollama para executar a V4."
    exit 2
end

echo "== Preparando Ollama =="
if not ollama list | string match -rq '^embeddinggemma'
    echo "Baixando modelo de embeddings (somente uma vez)..."
    ollama pull embeddinggemma
    or exit $status
end

if not curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1
    echo "ERRO: Ollama nao esta respondendo em localhost:11434"
    echo "Abra outro terminal e execute: ollama serve"
    exit 2
end

set -l saida resultados/semantica-v4-01
if test -f $saida/resumo.json; and test -f $saida/previsoes.csv
    echo "== Reutilizando resultados V4 ja calculados =="
else
    if test -e $saida
        set saida resultados/semantica-v4-(date +%Y%m%d-%H%M%S)
    end
    echo "== Embeddings locais + comparacao 3 modelos por repositorio =="
    .venv/bin/python -m commitx.semantica_v4 --saida $saida
    or exit $status
end

echo "== Resumo V4 =="
.venv/bin/python -c '
import json,sys
from pathlib import Path
d=json.loads((Path(sys.argv[1])/"resumo.json").read_text(encoding="utf-8"))
for name,m in d["modelos"].items():
 print("%s: acuracia %.3f | macro-F1 %.3f" % (name,m["acuracia"],m["macro_f1"]))
 print("  recalls:",m["recall_por_classe"])
' $saida
or exit $status

echo "== Criando ZIP pequeno so com resultados =="
.venv/bin/python -c '
import zipfile,sys
from pathlib import Path
from datetime import datetime
p=Path(sys.argv[1])
dest=Path.home()/"Downloads"/"commitx_v4_semantica_resultados.zip"
if dest.exists():
 dest=dest.with_name(dest.stem+"-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".zip")
dest.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(dest,"x",compression=zipfile.ZIP_DEFLATED) as z:
 for f in ("resumo.json","previsoes.csv"):
  z.write(p/f,arcname=f)
print("RESULTADO PARA ENVIAR:",dest)
' $saida
or exit $status
echo "Feito. Nenhum rotulo foi alterado."
