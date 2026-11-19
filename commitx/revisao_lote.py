"""Revisão humana rápida de várias mensagens na mesma tela.

Uso:
  python -m commitx.revisao_lote --amostra resultados/amostras/rodada1.csv
  python -m commitx.rotulagem --amostra resultados/amostras/rodada1.csv lote
"""
import argparse
import re

from .rotulagem import (
    BANCO, FONTE, OPCOES_CATEGORIA, OPCOES_CLAREZA,
    abrir_banco, avaliados, ler_amostra, registrar, status,
)


def _limpar(texto):
    """Evita quebra de layout e códigos de controle vindos de commits externos."""
    return " ".join(
        "".join(c if c.isprintable() else " " for c in str(texto or "")).split()
    )


def _resumo(texto, limite=115):
    texto = _limpar(texto)
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


def _eh_reservado(linha):
    return linha.get("particao", "") in ("validacao", "teste")


def _opcoes():
    categorias = " | ".join(f"{k}={v}" for k, v in OPCOES_CATEGORIA.items())
    clarezas = " | ".join(f"{k}={v}" for k, v in OPCOES_CLAREZA.items())
    return categorias, clarezas


def exibir_pagina(pagina, sugestoes, total, *, imprimir=print, revisados=0):
    imprimir(f"\n{'=' * 72}")
    imprimir(f"REVISÃO EM LOTE — {len(pagina)} mensagens / {total} na amostra; "
             f"{revisados} revisadas nesta sessão")
    imprimir("=" * 72)
    for numero, linha in enumerate(pagina, 1):
        sugestao = sugestoes.get(numero, {})
        categoria = sugestao.get("categoria") or "—"
        clareza = sugestao.get("clareza") or "—"
        imprimir(f"[{numero}] {_resumo(linha['titulo'])}")
        corpo = _resumo(linha.get("descricao") or "", 155)
        if corpo:
            imprimir(f"    Corpo: {corpo}")
        imprimir(f"    Sugestões: categoria={categoria}; clareza={clareza}"
                 + ("  [avaliação cega]" if _eh_reservado(linha) else ""))
        if sugestao.get("aviso_categoria"):
            imprimir("    ATENÇÃO: prefixo e modelo didático discordam.")
    cat, cla = _opcoes()
    imprimir("\nCATEGORIA: " + cat)
    imprimir("CLAREZA: " + cla)
    imprimir("Digite: 1=,3;2=4,2  (aceitar categoria sugerida da 1 e "
             "marcar clareza 3; corrigir ambas na 2)")
    imprimir("Ou 1=ok para aceitar as DUAS sugestões, se ambas existirem.")
    imprimir("d2 = detalhes da 2; p = próxima página; q = sair. "
             "Nada é salvo sem sua resposta.")


def detalhes(linha, sugestao, numero, *, imprimir=print):
    imprimir(f"\n--- DETALHES [{numero}] ---")
    imprimir("ID: " + _limpar(linha["id"]))
    imprimir("Título: " + _limpar(linha["titulo"]))
    imprimir("Descrição: " + (_limpar(linha.get("descricao")) or "(sem descrição)"))
    imprimir("Origem: " + _limpar(linha.get("origem")))
    imprimir("Repositório: " + _limpar(linha.get("repositorio")))
    imprimir("Partição: " + _limpar(linha.get("particao")))
    if sugestao.get("origem_categoria"):
        imprimir("Origem da categoria: " + sugestao["origem_categoria"])
    if sugestao.get("origem_clareza"):
        imprimir("Origem da clareza: " + sugestao["origem_clareza"])
    imprimir("Sugestões são hipóteses, nunca gabarito.")


def interpretar_respostas(texto, pagina, sugestoes):
    """Valida a linha inteira antes de qualquer gravação.

    O formato N=,3 aceita a categoria sugerida, mas exige clareza humana.
    N=ok só é permitido quando ambas as sugestões existem.
    """
    itens = [parte.strip() for parte in texto.strip().split(";")]
    if not itens or not all(itens):
        raise ValueError("Use N=categoria,clareza;N=categoria,clareza.")
    respostas = []
    usados = set()
    for item in itens:
        match = re.fullmatch(r"(\d+)\s*=\s*(.*)", item)
        if not match:
            raise ValueError(f"Formato inválido: {item!r}. Exemplo: 1=,3;2=4,2")
        indice = int(match.group(1))
        if not 1 <= indice <= len(pagina):
            raise ValueError(f"Número fora da página: {indice}")
        if indice in usados:
            raise ValueError(f"Mensagem {indice} repetida nesta resposta")
        usados.add(indice)
        proposta = sugestoes.get(indice, {})
        valor = match.group(2).strip().lower()
        if valor == "ok":
            categoria = proposta.get("categoria")
            clareza = proposta.get("clareza")
        else:
            partes = valor.split(",")
            if len(partes) != 2:
                raise ValueError(
                    f"Entrada {indice}: informe categoria e clareza (ex.: {indice}=1,3)"
                )
            valor_categoria, valor_clareza = [p.strip() for p in partes]
            categoria = (
                OPCOES_CATEGORIA.get(valor_categoria) if valor_categoria
                else proposta.get("categoria")
            )
            clareza = (
                OPCOES_CLAREZA.get(valor_clareza) if valor_clareza
                else proposta.get("clareza")
            )
        if categoria not in OPCOES_CATEGORIA.values():
            raise ValueError(
                f"Mensagem {indice}: categoria ausente ou inválida. "
                "Informe o número; não há sugestão para confirmar."
            )
        if clareza not in OPCOES_CLAREZA.values():
            raise ValueError(
                f"Mensagem {indice}: clareza ausente ou inválida. "
                "Informe o número; não há sugestão para confirmar."
            )
        respostas.append((indice, pagina[indice - 1]["id"], categoria, clareza))
    return respostas


