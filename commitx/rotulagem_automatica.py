"""Triagem automática em lote de commits, sem fabricar rótulos humanos.

Uso:
python -m commitx.rotulagem_automatica
python -m commitx.rotulagem_automatica --entrada resultados/preparacao-inicial/commits_preparados.csv --saida resultados/triagem/todos.csv --resumo resultados/triagem/todos.json
"""
import argparse
from collections import Counter
import csv
import itertools
import json
from pathlib import Path
import sqlite3

from .dados import carregar_dados
from .escrita import parse_cabecalho, revisar_escrita, texto_modelo
from .modelo import treinar
from .sugestoes import BASE_DIDATICA

ENTRADA = Path("resultados/preparacao-inicial/amostra_para_rotular.csv")
SAIDA = Path("resultados/triagem/amostra_sugerida.csv")
RESUMO = Path("resultados/triagem/resumo_amostra.json")
BANCO_HUMANO = Path("resultados/rotulagem/avaliacoes.sqlite3")
TIPOS_VALIDOS = ("fix", "feat", "docs", "refactor", "test")
CAMPOS = [
    "id", "titulo", "descricao", "origem", "repositorio", "grupo", "particao",
    "tipo_declarado", "categoria_sugerida", "fonte_categoria",
    "categoria_prevista_modelo", "divergencia_prefixo_modelo",
    "clareza_sugerida", "fonte_clareza", "categoria_humana", "clareza_humana",
    "status", "prioridade_revisao",
]


def rotulos_humanos(caminho):
    """Lê avaliações em modo somente leitura, sem abrir/criar o banco se ausente."""
    caminho = Path(caminho)
    if not caminho.is_file():
        return {}
    con = sqlite3.connect(f"file:{caminho.resolve().as_posix()}?mode=ro", uri=True)
    try:
        return {
            uid: (categoria, clareza)
            for uid, categoria, clareza in con.execute(
                "SELECT id, categoria, clareza FROM avaliacoes"
            )
        }
    finally:
        con.close()


def ler_lote(leitor, tamanho):
    return list(itertools.islice(leitor, tamanho))


def processar_lote(linhas, modelo, humanos):
    """Não promove hipótese do modelo/prefixo a rótulo de verdade."""
    textos = [texto_modelo(r["titulo"], r.get("descricao") or "") for r in linhas]
    previsoes = modelo.predict(textos) if linhas else []
    for original, previsto in zip(linhas, previsoes):
        titulo, descricao = original["titulo"], original.get("descricao") or ""
        cabecalho = parse_cabecalho(titulo)
        declarado = cabecalho["tipo"] if cabecalho else ""
        categoria_modelo = str(previsto)
        if declarado in TIPOS_VALIDOS:
            categoria = declarado
            fonte = "prefixo_nao_verificado"
        elif declarado:
            categoria = ""
            fonte = "abstencao_prefixo_nao_convencional"
        else:
            categoria = categoria_modelo
            fonte = "modelo_didatico_50_sinteticos"
        divergencia = bool(
            declarado in TIPOS_VALIDOS and declarado != categoria_modelo
        )
        revisao = revisar_escrita(titulo, descricao)
        generico = any(a["codigo"] == "titulo_vago" for a in revisao["alertas"])
        if generico and not descricao.strip():
            clareza = "vago"
            origem_clareza = "regra_generico_sem_corpo"
        else:
            clareza = ""
            origem_clareza = "sem_modelo_validado"
        categoria_humana, clareza_humana = humanos.get(original["id"], ("", ""))
        completo = bool(categoria_humana and clareza_humana)
        prioridade = (
            "ja_revisado" if completo
            else "alta" if divergencia or not categoria or generico
            else "normal"
        )
        yield {
            "id": original["id"],
            "titulo": titulo,
            "descricao": descricao,
            "origem": original.get("origem", ""),
            "repositorio": original.get("repositorio", ""),
            "grupo": original.get("grupo", ""),
            "particao": original.get("particao", ""),
            "tipo_declarado": declarado,
            "categoria_sugerida": categoria,
            "fonte_categoria": fonte,
            "categoria_prevista_modelo": categoria_modelo,
            "divergencia_prefixo_modelo": "sim" if divergencia else "nao",
            "clareza_sugerida": clareza,
            "fonte_clareza": origem_clareza,
            "categoria_humana": categoria_humana,
            "clareza_humana": clareza_humana,
            "status": "revisado_humano" if completo else "pendente_revisao",
            "prioridade_revisao": prioridade,
        }


