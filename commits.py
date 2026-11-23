"""Interface do CommitX: analisar mensagens, avaliar modelos e preparar dados."""

import argparse
import json
from pathlib import Path

from commitx.dados import carregar_dados, coletar_git
from commitx.escrita import revisar_escrita
from commitx.modelo import avaliar, sugerir, treinar
from commitx.relatorios import salvar_relatorios


BASE_PADRAO = Path(__file__).resolve().parent / "dados" / "commits_exemplo.csv"


def analisar_mensagem(modelo, titulo, descricao=""):
    escrita = revisar_escrita(titulo, descricao)
    return {
        "titulo": titulo.strip(),
        "descricao": descricao.strip(),
        "classificacao": sugerir(modelo, titulo, descricao),
        "escrita": escrita,
    }


def exibir_analise(resultado):
    classificacao, escrita = resultado["classificacao"], resultado["escrita"]
    print("\nTipo declarado:", escrita["tipo_declarado"] or "não identificado")
    print("Categoria sugerida:", classificacao["categoria_sugerida"] or "revisão humana necessária")
    for aviso in classificacao["avisos"]:
        print("Aviso:", aviso)
    if classificacao.get("evidencias"):
        print("Termos associados à sugestão:", ", ".join(classificacao["evidencias"]))
    print("\nRevisão de escrita (regras explicáveis):")
    if not escrita["alertas"]:
        print("Nenhum alerta destas regras. Confira se a mensagem corresponde ao código.")
    for alerta in escrita["alertas"]:
        print(f"- {alerta['mensagem']} {alerta['sugestao']}")
    print("\nModelo para preencher; os campos entre colchetes precisam ser informados:")
    print(escrita["modelo_para_preencher"])
    print("\n" + escrita["limite"])


def modo_interativo(modelo):
    print("CommitX — análise de mensagens")
    print("Digite um título; deixe-o vazio para sair. Ctrl+C também encerra.")
    while True:
        try:
            titulo = input("\nTítulo: ").strip()
            if not titulo:
                return
            descricao = input("Descrição (opcional, uma linha): ")
            exibir_analise(analisar_mensagem(modelo, titulo, descricao))
        except ValueError as erro:
            print("Confira a mensagem:", erro)
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrado.")
            return


def criar_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    comandos = parser.add_subparsers(dest="comando")
    analise = comandos.add_parser("analisar", help="Classifica e revisa uma mensagem.")
    analise.add_argument("titulo")
    analise.add_argument("--descricao", default="")
    analise.add_argument("--json", action="store_true", help="Imprime a análise como JSON.")
    interativo = comandos.add_parser("interativo", help="Analisa várias mensagens sem repetir comandos.")
    avaliacao = comandos.add_parser("avaliar", help="Compara modelos por validação cruzada.")
    avaliacao.add_argument("--folds", type=int, default=5)
    avaliacao.add_argument("--saida", type=Path, default=Path("resultados"))
    for comando in [analise, interativo, avaliacao]:
        comando.add_argument("--dados", type=Path, default=BASE_PADRAO, help="CSV rotulado para treinamento.")
    for comando in [analise, interativo]:
        comando.add_argument("--modelo", choices=["misto", "palavras"], default="misto")
    coleta = comandos.add_parser("coletar", help="Exporta commits de um repositório Git local para rotular.")
    coleta.add_argument("repositorio", type=Path)
    coleta.add_argument("--saida", type=Path, required=True)
    coleta.add_argument("--limite", type=int, default=100)

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
    return parser


def main(argv=None):
    parser = criar_parser()
    args = parser.parse_args(argv)
    try:

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
        if args.comando == "coletar":
            quantidade = coletar_git(args.repositorio, args.saida, args.limite)
            print(f"{quantidade} commits exportados para {args.saida}.")
            print("Preencha a coluna categoria após revisar cada mensagem; o prefixo não foi usado como rótulo.")
            return 0
        # Sem argumentos, abre uma conversa curta no terminal usando a base padrão.
        dados = carregar_dados(getattr(args, "dados", BASE_PADRAO))
        if args.comando == "avaliar":
            relatorio = avaliar(dados, folds=args.folds)
            pasta = salvar_relatorios(relatorio, args.saida)
            print(f"Validação cruzada: {relatorio['n_exemplos']} mensagens, {len(relatorio['folds'])} divisões.")
            print(f"{'Modelo':<12} {'Acurácia OOF':>13} {'Macro-F1 OOF':>13}")
            for nome, resultado in relatorio["resultados"].items():
                print(f"{nome:<12} {resultado['acuracia']:>13.3f} {resultado['macro_f1']:>13.3f}")
            print(f"Relatórios em {pasta.resolve()}. Comece por resumo.md e erros.csv.")
            print("Avaliação exploratória: resultados sintéticos não demonstram desempenho real nem medem clareza.")
        else:
            modelo = treinar(dados, tipo=getattr(args, "modelo", "misto"))
            if args.comando == "analisar":
                resultado = analisar_mensagem(modelo, args.titulo, args.descricao)
                if args.json:
                    print(json.dumps(resultado, ensure_ascii=False, indent=2))
                else:
                    exibir_analise(resultado)
            else:
                modo_interativo(modelo)
    except (ValueError, OSError) as erro:
        parser.error(str(erro))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
