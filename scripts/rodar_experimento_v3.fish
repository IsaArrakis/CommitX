#!/usr/bin/env fish
# Rode a partir de qualquer pasta: fish scripts/rodar_experimento_v3.fish
cd (dirname (status filename))/..
or exit 1

echo "== Testes V3 =="
.venv/bin/python -m unittest discover -s tests -p 'test_experimento_v3.py' -v
or exit $status

set -l output resultados/experimento-v3-01
if test -e $output
    set output resultados/experimento-v3-(date +%Y%m%d-%H%M%S)
end

echo "== Experimento completo (9 configuracoes, validacao aninhada) =="
.venv/bin/python -m commitx.experimento_v3 --saida $output
or exit $status

echo "== Resultados resumidos =="
.venv/bin/python -c '
import json, sys
from pathlib import Path
d=json.loads((Path(sys.argv[1])/"resumo.json").read_text(encoding="utf-8"))
for k,v in d["metricas"].items():
    print(f"{k}: acuracia={v['acuracia']:.3f}, macro-F1={v['macro_f1']:.3f}")
    print("  recalls:", v["recall_por_classe"])
' $output
or exit $status

echo "== Empacotar relatorio e previsoes =="
.venv/bin/python -c '
from pathlib import Path
import sys, zipfile
p=Path(sys.argv[1])
dest=Path.home()/"Downloads"/("commitx_v3_resultados_"+p.name+".zip")
dest.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(dest, "x", compression=zipfile.ZIP_DEFLATED) as z:
    for name in ("resumo.json", "previsoes_oof.csv"):
        z.write(p/name, arcname=name)
print("ZIP PARA ENVIAR:", dest)
' $output
or exit $status

echo "Concluido. Banco SQLite e rotulos originais nao foram modificados."