def revisar_em_lote(amostra, db, *, tamanho=5, limite=20,
                   sugestor=None, entrada=input, imprimir=print):
    """Cada seleção humana é salva individualmente e sessões podem ser retomadas."""
    if not 1 <= tamanho <= 20:
        raise ValueError("--tamanho deve estar entre 1 e 20")
    if limite < 1:
        raise ValueError("--limite precisa ser positivo")

    previamente = set(avaliados(db))
    pendentes = [r for r in amostra if r["id"] not in previamente]
    cursor = 0
    salvos = 0
    while cursor < len(pendentes) and salvos < limite:
        pagina = pendentes[cursor:cursor + min(tamanho, limite - salvos)]
        if not pagina:
            break
        propostas = {}
        for numero, linha in enumerate(pagina, 1):
            if sugestor is not None and not _eh_reservado(linha):
                try:
                    propostas[numero] = sugestor.analisar(
                        linha["titulo"], linha.get("descricao") or ""
                    )
                except (ValueError, TypeError):
                    propostas[numero] = {}
            else:
                propostas[numero] = {}
        ativos = set(range(1, len(pagina) + 1))
        while ativos and salvos < limite:
            exibir_pagina(
                [pagina[i - 1] for i in sorted(ativos)],
                # Renderizamos os números originais abaixo, sem renumerar comandos.
                {j: propostas[i] for j, i in enumerate(sorted(ativos), 1)},
                len(amostra), imprimir=imprimir, revisados=salvos,
            )
            mapa = sorted(ativos)
            propostas_ativas = {j: propostas[i] for j, i in enumerate(mapa, 1)}
            pagina_ativa = [pagina[i - 1] for i in mapa]
            try:
                comando = entrada("\nLote> ").strip()
            except (EOFError, KeyboardInterrupt):
                imprimir("\nSessão interrompida. Avaliações anteriores preservadas.")
                return salvos
            if comando.lower() == "q":
                return salvos
            if comando.lower() == "p":
                break
            detalhes_match = re.fullmatch(r"d\s*(\d+)", comando, re.IGNORECASE)
            if detalhes_match:
                numero = int(detalhes_match.group(1))
                if numero not in range(1, len(pagina_ativa) + 1):
                    imprimir("Número inválido para esta página.")
                    continue
                detalhes(pagina_ativa[numero - 1], propostas_ativas[numero],
                         numero, imprimir=imprimir)
                continue
            try:
                respostas = interpretar_respostas(
                    comando, pagina_ativa, propostas_ativas
                )
                if len(respostas) > limite - salvos:
                    raise ValueError(
                        "Essa linha excede --limite. Escolha menos mensagens."
                    )
            except ValueError as erro:
                imprimir("Entrada rejeitada, nenhum rótulo salvo: " + str(erro))
                continue
            for numero, uid, categoria, clareza in respostas:
                registrar(db, uid, categoria, clareza)
                salvos += 1
                ativos.remove(mapa[numero - 1])
                imprimir(f"Salvo: [{numero}] {categoria} / {clareza}")
        cursor += len(pagina)
    return salvos


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amostra", default=FONTE, type=str)
    parser.add_argument("--banco", default=BANCO, type=str)
    parser.add_argument("--tamanho", type=int, default=5)
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--sem-sugestoes", action="store_true")
    args = parser.parse_args(argv)
    try:
        amostra = ler_amostra(args.amostra)
        with abrir_banco(args.banco) as db:
            sugestor = None
            if not args.sem_sugestoes:
                elegiveis = [r for r in amostra if not _eh_reservado(r)]
                if elegiveis:
                    from .sugestoes import Sugestor
                    sugestor = Sugestor(elegiveis, db)
            salvos = revisar_em_lote(
                amostra, db, tamanho=args.tamanho, limite=args.limite,
                sugestor=sugestor
            )
            resumo = status(amostra, db)
        print(f"\nNesta sessão: {salvos} avaliações confirmadas.")
        print(f"Na amostra: {resumo['avaliados']}/{resumo['total']} revisadas.")
        print("Seus rótulos humanos permanecem no banco SQLite.")
    except (OSError, ValueError) as erro:
        parser.error(str(erro))


if __name__ == "__main__":
    main()
