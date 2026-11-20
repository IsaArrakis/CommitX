#!/usr/bin/env fish
cd (dirname (status filename))/..
or exit 1

echo "== Testes de seguranca da validacao =="
.venv/bin/python -m unittest discover -s tests -p test_avaliacao_hibrido_validacao.py -v
or exit $status

echo "== Comparacao congelada, sem novo treinamento =="
set -l saida resultados/validacao-hibrido-v4-01
if test -e $saida
    set saida resultados/validacao-hibrido-v4-(date +%Y%m%d-%H%M%S)
end

.venv/bin/python -m commitx.avaliacao_hibrido_validacao --saida $saida
or exit $status

echo "== Resumo em linguagem simples =="
cat $saida/resumo.md
or exit $status

echo "== Preparar pacote reduzido para compartilhamento =="
.venv/bin/python -c '
import sys, zipfile
from pathlib import Path
from datetime import datetime
p=Path(sys.argv[1])
z=Path.home()/"Downloads"/"commitx_validacao_hibrido_v4.zip"
if z.exists():
    z=z.with_name(z.stem+"-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".zip")
z.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(z,"x",compression=zipfile.ZIP_DEFLATED) as arq:
    for name in ("resumo.json","resumo.md","previsoes.csv","erros_hibrido.csv"):
        arq.write(p/name,arcname=name)
print("ZIP FINAL:",z)
' $saida
or exit $status
echo "Teste reservado nao foi utilizado. Bases de rotulos intactas."