def gerar(entrada, saida, resumo, banco_humano=BANCO_HUMANO,
          lote=256, limite=0, modelo=None):
    entrada, saida, resumo = map(Path, (entrada, saida, resumo))
    if lote < 1 or limite < 0:
        raise ValueError("--lote deve ser positivo e --limite não pode ser negativo")
    if not entrada.is_file():
        raise ValueError(f"Arquivo de entrada não encontrado: {entrada}")
    caminhos = [entrada.resolve(), saida.resolve(), resumo.resolve()]
    if len(set(caminhos)) != len(caminhos):
        raise ValueError("Entrada, CSV e resumo precisam ser arquivos diferentes")
    if saida.exists() or resumo.exists():
        raise FileExistsError("Os arquivos de saída já existem. Use outros nomes para preservá-los")
    if modelo is None:
        modelo = treinar(carregar_dados(BASE_DIDATICA), tipo="misto")
    humanos = rotulos_humanos(banco_humano)
    saida.parent.mkdir(parents=True, exist_ok=True)
    resumo.parent.mkdir(parents=True, exist_ok=True)
    contagem = Counter()
    with entrada.open("r", encoding="utf-8-sig", newline="") as origem:
        leitor = csv.DictReader(origem)
        requisitos = {"id", "titulo", "descricao"}
        if not requisitos.issubset(leitor.fieldnames or []):
            raise ValueError("Arquivo de entrada sem colunas: " +
                             ", ".join(sorted(requisitos - set(leitor.fieldnames or []))))
        with saida.open("x", encoding="utf-8", newline="") as destino:
            escritor = csv.DictWriter(destino, fieldnames=CAMPOS)
            escritor.writeheader()
            while True:
                quantidade = lote if not limite else min(lote, limite - contagem["processados"])
                if quantidade < 1:
                    break
                linhas = ler_lote(leitor, quantidade)
                if not linhas:
                    break
                for registro in linhas:
                    if not (registro.get("id") or "").strip() or not (registro.get("titulo") or "").strip():
                        raise ValueError("Registro com ID ou título vazio")
                for resultado in processar_lote(linhas, modelo, humanos):
                    escritor.writerow(resultado)
                    contagem["processados"] += 1
                    contagem["revisados_humanos"] += (resultado["status"] == "revisado_humano")
                    contagem["prioridade_alta"] += (resultado["prioridade_revisao"] == "alta")
                    contagem["discordancias"] += (resultado["divergencia_prefixo_modelo"] == "sim")
                    contagem["sem_categoria_sugerida"] += (not resultado["categoria_sugerida"])
                    contagem["sem_clareza_sugerida"] += (not resultado["clareza_sugerida"])
                    contagem["categoria_" + (resultado["categoria_sugerida"] or "sem_previsao")] += 1
                if contagem["processados"] % 5000 < len(linhas):
                    print(f"Triagem: {contagem['processados']} mensagens processadas", flush=True)
    relatorio = {
        "estatisticas": dict(contagem),
        "entrada": str(entrada),
        "csv_sugestoes": str(saida),
        "modelo_categoria": "TF-IDF + Regressão Logística (50 exemplos sintéticos)",
        "modelo_clareza": "Somente regra de título genérico; demais sem previsão",
        "uso": (
            "Hipóteses para triagem, não rótulos humanos, nem dados automaticamente "
            "prontos para treino supervisionado. Não foram conferidos diffs."
        ),
        "aviso": (
            "Validação independente é necessária antes de treinar com pseudo-rótulos. "
            "A categoria prevista pelo modelo pode estar errada mesmo quando há prefixo."
        ),
    }
    with resumo.open("x", encoding="utf-8") as arq:
        json.dump(relatorio, arq, ensure_ascii=False, indent=2)
        arq.write("\n")
    return relatorio


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--resumo", type=Path, default=RESUMO)
    parser.add_argument("--banco-humano", type=Path, default=BANCO_HUMANO)
    parser.add_argument("--lote", type=int, default=256)
    parser.add_argument("--limite", type=int, default=0,
                        help="0 = todos os registros da entrada")
    args = parser.parse_args(argv)
    try:
        relatorio = gerar(
            args.entrada, args.saida, args.resumo,
            banco_humano=args.banco_humano, lote=args.lote, limite=args.limite
        )
    except (OSError, ValueError, sqlite3.Error, csv.Error) as erro:
        parser.error(str(erro))
    e = relatorio["estatisticas"]
    print(f"Total: {e.get('processados', 0)}")
    print(f"Revisados por humanos preservados: {e.get('revisados_humanos', 0)}")
    print(f"Prioridade alta para revisão: {e.get('prioridade_alta', 0)}")
    print(f"Discordâncias prefixo/modelo: {e.get('discordancias', 0)}")
    print(f"CSV: {args.saida}")
    print(f"Relatório: {args.resumo}")


if __name__ == "__main__":
    main()
