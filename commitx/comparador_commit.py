"""Compara a previsão textual da V12 com indícios do diff."""

from copy import deepcopy


def comparar_commit(classificacao_v12: dict, analise_diff: dict, *,
                    versao: str = "V12", trecho: str = "prévia") -> dict:
    """Recebe os retornos de analisar_modelo e analisar_diff."""
    categoria_textual = classificacao_v12.get("categoria_sugerida")
    caminhos = analise_diff.get("indicios", {})
    codigo = analise_diff.get("indicios_codigo", {})
    evidencias_caminhos = caminhos.get("evidencias", [])
    evidencias_codigo = codigo.get("evidencias", [])
    categorias = {categoria for evidencia in evidencias_caminhos
                  for categoria in evidencia["categorias"]}
    categorias.update(evidencia["categoria"] for evidencia in evidencias_codigo)

    avisos = [
        *classificacao_v12.get("avisos", []),
        "A comparação é indicativa. A intenção do commit e os efeitos em execução exigem revisão.",
    ]
    if evidencias_caminhos:
        avisos.extend(caminhos.get("limites", []))
    if evidencias_codigo:
        avisos.append(f"Os sinais de implementação dependem dos trechos Python analisáveis na {trecho}.")

    truncado = analise_diff.get("diff_truncado") or codigo.get("diff_truncado")
    previa_parcial = analise_diff.get("estado") == "parcial"
    if truncado:
        avisos.append(f"A {trecho} do diff foi truncada e pode omitir alterações relevantes.")
    elif previa_parcial:
        avisos.append("A leitura do diff tem cobertura parcial.")
    codigo_insuficiente = evidencias_codigo and codigo.get("previa_insuficiente")
    if codigo_insuficiente and not (truncado or previa_parcial):
        avisos.append(f"A {trecho} é insuficiente para avaliar os indícios de implementação.")

    status = "inconclusivo"
    if truncado or previa_parcial or codigo_insuficiente:
        explicacao = f"A {trecho} do diff é insuficiente para concluir a comparação."
    elif categoria_textual is None:
        explicacao = f"A {versao} se absteve da previsão textual."
    elif not categorias:
        explicacao = "O diff não forneceu indícios de categoria suficientes."
    elif len(categorias) > 1 or caminhos.get("misto"):
        explicacao = "O diff reúne alterações com sinais mistos ou ambíguos."
    else:
        categoria_diff = next(iter(categorias))
        if categoria_diff == categoria_textual:
            status = "compativel"
            explicacao = f"A previsão textual e os indícios do diff apontam para {categoria_diff}."
        else:
            status = "possivel_divergencia"
            explicacao = f"A previsão textual aponta para {categoria_textual} e o diff sugere {categoria_diff}."

    return {
        "status": status,
        "categoria_textual": categoria_textual,
        "categorias_codigo": sorted(categorias),
        "explicacao": explicacao,
        "evidencias": deepcopy([*evidencias_caminhos, *evidencias_codigo]),
        "avisos": list(dict.fromkeys(avisos)),
    }
