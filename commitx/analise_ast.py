"""Comparação estática dos registros em memória de ler_versoes_git()."""

import ast
from collections import defaultdict, deque
from io import StringIO
import tokenize


_FUNCOES = (ast.FunctionDef, ast.AsyncFunctionDef)
_DECLARACOES = (*_FUNCOES, ast.ClassDef)
_RESSALVA = "Indício estrutural. Escopo, resolução de nomes e comportamento podem mudar."


class _Limite(Exception):
    pass


def _arvore(texto, max_bytes, max_profundidade):
    if len(texto) > max_bytes or len(texto.encode("utf-8")) > max_bytes:
        raise _Limite("limite_bytes")
    # Protege também o parser, antes de existir uma AST cuja altura medir.
    tokens_linha = 0
    for token in tokenize.generate_tokens(StringIO(texto).readline):
        if token.type == tokenize.NEWLINE:
            tokens_linha = 0
        elif token.type not in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT):
            tokens_linha += 1
            if tokens_linha > 1024:
                raise _Limite("limite_complexidade")
    arvore = ast.parse(texto)
    pilha = [(arvore, 1)]
    while pilha:
        no, altura = pilha.pop()
        # ast.dump usa repr() para inteiros. Evita expansão decimal excessiva.
        if isinstance(no, ast.Constant) and type(no.value) is int and no.value.bit_length() > 12000:
            raise _Limite("limite_complexidade")
        if altura > max_profundidade:
            raise _Limite("limite_profundidade")
        pilha.extend((filho, altura + 1) for filho in ast.iter_child_nodes(no))
    return arvore


def _forma(no):
    return ast.dump(no, include_attributes=False) if no is not None else None


def _formas(nos):
    return tuple(map(_forma, nos))


def _escopos(arvore):
    escopos = {"": arvore}

    def visitar(no, escopo):
        if isinstance(no, _DECLARACOES):
            escopo = f"{escopo}.{no.name}" if escopo else no.name
            if escopo in escopos:
                raise _Limite("declaracoes_homonimas")
            escopos[escopo] = no
        for filho in ast.iter_child_nodes(no):
            visitar(filho, escopo)

    visitar(arvore, "")
    return escopos


def _local(caminho, escopo, no):
    return {"arquivo": caminho, "escopo": escopo or "<modulo>", "linha": no.lineno}


def _evento(tipo, antes=None, depois=None, **detalhes):
    return dict(tipo=tipo, anterior=antes, posterior=depois, **detalhes)


def _assinatura(no):
    genericos = _formas(getattr(no, "type_params", []))
    if isinstance(no, ast.ClassDef):
        return genericos, _formas(no.bases), _formas(no.keywords)
    return type(no).__name__, genericos, _forma(no.args), _forma(no.returns)


