"""Revisão de escrita por regras, separada da classificação por aprendizado de máquina."""

import re
import unicodedata


CABECALHO = re.compile(
    r"^(?P<tipo>[A-Za-z][A-Za-z0-9_-]*)"
    r"(?:\((?P<escopo>[^()\r\n]+)\))?"
    r"(?P<quebra>!)?:[ \t]+(?P<resumo>\S[^\r\n]*)$"
)
# Para o modelo, remove também prefixos sem o espaço recomendado após ':'.
PREFIXO = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\([^()\r\n]+\))?!?:[ \t]*")

TERMOS_GENERICOS = {
    "bug", "bugs", "erro", "erros", "problema", "problemas", "ajuste", "ajustes",
    "melhoria", "melhorias", "coisa", "coisas", "algo", "mudanca", "mudancas",
    "atualizacao", "atualizacoes", "correcao", "correcoes",
}
# Esses termos, sozinhos, não explicam qual comportamento ou objeto mudou.
COMPLEMENTOS_GENERICOS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "da", "das",
    "do", "dos", "em", "na", "nas", "no", "nos", "e", "para", "por",
    "ao", "aos", "com", "sem", "que", "se", "algum", "alguma", "alguns",
    "algumas", "pequeno", "pequenos", "pequena", "pequenas", "geral", "gerais",
    "arrumar", "corrigir", "resolver", "ajustar", "melhorar", "atualizar",
    "alterar", "fazer", "feito", "feita", "feitos", "feitas", "corrigido",
    "corrigida", "corrigidos", "corrigidas", "painel", "admin", "administrador",
    "administrativo", "sistema", "tela", "pagina", "codigo", "projeto", "site",
    "app", "aplicacao", "modulo", "area", "funcao",
}


def _validar_titulo(titulo):
    if not isinstance(titulo, str) or not titulo.strip():
        raise ValueError("Informe um título para analisar.")
    return titulo.strip()


def parse_cabecalho(titulo):
    """Reconhece apenas o cabeçalho; corpo e rodapés não são validados."""
    encontrado = CABECALHO.fullmatch(_validar_titulo(titulo))
    if not encontrado:
        return None
    return {
        "tipo": encontrado.group("tipo").lower(),
        "escopo": encontrado.group("escopo"),
        "resumo": encontrado.group("resumo").strip(),
        "quebra": bool(encontrado.group("quebra")),
    }


def texto_modelo(titulo, descricao=""):
    """Remove o tipo e o escopo iniciais; preserva o conteúdo, inclusive negações."""
    resumo = PREFIXO.sub("", _validar_titulo(titulo))
    return (resumo + "\n" + descricao.strip()).strip()


def _titulo_generico(resumo):
    # Esta regra encontra apenas combinações simples de expressões genéricas.
    # Não tenta determinar automaticamente o significado de qualquer frase.
    normalizado = "".join(
        letra for letra in unicodedata.normalize("NFD", resumo.lower())
        if unicodedata.category(letra) != "Mn"
    )
    palavras = set(re.findall(r"\b\w+\b", normalizado))
    tem_termo_generico = bool(palavras & TERMOS_GENERICOS)
    complemento = palavras - TERMOS_GENERICOS - COMPLEMENTOS_GENERICOS
    return tem_termo_generico and not complemento


def revisar_escrita(titulo, descricao=""):
    """Retorna recomendações explicáveis; não atribui uma nota de clareza."""
    titulo = _validar_titulo(titulo)
    cabecalho = parse_cabecalho(titulo)
    resumo = PREFIXO.sub("", titulo).strip()
    if not resumo:
        raise ValueError("Descreva a mudança após o prefixo.")

    alertas = []
    if not cabecalho:
        alertas.append({
            "codigo": "formato_convencional",
            "mensagem": "O cabeçalho convencional não foi reconhecido. Isso não indica falta de clareza.",
            "sugestao": "Se adotar Conventional Commits, use tipo: resumo ou tipo(escopo): resumo. O escopo é opcional.",
        })
    if _titulo_generico(resumo):
        sugestao = "Nomeie a mudança específica: qual comportamento ou item foi alterado e, quando relevante, em que situação."
        if not descricao.strip():
            sugestao += " Se o título não bastar, acrescente o motivo e o resultado esperado no corpo."
        alertas.append({
            "codigo": "titulo_vago",
            "mensagem": "O título combina uma expressão genérica com pouca informação específica.",
            "sugestao": sugestao,
        })

    tipo = cabecalho["tipo"] if cabecalho else None
    escopo = cabecalho["escopo"] if cabecalho else None
    inicio = tipo or "[tipo]"
    if escopo:
        inicio += f"({escopo})"
    if cabecalho and cabecalho["quebra"]:
        inicio += "!"

    return {
        "tipo_declarado": tipo,
        "escopo_declarado": escopo,
        "cabecalho_reconhecido": cabecalho is not None,
        "alertas": alertas,
        "modelo_para_preencher": (
            inicio + ": [ação e mudança específica]\n\n"
            "[Se necessário: motivo, comportamento anterior e resultado esperado.]\n"
            "[Detalhe relevante da implementação, se houver.]"
        ),
        "limite": (
            "Regras simples em português, sem pontuação ou modelo treinado de clareza. "
            "Ausência de alertas não comprova clareza. O corpo é opcional para mudanças "
            "bem explicadas no título. O cabeçalho não valida a especificação completa "
            "nem confirma que a mensagem corresponde ao código."
        ),
    }
