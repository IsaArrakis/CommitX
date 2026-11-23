#!/usr/bin/env python3
"""Integra CLI V12 de modo conservador no commits.py, com backup.

Extraia o ZIP na raiz do projeto, depois execute:
    .venv/bin/python scripts/instalar_v12_final.py

Não modifica banco de rótulos, modelos anteriores ou dados de avaliação.
"""
from pathlib import Path
import shutil
import sys

RAIZ = Path(__file__).resolve().parents[1]
MAIN = RAIZ / 'commits.py'
MODULO = RAIZ / 'commitx' / 'v12_final.py'
TESTE = RAIZ / 'testes' / 'test_v12_final.py'
DOC = RAIZ / 'docs' / 'V12_FINAL.md'

SUBCOMANDOS = '''
    # CommitX V12 final: modo opt-in, sem modificar a demonstracao didatica.
    tr12 = comandos.add_parser("treinar-v12", help="Verifica paridade e salva a V12 final.")
    tr12.add_argument("--saida", type=Path, default=Path("resultados/modelo-final-v12-01"))
    tr12.add_argument("--entrada", type=Path, default=Path("resultados/preparacao-inicial/commits_preparados.csv"))
    tr12.add_argument("--banco", type=Path, default=Path("resultados/rotulagem/avaliacoes.sqlite3"))
    tr12.add_argument("--ref-com", type=Path, default=Path("resultados/experimento-v12-paridade-corrigida-01/previsoes_oof.csv"))
    tr12.add_argument("--ref-sem", type=Path, default=Path("resultados/experimento-v12-sem-prefixos-01/previsoes_oof.csv"))
    an12 = comandos.add_parser("analisar-v12", help="Classifica com o modelo V12 final salvo.")
    an12.add_argument("titulo")
    an12.add_argument("--descricao", default="", help="Usada so na revisao de escrita.")
    an12.add_argument("--artefatos", type=Path, default=Path("resultados/modelo-final-v12-01"))
    an12.add_argument("--modo", choices=["auto", "com_prefixo", "sem_prefixo"], default="auto")
    an12.add_argument("--json", action="store_true")
'''

DESPACHO = '''
        if args.comando == "treinar-v12":
            from commitx.v12_final import treinar_e_salvar
            resumo = treinar_e_salvar(args.saida, args.entrada, args.banco,
                                     args.ref_com, args.ref_sem)
            print("Paridade V12 confirmada:", resumo["paridade_oof"])
            print("Artefatos salvos em:", args.saida)
            return 0
        if args.comando == "analisar-v12":
            from commitx.v12_final import analisar_modelo
            resultado = {
                "titulo": args.titulo.strip(),
                "descricao": args.descricao.strip(),
                "classificacao": analisar_modelo(args.artefatos, args.titulo, args.modo),
                "escrita": revisar_escrita(args.titulo, args.descricao),
            }
            if args.json:
                print(json.dumps(resultado, ensure_ascii=False, indent=2))
            else:
                exibir_analise(resultado)
            return 0
'''


def main():
    if not all(p.is_file() for p in (MAIN, MODULO, TESTE, DOC)):
        raise SystemExit('Execute na raiz do CommitX apos extrair o ZIP; arquivos obrigatorios nao encontrados.')
    s = MAIN.read_text(encoding='utf-8')
    if 'comandos.add_parser("treinar-v12"' in s and 'if args.comando == "treinar-v12"' in s:
        print('V12 ja integrada ao commits.py. Nenhuma alteracao realizada.')
        return
    if 'treinar-v12' in s or 'analisar-v12' in s:
        raise SystemExit('commits.py ja contem integracao V12 parcial/diferente; revisar manualmente.')
    anchor_parser = '    return parser\n'
    anchor_dispatch = '    try:\n        if args.comando == "coletar":'
    if s.count(anchor_parser) != 1 or s.count(anchor_dispatch) != 1:
        raise SystemExit('commits.py diferente do esperado; nao alterar. Use python -m commitx.v12_final.')
    atualizado = s.replace(anchor_parser, SUBCOMANDOS + anchor_parser, 1)
    atualizado = atualizado.replace(anchor_dispatch,
                                   '    try:\n' + DESPACHO + '        if args.comando == "coletar":', 1)
    compile(atualizado, str(MAIN), 'exec')
    pasta = RAIZ / 'resultados' / 'backup-integracao-v12'
    pasta.mkdir(parents=True, exist_ok=True)
    backup = pasta / 'commits.py'
    if backup.exists():
        raise SystemExit('Backup ja existente, nao sobrescrever: ' + str(backup))
    shutil.copy2(MAIN, backup)
    MAIN.write_text(atualizado, encoding='utf-8')
    print('V12 integrada ao commits.py. Backup:', backup)
    print('Proximo comando: .venv/bin/python -m unittest testes.test_v12_final -v')


if __name__ == '__main__':
    main()
