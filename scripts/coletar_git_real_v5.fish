#!/usr/bin/env fish
cd (dirname (status filename))/..
or exit 1

echo "== Testes da coleta Git real =="
.venv/bin/python -m unittest discover -s tests -p test_coleta_git_real.py -v
or exit $status

set -l destino resultados/coleta-git-real-v5-01
if test -e $destino
    set destino resultados/coleta-git-real-v5-(date +%Y%m%d-%H%M%S)
end

echo "== Coletando commits de clones Git locais =="
.venv/bin/python -m commitx.coleta_git_real --raiz repos --por-repo 150 --max-repos 20 --saida $destino
or exit $status

echo "== Relatorio =="
cat $destino/resumo.md
or exit $status

echo "== ZIP resumido (SEM mensagens e caminhos de commits) =="
.venv/bin/python -c '
import sys,zipfile
from pathlib import Path
from datetime import datetime
d=Path(sys.argv[1])
p=Path.home()/"Downloads"/"commitx_coleta_git_real_v5_resumo.zip"
if p.exists(): p=p.with_name(p.stem+"-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".zip")
p.parent.mkdir(exist_ok=True,parents=True)
with zipfile.ZipFile(p,"x",compression=zipfile.ZIP_DEFLATED) as z:
    for name in ("resumo.json","resumo.md"):
        z.write(d/name,arcname=name)
print("ZIP PARA ENVIAR:", p)
print("CSV LOCAL (nao compartilhar sem revisar caminhos/titulos):",d/"commits_git_reais.csv")
' $destino
or exit $status
echo "Nenhum rotulo, banco ou repositorio alterado."
