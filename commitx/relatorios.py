"""Exportação legível e reproduzível da avaliação, sem dependências extras."""

import csv
import json
from pathlib import Path


def salvar_relatorios(relatorio, pasta):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "relatorio.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    modelos = list(relatorio["resultados"])
    campos = ["id", "titulo", "descricao", "categoria", "grupo", "origem"]
    campos += [f"previsao_{nome}" for nome in modelos] + ["acertou_misto"]
    linhas = []
    for previsao in relatorio["previsoes"]:
        linha = {chave: previsao.get(chave, "") for chave in campos[:6]}
        linha.update({f"previsao_{nome}": previsao["por_modelo"][nome] for nome in modelos})
        linha["acertou_misto"] = previsao["por_modelo"]["misto"] == previsao["categoria"]
        linhas.append(linha)
    for arquivo, registros in [
        ("previsoes.csv", linhas),
        ("erros.csv", [linha for linha in linhas if not linha["acertou_misto"]]),
    ]:
        with (pasta / arquivo).open("w", encoding="utf-8", newline="") as destino:
            escritor = csv.DictWriter(destino, fieldnames=campos)
            escritor.writeheader()
            escritor.writerows(registros)
    classes = relatorio["classes"]
    with (pasta / "matriz_confusao.csv").open("w", encoding="utf-8", newline="") as destino:
        escritor = csv.writer(destino)
        escritor.writerow(["real / prevista", *classes])
        for classe, valores in zip(classes, relatorio["resultados"]["misto"]["matriz_confusao"]):
            escritor.writerow([classe, *valores])
    texto = [
        "# Avaliação do CommitX", "",
        f"Mensagens: {relatorio['n_exemplos']}. Divisões: {len(relatorio['folds'])}.", "",
        "Cada mensagem foi prevista uma vez por um modelo que não a usou no treino. "
        "As três alternativas usam as mesmas divisões.", "",
        "| Modelo | Acurácia OOF | Macro-F1 OOF | Desvio do F1 entre divisões |",
        "| --- | ---: | ---: | ---: |",
    ]
    for nome, resultado in relatorio["resultados"].items():
        texto.append(
            f"| {nome} | {resultado['acuracia']:.3f} | {resultado['macro_f1']:.3f} "
            f"| {resultado['desvio_macro_f1']:.3f} |"
        )
    texto += [
        "", "OOF (*out of fold*) reúne as previsões das divisões de teste. "
        "O macro-F1 OOF é calculado sobre essas previsões reunidas. "
        "O desvio descreve a variação entre divisões; não é um intervalo de confiança.", "",
        "## Como ler os arquivos", "",
        "- `erros.csv`: erros do modelo misto, com texto, rótulo e previsões para revisão.",
        "- `previsoes.csv`: todas as mensagens e previsões dos três modelos.",
        "- `matriz_confusao.csv`: modelo misto; linhas reais, colunas previstas.",
        "- `relatorio.json`: métricas por classe, IDs das divisões e configuração do experimento.",
        "", "## Limites", "",
        "Avaliação exploratória, sem teste externo independente. Dados sintéticos não "
        "demonstram desempenho em repositórios reais. Nenhuma dessas métricas mede clareza. "
        "Revisar os erros é parte do desenvolvimento; qualquer ajuste motivado por eles "
        "deve ser validado posteriormente em dados independentes.", "",
        "Origens da base:", "",
    ]
    texto += [f"- {origem}: {quantidade}" for origem, quantidade in relatorio["origens"].items()]
    texto.append("")
    (pasta / "resumo.md").write_text("\n".join(texto), encoding="utf-8")
    return pasta
