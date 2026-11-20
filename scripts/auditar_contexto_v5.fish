#!/usr/bin/env fish
# V5: auditoria de arquivos e mudancas Git dos nove erros reais.
cd (dirname (status filename))/..
or exit 1

echo "== Testes V5 =="
.venv/bin/python -m unittest discover -s tests -p test_auditoria_contexto_v5.py -v
or exit $status

set -l saida resultados/auditoria-contexto-v5-01
if test -f $saida/resumo.json; and test -f $saida/auditoria.csv
    echo "== Auditoria V5 ja existe, reutilizando =="
else
    if test -e $saida
        set saida resultados/auditoria-contexto-v5-(date +%Y%m%d-%H%M%S)
    end
    echo "== Consultando somente erros de validacao e Git local =="
    .venv/bin/python -m commitx.auditoria_contexto_v5 --saida $saida --raiz-repos repos
    or exit $status
end

echo "== Relatorio simples =="
cat $saida/relatorio.md
or exit $status

echo "== ZIP somente dos relatorios V5 =="
.venv/bin/python -c '
from pathlib import Path
from datetime import datetime
import zipfile,sys
p=Path(sys.argv[1])
out=Path.home()/"Downloads"/"commitx_v5_auditoria_contexto.zip"
if out.exists():
 out=out.with_name(out.stem+"-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".zip")
out.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED) as z:
 for name in ("resumo.json","auditoria.csv","relatorio.md"):
  z.write(p/name,arcname=name)
print("ZIP PARA ENVIAR:",out)
' $saida
or exit $status
echo "Nenhum banco, rotulo ou modelo foi alterado."