def _observacoes(raiz):
    grupos = defaultdict(list)

    def visitar(no):
        if isinstance(no, _DECLARACOES):
            return
        if isinstance(no, (ast.If, ast.While, ast.IfExp)):
            grupos["condicao", type(no).__name__].append((_forma(no.test), no.test))
        if isinstance(no, ast.match_case) and no.guard:
            grupos["condicao", "match"].append((_forma(no.guard), no.guard))
        if isinstance(no, ast.comprehension):
            for teste in no.ifs:
                grupos["condicao", "comprehension"].append((_forma(teste), teste))
        if isinstance(no, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            for handler in no.handlers:
                grupos["tratamento_excecao", type(no).__name__].append((_forma(handler), handler))
        for filho in ast.iter_child_nodes(no):
            visitar(filho)

    for instrucao in raiz.body:
        visitar(instrucao)
    return grupos


def _sobras(antes, depois):
    indices = defaultdict(deque)
    for indice, (forma, _) in enumerate(depois):
        indices[forma].append(indice)
    iguais, removidos = set(), []
    for forma, no in antes:
        if indices[forma]:
            iguais.add(indices[forma].popleft())
        else:
            removidos.append(no)
    return removidos, [no for i, (_, no) in enumerate(depois) if i not in iguais]


def _comparar_escopo(caminho, nome, a, b):
    def local(no):
        return _local(caminho, nome, no)

    if nome:
        if _assinatura(a) != _assinatura(b):
            yield _evento("assinatura_modificada", local(a), local(b))
        if _formas(a.decorator_list) != _formas(b.decorator_list):
            yield _evento("decoradores_modificados", local(a), local(b))
    if ast.get_docstring(a, clean=False) != ast.get_docstring(b, clean=False):
        yield _evento("docstring_alterada",
                      local(a.body[0]) if ast.get_docstring(a, clean=False) is not None else None,
                      local(b.body[0]) if ast.get_docstring(b, clean=False) is not None else None)
    antigos, novos = _observacoes(a), _observacoes(b)
    for chave in sorted(antigos.keys() | novos.keys()):
        tipo, construcao = chave
        removidos, adicionados = _sobras(antigos[chave], novos[chave])
        # Só pareia condições na mesma posição quando as demais coincidem em ordem.
        if len(removidos) == len(adicionados) == 1:
            divergencias = sum(x[0] != y[0] for x, y in zip(antigos[chave], novos[chave]))
            if divergencias == 1:
                alteracao = "condicao_modificada" if tipo == "condicao" else "tratamento_excecao_modificado"
                yield _evento(alteracao, local(removidos[0]), local(adicionados[0]),
                              construcao=construcao)
                continue
        for no in removidos:
            yield _evento(tipo + ("_removida" if tipo == "condicao" else "_removido"), local(no))
        for no in adicionados:
            yield _evento(tipo + ("_adicionada" if tipo == "condicao" else "_adicionado"),
                          depois=local(no))


def _extracao(caminho, nome, a, b, novas):
    """Um bloco contíguo virou uma chamada direta a uma auxiliar do mesmo módulo."""
    antigos, novos = _formas(a.body), _formas(b.body)
    inicio = 0
    while inicio < min(len(antigos), len(novos)) and antigos[inicio] == novos[inicio]:
        inicio += 1
    fim_a, fim_b = len(antigos), len(novos)
    while min(fim_a, fim_b) > inicio and antigos[fim_a-1] == novos[fim_b-1]:
        fim_a -= 1
        fim_b -= 1
    if fim_b - inicio != 1 or fim_a - inicio < 2:
        return
    substituto = b.body[inicio]
    if not isinstance(substituto, (ast.Return, ast.Expr)):
        return
    chamada = substituto.value
    if not isinstance(chamada, ast.Call) or not isinstance(chamada.func, ast.Name):
        return
    auxiliar = novas.get((caminho, chamada.func.id))
    if type(auxiliar) is not ast.FunctionDef or auxiliar.decorator_list:
        return
    params = auxiliar.args
    if params.vararg or params.kwarg or params.kwonlyargs or chamada.keywords:
        return
    if not all(isinstance(arg, ast.Name) for arg in chamada.args):
        return
    if [arg.id for arg in chamada.args] != [arg.arg for arg in (*params.posonlyargs, *params.args)]:
        return
    if isinstance(substituto, ast.Return) != isinstance(a.body[fim_a-1], ast.Return):
        return
    if _formas(auxiliar.body) == antigos[inicio:fim_a]:
        return _evento("possivel_extracao", _local(caminho, nome, a.body[inicio]),
                       _local(caminho, auxiliar.name, auxiliar), linha_chamada=substituto.lineno,
                       limitacao=_RESSALVA)


def _movimentos(declaracoes):
    grupos = defaultdict(list)
    for (caminho, nome), no in declaracoes.items():
        if "." not in nome and isinstance(no, _FUNCOES) and len(no.body) >= 2:
            grupos[_forma(no)].append(_local(caminho, nome, no))
    return grupos


def analisar_ast(versoes, *, max_bytes=262144, max_profundidade=64):
    """Compara lados integrais, limitando bytes por versão e profundidade AST (1–128)."""
    if type(max_bytes) is not int or max_bytes < 0 or type(max_profundidade) is not int or not 1 <= max_profundidade <= 128:
        raise ValueError("Limites AST inválidos.")
    resultado = {k: versoes[k] for k in ("commit", "comparado_com", "cobertura")}
    limites = list(versoes["limitacoes"])
    fatos, arquivos = [], []
    resultado.update(limitacoes=limites, arquivos=arquivos, evidencias=fatos)
    novas, removidas = {}, {}
    for registro in versoes["arquivos"]:
        caminho = registro["caminho"]
        cobertura = registro["cobertura"]
        lados, problemas = [], []
        for lado in ("anterior", "posterior"):
            versao = registro[lado]
            motivo, linha = versao["motivo"], None
            ausente = (registro["status"], lado) in (("adicionado", "anterior"), ("removido", "posterior"))
            if ausente and motivo == "nao_aplicavel":
                lados.append({"": ast.Module(body=[], type_ignores=[])})
                continue
            if motivo is None and isinstance(versao["conteudo"], str):
                try:
                    lados.append(_escopos(_arvore(versao["conteudo"], max_bytes, max_profundidade)))
                    continue
                except (SyntaxError, tokenize.TokenError) as erro:
                    motivo, linha = "erro_sintaxe", getattr(erro, "lineno", None)
                    if isinstance(erro, tokenize.TokenError) and len(erro.args) > 1:
                        linha = erro.args[1][0]
                except ValueError:
                    motivo = "erro_sintaxe"
                except _Limite as erro:
                    motivo = str(erro)
                except RecursionError:
                    motivo = "limite_profundidade"
            problemas.append(dict(lado=lado, motivo=motivo or "conteudo_indisponivel", linha=linha))
        if problemas:
            if any(p["motivo"] == "erro_sintaxe" for p in problemas):
                cobertura = "erro_sintaxe"
            else:
                cobertura = "parcial" if lados else "indisponivel"
        arquivos.append(dict(caminho=caminho, cobertura=cobertura, limitacoes=problemas))
        if cobertura != "completa":
            continue
        antes, depois = lados
        if _forma(antes[""]) == _forma(depois[""]):
            continue
        inicio = len(fatos)
        alteradas = []
        for nome in sorted(antes.keys() | depois.keys()):
            a, b = antes.get(nome), depois.get(nome)
            if a and b and isinstance(a, ast.ClassDef) == isinstance(b, ast.ClassDef):
                observados = list(_comparar_escopo(caminho, nome, a, b))
                if not observados and isinstance(a, _FUNCOES) and _formas(a.body) != _formas(b.body):
                    observados.append(_evento("corpo_modificado", _local(caminho, nome, a),
                                              _local(caminho, nome, b)))
                fatos.extend(observados)
                if nome and "." not in nome and isinstance(a, _FUNCOES):
                    alteradas.append((nome, a, b))
                continue
            if a:
                tipo = "classe_removida" if isinstance(a, ast.ClassDef) else "funcao_removida"
                fatos.append(_evento(tipo, _local(caminho, nome, a)))
                removidas[caminho, nome] = a
            if b:
                tipo = "classe_adicionada" if isinstance(b, ast.ClassDef) else "funcao_adicionada"
                fatos.append(_evento(tipo, depois=_local(caminho, nome, b)))
                novas[caminho, nome] = b
        for nome, a, b in alteradas:
            indicio = _extracao(caminho, nome, a, b, novas)
            if indicio:
                fatos.append(indicio)
        if len(fatos) == inicio:
            # Localiza uma mudança fora dos padrões específicos (p.ex. uma atribuição).
            a, b = antes[""].body, depois[""].body
            i = next((i for i, (x, y) in enumerate(zip(a, b)) if _forma(x) != _forma(y)), min(len(a), len(b)))
            fatos.append(_evento("estrutura_alterada", _local(caminho, "", a[i]) if i < len(a) else None,
                                 _local(caminho, "", b[i]) if i < len(b) else None))
    origens, destinos = _movimentos(removidas), _movimentos(novas)
    for forma, locais in origens.items():
        candidatos = destinos.get(forma, [])
        if len(locais) == len(candidatos) == 1 and locais[0]["arquivo"] != candidatos[0]["arquivo"]:
            fatos.append(_evento("possivel_movimentacao", locais[0], candidatos[0], limitacao=_RESSALVA))
    estados = {arquivo["cobertura"] for arquivo in arquivos}
    if estados - {"completa"} and resultado["cobertura"] != "indisponivel":
        if len(estados) == 1 and versoes["cobertura"] == "completa":
            resultado["cobertura"] = next(iter(estados))
        else:
            resultado["cobertura"] = "parcial"
    return resultado
