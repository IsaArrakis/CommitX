"""Extrai evidências da prévia de um commit Git, em memória."""

from io import StringIO
import re
import tokenize


_HUNK = re.compile(r"^@@ -([0-9]{1,18})(?:,([0-9]{1,18}))? "
                   r"\+([0-9]{1,18})(?:,([0-9]{1,18}))? @@(?: .*)?$")
_SECAO = re.compile(r"(?m)(?=^diff --git )")
_INICIO_HUNK = re.compile(r"(?m)(?=^@@)")
_CAMINHOS = re.compile(r"(?m)^--- (.+)\n\+\+\+ (.+)$")


def _caminho(cabecalho, prefixo):
    nome = cabecalho.removesuffix("\t")
    if nome.startswith('"' + prefixo):
        return '"' + nome[len(prefixo) + 1:]
    return nome.removeprefix(prefixo)


def _arquivo_documentacao(caminho):
    partes = caminho.strip('"').lower().split("/")
    nome = partes[-1]
    return (
        nome in {"readme", "readme.txt"}
        or nome.endswith((".md", ".markdown", ".rst", ".adoc", ".asciidoc"))
        or (nome.endswith(".txt") and any(
            parte in {"doc", "docs", "documentacao", "documentation"} for parte in partes[:-1]
        ))
    )


def _arquivo_teste(caminho):
    partes = caminho.strip('"').lower().split("/")
    nome = partes[-1]
    return (
        any(parte in {"test", "tests", "testes", "__tests__"} for parte in partes[:-1])
        or nome == "conftest.py"
        or nome.startswith("test_")
        or nome.endswith(("_test.py", "_test.go", ".test.js", ".test.ts", ".test.jsx",
                          ".test.tsx", ".spec.js", ".spec.ts", ".spec.jsx", ".spec.tsx"))
    )


def _indicios_por_arquivo(arquivos):
    evidencias = []
    categorias = set()
    for arquivo in arquivos:
        if arquivo["binario"]:
            continue
        sinais = [
            categoria
            for categoria, campo in (("docs", "arquivo_documentacao"), ("test", "arquivo_teste"))
            if arquivo[campo]
        ]
        if sinais:
            categorias.update(sinais)
            evidencias.append({
                "tipo": "caminho",
                "arquivo": arquivo["arquivo"],
                "categorias": sinais,
            })

    categoria = None
    limites = ["A intenção do commit permanece em aberto quando a evidência se limita aos caminhos."]
    misto = bool(evidencias) and len(arquivos) > 1 and (
        len(categorias) > 1 or len(evidencias) != len(arquivos)
    )
    if len(categorias) == 1 and len(evidencias) == len(arquivos):
        categoria = next(iter(categorias))
    elif misto:
        limites.append("A lista inclui sinais diferentes ou arquivos sem indícios reconhecidos.")
    elif evidencias:
        limites.append("O caminho tem convenções de documentação e de testes.")
    else:
        limites.append("A lista de arquivos não oferece indícios suficientes.")

    return {
        "categoria": categoria,
        "estado": "inconclusivo" if categoria is None else "com_indicios",
        "misto": misto,
        "evidencias": evidencias,
        "arquivos_relacionados": [evidencia["arquivo"] for evidencia in evidencias],
        "limites": limites,
    }


def _ler_hunk(cabecalho, linhas):
    """Lê cada lado com sua numeração e distingue falta de linhas de erro de formato."""
    trecho = _HUNK.fullmatch(cabecalho)
    if trecho is None:
        return None, False

    antiga, total_antigo, nova, total_novo = (
        int(valor) if valor is not None else 1 for valor in trecho.groups()
    )
    if (antiga == 0 and total_antigo) or (nova == 0 and total_novo):
        return None, False

    removidas, adicionadas = [], []
    marcador_permitido = False
    for linha in linhas:
        marca = linha[:1]
        if marca == "\\" and marcador_permitido and linha.startswith("\\ "):
            marcador_permitido = False
            continue
        if marca not in (" ", "-", "+"):
            return None, False
        if marca in (" ", "-"):
            removidas.append((antiga + len(removidas), marca == "-", linha[1:]))
        if marca in (" ", "+"):
            adicionadas.append((nova + len(adicionadas), marca == "+", linha[1:]))
        if len(removidas) > total_antigo or len(adicionadas) > total_novo:
            return None, False
        marcador_permitido = True

    completo = len(removidas) == total_antigo and len(adicionadas) == total_novo
    return (removidas, adicionadas), completo


def _sinais_comando(tokens):
    if not tokens or tokens[0].type != tokenize.NAME:
        return
    valores = [token.string for token in tokens]
    comando = valores[0]
    linha = tokens[0].start[0] - 1
    if valores[:2] == ["async", "def"]:
        tokens = tokens[1:]
        comando = "def"

    if comando in ("def", "class") and len(tokens) > 1 and tokens[1].type == tokenize.NAME:
        yield linha, "funcao" if comando == "def" else "classe", tokens[1].string
    elif comando in ("if", "elif", "else"):
        yield linha, "condicao", comando
    elif comando in ("try", "except", "finally", "raise"):
        yield linha, "excecao", comando
    elif comando == "from" and "import" in valores[1:]:
        modulo = "".join(valores[1:valores.index("import")])
        if modulo:
            yield linha, "import", modulo
    elif comando == "import":
        for parte in " ".join(valores[1:]).split(","):
            modulo = parte.partition(" as ")[0].replace(" ", "")
            if modulo:
                yield linha, "import", modulo


