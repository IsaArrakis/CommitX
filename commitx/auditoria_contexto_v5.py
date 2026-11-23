"""Auditoria de contexto V5 para erros da validacao do CommitX.

Leitura SOMENTE dos 9 erros da validacao V4; não treina nem muda rotulos.
Para commits de Git local, verifica SHA e titulo original e lista arquivos
e estatisticas. Nunca faz clone, fetch, checkout, download ou consulta remota.
Para commits externos, marca como NAO_VERIFICADO, sem inventar um diff.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

from .leitor_diff import analisar_commit

DEFAULT_ENTRADA = Path("resultados/validacao-hibrido-v4-01/erros_hibrido.csv")
DEFAULT_SAIDA = Path("resultados/auditoria-contexto-v5-01")
SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")
CAMINHOS_DOCS = (".md", ".rst", ".adoc", ".txt")
ARQUIVOS_TEST = ("test_", "_test.", "/tests/", "/test/", ".spec.", ".test.")


def _nomes_locais(valor, raiz):
    """Retorna apenas repositórios declarados em git: e sob a raiz autorizada."""
    raiz = Path(raiz).expanduser().resolve()
    paths = set()
    for item in str(valor).split(","):
        item = item.strip()
        if not item.startswith("git:"):
            continue
        candidato = Path(item[4:]).expanduser().resolve()
        if candidato != raiz and candidato.is_relative_to(raiz) and candidato.is_dir():
            paths.add(candidato)
    return sorted(paths)


def _pistas_nomes(arquivos):
    """Caracteristicas observaveis de paths; nunca substituem rotulo humano."""
    nomes = [r["arquivo"] for r in arquivos if r.get("arquivo")]
    if not nomes:
        return ["sem_arquivos_identificados"]
    pistas = []
    lower = [p.lower() for p in nomes]
    documentais = [any(p.endswith(ext) for ext in CAMINHOS_DOCS)
                    or "/docs/" in p or p.startswith("docs/") for p in lower]
    testes = [any(t in "/" + p for t in ARQUIVOS_TEST)
              or p.startswith("tests/") or p.startswith("test/") for p in lower]
    if all(documentais):
        pistas.append("todos_arquivos_documentacao")
    if any(documentais):
        pistas.append("inclui_documentacao")
    if all(testes):
        pistas.append("todos_arquivos_testes")
    if any(testes):
        pistas.append("inclui_testes")
    if not any(documentais) and not any(testes):
        pistas.append("sem_indicador_simples_de_docs_ou_testes")
    if len(nomes) > 10:
        pistas.append("muitos_arquivos_modificados")
    return pistas


def auditar_erro(registro, *, raiz):
    titulo = (registro.get("titulo") or "").strip()
    identificador = (registro.get("id") or "").strip()
    saida = {
        "id": identificador,
        "titulo": titulo,
        "categoria_rotulada": registro.get("real") or "",
        "previsao_hibrido": registro.get("hibrido") or "",
        "previsao_svm": registro.get("svm_titulo") or "",
        "repositorio_origem": registro.get("repositorio") or "",
        "situacao": "",
        "causa_nao_verificado": "",
        "repositorio_git_verificado": "",
        "sha_git_verificado": "",
        "numero_arquivos": "",
        "linhas_adicionadas": "",
        "linhas_removidas": "",
        "nomes_arquivos": "",
        "pistas_arquivos": "",
    }
    if not SHA_RE.fullmatch(identificador):
        saida["situacao"] = "nao_verificado"
        saida["causa_nao_verificado"] = "id_nao_e_sha40"
        return saida
    locais = _nomes_locais(registro.get("repositorio"), raiz)
    if not locais:
        saida["situacao"] = "nao_verificado"
        saida["causa_nao_verificado"] = "sem_repositorio_git_local_acessivel"
        return saida
    problemas = []
    for local in locais:
        try:
            dados = analisar_commit(local, identificador, max_chars=100)
        except (ValueError, OSError) as e:
            problemas.append(type(e).__name__ + ": " + str(e)[:140])
            continue
        # SHA e titulo devem corresponder ao mesmo commit, nunca assumir que ID valido basta.
        if dados["commit"].lower() != identificador.lower():
            problemas.append("sha_diverge")
            continue
        if dados["titulo"].strip() != titulo:
            problemas.append("titulo_diverge_do_git")
            continue
        arquivos = dados["arquivos"]
        saida.update({
            "situacao": "git_local_verificado",
            "repositorio_git_verificado": str(local),
            "sha_git_verificado": dados["commit"],
            "numero_arquivos": dados["quantidade_arquivos"],
            "linhas_adicionadas": dados["linhas_adicionadas"],
            "linhas_removidas": dados["linhas_removidas"],
            "nomes_arquivos": " | ".join(x["arquivo"] for x in arquivos[:30]),
            "pistas_arquivos": " | ".join(_pistas_nomes(arquivos)),
        })
        return saida
    saida["situacao"] = "nao_verificado"
    saida["causa_nao_verificado"] = " | ".join(problemas[:4]) or "git_nao_encontrou_commit"
    return saida


def executar(entrada=DEFAULT_ENTRADA, saida=DEFAULT_SAIDA, raiz=Path("repos")):
    entrada, saida = Path(entrada), Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError("A pasta de saida ja existe: " + str(saida))
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        campos = {"id", "titulo", "real", "hibrido", "svm_titulo", "repositorio"}
        if not campos.issubset(reader.fieldnames or []):
            raise ValueError("CSV de erros sem as colunas esperadas")
        registros = list(reader)
    if not registros:
        raise ValueError("CSV de erros vazio")
    if len(set(r["id"] for r in registros)) != len(registros):
        raise ValueError("CSV de erros com IDs repetidos")
    analises = [auditar_erro(r, raiz=raiz) for r in registros]
    contagem = Counter(r["situacao"] for r in analises)
    relatorio = {
        "protocolo": "V5-auditoria-local-dos-erros-de-validacao-sem-retreino",
        "total_erros": len(analises),
        "git_local_verificado": contagem["git_local_verificado"],
        "nao_verificado": contagem["nao_verificado"],
        "erros_por_categoria_rotulada": dict(Counter(r["real"] for r in registros)),
        "restricoes": [
            "Somente casos de validacao previamente usados na avaliacao; nao avaliar ou mexer no teste reservado",
            "Git diff e caminhos apenas quando SHA e titulo correspondem ao Git local",
            "Sem downloads, sem consultas a repositorios remotos e sem checkout",
            "Pistas de arquivos nao sao categoria prevista nem validam o rotulo original",
            "Nao altera qualquer dado original, banco, modelo ou rotulo",
            "Validacao ja conhecida nao deve virar gabarito de ajustes de hiperparametros",
        ],
    }
    saida.mkdir(parents=True, exist_ok=False)
    with (saida / "auditoria.csv").open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(analises[0]))
        writer.writeheader()
        writer.writerows(analises)
    (saida / "resumo.json").write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    linhas = [
        "# Auditoria V5 de contexto dos erros da validacao", "",
        f"- Erros analisados: **{len(analises)}**",
        f"- Com SHA e titulo conferidos em Git local: **{contagem['git_local_verificado']}**",
        f"- Sem diff confirmado: **{contagem['nao_verificado']}**",
        "", "## Por caso", "",
    ]
    for i, r in enumerate(analises, 1):
        linhas += [
            f"{i}. **{r['titulo']}**",
            f"   - Rotulo: {r['categoria_rotulada']} | Hibrido: {r['previsao_hibrido']}",
            f"   - Git: {r['situacao']} — {r['causa_nao_verificado'] or r['repositorio_git_verificado']}",
            f"   - Arquivos: {r['nomes_arquivos'] or '(nao verificados)'}",
            f"   - Pistas: {r['pistas_arquivos'] or '(nao verificadas)'}",
        ]
    linhas += ["", "## Restrições", ""] + ["- " + x for x in relatorio["restricoes"]]
    (saida / "relatorio.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return relatorio


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, default=DEFAULT_ENTRADA)
    p.add_argument("--saida", type=Path, default=DEFAULT_SAIDA)
    p.add_argument("--raiz-repos", type=Path, default=Path("repos"))
    a = p.parse_args(argv)
    try:
        r = executar(a.entrada, a.saida, a.raiz_repos)
    except (OSError, ValueError, csv.Error) as e:
        p.error(str(e))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print("Relatorio:", a.saida / "relatorio.md")


if __name__ == "__main__":
    main()
