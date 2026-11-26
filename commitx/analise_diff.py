"""Extrai evidências da prévia de um commit Git, em memória."""

import ast
from collections import defaultdict
from io import StringIO
import re
from textwrap import dedent
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


_FUNCOES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _fragmento(linhas):
    fonte = dedent("\n".join(texto for _, _, texto in linhas))
    return ast.parse(fonte)


def _marcas(arvore):
    """Associa cada sinal à sintaxe relevante, sem posições ou comentários."""
    for no in ast.walk(arvore):
        if isinstance(no, (*_FUNCOES, ast.ClassDef)):
            yield "feat", "declaracao", no.name, no
            for decorador in no.decorator_list:
                if (isinstance(decorador, ast.Call) and isinstance(decorador.func, ast.Attribute)
                        and decorador.func.attr in {"route", "get", "post", "put", "patch", "delete"}
                        and decorador.args and isinstance(decorador.args[0], ast.Constant)
                        and isinstance(decorador.args[0].value, str)
                        and decorador.args[0].value.startswith("/")):
                    yield "feat", "endpoint", ast.dump(decorador), decorador
        elif isinstance(no, ast.ExceptHandler):
            yield "fix", "tratamento_excecao", ast.dump(no.type) if no.type else "*", no
        elif isinstance(no, ast.Assert):
            yield "fix", "validacao", ast.dump(no.test), no.test
        elif isinstance(no, ast.If):
            yield "fix", "condicao_alterada", ast.dump(no.test), no.test
            for expr in ast.walk(no.test):
                if isinstance(expr, ast.Compare) and any(
                    isinstance(item, ast.Constant) and item.value is None
                    for item in [expr.left, *expr.comparators]
                ):
                    yield "fix", "verificacao_nulo", ast.dump(expr), expr


def _padroes_hunk(arquivo, lados, novo, evidencias, funcoes):
    removidas, adicionadas = lados
    antes, depois = map(_fragmento, lados)
    anteriores = {(tipo, chave): no for _, tipo, chave, no in _marcas(antes)}
    condicoes = [no for (tipo, _), no in anteriores.items()
                 if tipo == "condicao_alterada" and removidas[no.lineno - 1][1]]
    atuais = list(_marcas(depois))
    for categoria, tipo, chave, no in atuais:
        numero, alterada, _ = adicionadas[no.lineno - 1]
        if not alterada or (tipo, chave) in anteriores:
            continue
        evidencia = {"categoria": categoria, "tipo": tipo, "arquivo": arquivo, "linha": numero}
        if tipo == "condicao_alterada":
            if len(condicoes) != 1 or sum(t == tipo for _, t, _, n in atuais
                                         if adicionadas[n.lineno - 1][1]) != 1:
                continue
            evidencia["linha_anterior"] = removidas[condicoes[0].lineno - 1][0]
        if tipo == "declaracao":
            evidencia["nome"] = chave
        evidencias.append(evidencia)
    if novo and depois.body:
        evidencias.append({"categoria": "feat", "tipo": "arquivo_novo", "arquivo": arquivo,
                           "linha": adicionadas[depois.body[0].lineno - 1][0]})

    for arvore, linhas, lado in ((antes, removidas, "removida"), (depois, adicionadas, "adicionada")):
        for no in ast.walk(arvore):
            if isinstance(no, _FUNCOES):
                funcoes[lado].append((arquivo, no, linhas))


def _refatoracoes(funcoes):
    # Exigir a mesma estrutura observável e registrar origem e destino.
    antigas_por_nome = defaultdict(list)
    antigas_por_arquivo = defaultdict(list)
    atuais_por_nome = defaultdict(list)
    for arquivo, no, linhas in funcoes["removida"]:
        antigas_por_nome[no.name].append((arquivo, no, linhas))
        antigas_por_arquivo[arquivo].append((no, linhas))
    for arquivo, no, linhas in funcoes["adicionada"]:
        atuais_por_nome[arquivo, no.name].append((no, linhas))

    for destino, nova, linhas in funcoes["adicionada"]:
        if not linhas[nova.lineno - 1][1]:
            continue
        local = {"categoria": "refactor", "arquivo": destino,
                 "linha": linhas[nova.lineno - 1][0], "nome": nova.name}
        for origem, antiga, anteriores in antigas_por_nome[nova.name]:
            if (origem != destino and anteriores[antiga.lineno - 1][1]
                    and ast.dump(antiga) == ast.dump(nova)):
                yield {**local, "tipo": "movimentacao_funcao", "arquivo_anterior": origem,
                       "linha_anterior": anteriores[antiga.lineno - 1][0]}

        if len(nova.body) != 1 or not isinstance(nova.body[0], ast.Return):
            continue
        retorno = nova.body[0]
        if retorno.value is None or isinstance(retorno.value, (ast.Constant, ast.Name)):
            continue
        for antiga, anteriores in antigas_por_arquivo[destino]:
            if antiga.name == nova.name:
                continue
            for chamadora, atuais in atuais_por_nome[destino, antiga.name]:
                for velho, atual in zip(antiga.body, chamadora.body):
                    if (isinstance(atual, ast.Return) and isinstance(atual.value, ast.Call)
                            and isinstance(atual.value.func, ast.Name)
                            and atual.value.func.id == nova.name and atuais[atual.lineno - 1][1]
                            and ast.dump(velho) == ast.dump(retorno)):
                        yield {**local, "tipo": "extracao_funcao", "arquivo_anterior": destino,
                               "linha_anterior": anteriores[velho.lineno - 1][0]}


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
    padroes = []
    funcoes = {"removida": [], "adicionada": []}
    fragmento_incompleto = False
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

            caminho = anterior if posterior == "/dev/null" else posterior
            if caminho.rstrip('"').endswith((".py", ".pyi")) and not _arquivo_teste(caminho):
                try:
                    _padroes_hunk(caminho, lados, anterior == "/dev/null", padroes, funcoes)
                except (SyntaxError, ValueError, RecursionError):
                    fragmento_incompleto = True

    if not limitacoes and (total_adicionadas, total_removidas) != (
        commit["linhas_adicionadas"], commit["linhas_removidas"]
    ):
        limitacoes.append({"tipo": "contagens_divergentes"})

    limites_codigo = [item["tipo"] for item in limitacoes]
    if fragmento_incompleto:
        limites_codigo.append("fragmento_python_incompleto")
    if not limites_codigo:
        try:
            padroes.extend(_refatoracoes(funcoes))
        except RecursionError:
            limites_codigo.append("estrutura_profunda")
    candidatas = sorted({item["categoria"] for item in padroes})
    return {
        "indicios_codigo": {
            "estado": "com_indicios" if len(candidatas) == 1 and not limites_codigo else "inconclusivo",
            "candidatas": candidatas,
            "evidencias": padroes,
            "diff_truncado": truncado,
            "previa_insuficiente": bool(limites_codigo) or not padroes,
            "limites": limites_codigo + ["A equivalência funcional exige revisão do código completo."],
        },
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