def _sinais_python(linhas):
    # Remover a indentação permite tokenizar hunks que começam dentro de um bloco.
    fonte = "".join(texto.lstrip(" \t") + "\n" for _, _, texto in linhas)
    comando = []
    try:
        for token in tokenize.generate_tokens(StringIO(fonte).readline):
            if token.type == tokenize.COMMENT:
                yield token.start[0] - 1, "comentario", None
            elif token.type == tokenize.NEWLINE:
                yield from _sinais_comando(comando)
                comando.clear()
            elif token.type not in (tokenize.NL, tokenize.ENDMARKER):
                comando.append(token)
    except (tokenize.TokenError, SyntaxError):
        # Um hunk pode começar ou terminar no meio de uma expressão ou string.
        return


def _evidencias_lado(arquivo, lado, linhas):
    if _arquivo_teste(arquivo):
        for numero, alterada, _ in linhas:
            if alterada:
                yield {"tipo": "teste", "arquivo": arquivo, "lado": lado, "linha": numero}

    if arquivo.rstrip('"').lower().endswith((".py", ".pyi")):
        for indice, tipo, nome in _sinais_python(linhas):
            numero, alterada, _ = linhas[indice]
            if alterada:
                evidencia = {"tipo": tipo, "arquivo": arquivo, "lado": lado, "linha": numero}
                if nome is not None:
                    evidencia["nome"] = nome
                yield evidencia


def analisar_diff(commit: dict) -> dict:
    """Recebe o retorno de analisar_commit e devolve evidências por lado e linha.

    As contagens totais vêm do leitor. As contagens da prévia e as evidências
    usam apenas linhas visíveis de hunks válidos ou interrompidos pelo corte.
    Os sinais Python são léxicos e dependem do contexto visível em cada hunk.
    Os indícios de documentação e testes usam a lista completa de arquivos.
    """
    arquivos = [
        {**arquivo, "binario": arquivo["adicionadas"] is None and arquivo["removidas"] is None,
         "arquivo_documentacao": _arquivo_documentacao(arquivo["arquivo"]),
         "arquivo_teste": _arquivo_teste(arquivo["arquivo"])}
        for arquivo in commit["arquivos"]
    ]
    truncado = commit["diff_truncado"]
    previa = commit["diff_previa"]
    limitacoes = [{"tipo": "diff_truncado"}] if truncado else []
    if truncado and not previa.endswith("\n"):
        # O leitor corta por caracteres e a última linha pode estar incompleta.
        ultima_quebra = previa.rfind("\n")
        previa = previa[:ultima_quebra + 1]

    evidencias = []
    total_adicionadas = total_removidas = 0
    secoes = _SECAO.split(previa)
    for indice_secao, secao in enumerate(secoes):
        cabecalho, *hunks = _INICIO_HUNK.split(secao)
        caminhos = _CAMINHOS.search(cabecalho)
        anterior = posterior = None
        if caminhos:
            anterior = _caminho(caminhos[1], "a/")
            posterior = _caminho(caminhos[2], "b/")
        for indice_hunk, hunk in enumerate(hunks):
            linhas = hunk.removesuffix("\n").split("\n")
            lados, completo = _ler_hunk(linhas[0], linhas[1:])
            no_corte = (truncado and indice_secao == len(secoes) - 1
                        and indice_hunk == len(hunks) - 1)
            if not caminhos or lados is None or (not completo and not no_corte):
                arquivo = anterior if posterior == "/dev/null" else posterior
                limitacoes.append({"tipo": "hunk_malformado", "arquivo": arquivo})
                continue

            removidas, adicionadas = lados
            total_removidas += sum(alterada for _, alterada, _ in removidas)
            total_adicionadas += sum(alterada for _, alterada, _ in adicionadas)
            evidencias.extend(_evidencias_lado(anterior, "removida", removidas))
            evidencias.extend(_evidencias_lado(posterior, "adicionada", adicionadas))

    if not limitacoes and (total_adicionadas, total_removidas) != (
        commit["linhas_adicionadas"], commit["linhas_removidas"]
    ):
        limitacoes.append({"tipo": "contagens_divergentes"})

    return {
        "versao": 1,
        "estado": "parcial" if limitacoes else "completo",
        "arquivos": arquivos,
        "linhas_adicionadas": commit["linhas_adicionadas"],
        "linhas_removidas": commit["linhas_removidas"],
        "linhas_adicionadas_na_previa": total_adicionadas,
        "linhas_removidas_na_previa": total_removidas,
        "diff_truncado": truncado,
        "evidencias": evidencias,
        "limitacoes": limitacoes,
        "indicios": _indicios_por_arquivo(arquivos),
    }
