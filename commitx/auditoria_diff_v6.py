"""Auditoria em lote dos conflitos V6 usando apenas Git local, sem rotular."""
import argparse
import csv
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

DEFAULT_IN = Path("resultados/diagnostico-v6-01/amostra_para_auditoria.csv")
DEFAULT_OUT = Path("resultados/auditoria-diff-v6-01")
MAX_PREVIEW = 1800


def git(repo, *args):
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=25, check=False
        )
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def repos_disponiveis(base):
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and git(p, "rev-parse", "--show-toplevel"))


def procurar(sha, repos):
    # Só aceita SHA completo, evitando correspondências acidentais e injeção.
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        return None, "id_nao_e_sha40"
    for repo in repos:
        resolved = git(repo, "rev-parse", "--verify", sha + "^{commit}")
        if resolved and resolved.strip().lower() == sha.lower():
            return repo, "encontrado"
    return None, "nao_encontrado_nos_clones"


def examinar(repo, sha):
    pais = (git(repo, "rev-list", "--parents", "-n", "1", sha) or "").split()
    if not pais:
        return None
    if len(pais) > 1:
        a = git(repo, "diff", "--no-ext-diff", "--no-textconv",
                "--no-renames", "--numstat", pais[1], sha, "--")
        nomes = git(repo, "diff", "--no-ext-diff", "--no-textconv",
                    "--no-renames", "--name-only", pais[1], sha, "--")
        patch = git(repo, "diff", "--no-ext-diff", "--no-textconv",
                    "--no-renames", "--no-color", "--unified=1",
                    pais[1], sha, "--")
    else:
        a = git(repo, "show", "--format=", "--numstat", "--no-renames", sha)
        nomes = git(repo, "show", "--format=", "--name-only", "--no-renames", sha)
        patch = git(repo, "show", "--format=", "--no-ext-diff",
                    "--no-textconv", "--no-renames", "--unified=1", sha)
    if nomes is None or a is None or patch is None:
        return None
    files = [s for s in nomes.splitlines() if s.strip()]
    ad, rem = 0, 0
    for line in a.splitlines():
        fields = line.split("\t")
        if len(fields) >= 3:
            if fields[0].isdigit(): ad += int(fields[0])
            if fields[1].isdigit(): rem += int(fields[1])
    return files, ad, rem, patch[:MAX_PREVIEW], len(patch) > MAX_PREVIEW


def analisar(entrada=DEFAULT_IN, saida=DEFAULT_OUT, repos_root=Path("repos")):
    with entrada.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"id", "titulo", "categoria_svm", "categoria_ollama"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV sem colunas essenciais: " + ", ".join(sorted(required)))
        rows = list(reader)
    repos = repos_disponiveis(repos_root)
    saida.mkdir(parents=True, exist_ok=True)
    audit = []
    counts = Counter()
    for r in rows:
        sha = r["id"].strip()
        repo, status = procurar(sha, repos)
        record = {k:r.get(k,"") for k in ("id","repositorio","titulo",
                                           "categoria_svm","categoria_ollama")}
        record.update({"git_status":status, "repo_local":str(repo or ""),
                       "qtd_arquivos":"", "linhas_adicionadas":"",
                       "linhas_removidas":"", "arquivos":"",
                       "patch_previa":"", "patch_truncado":"",
                       "revisao_humana":"", "justificativa":""})
        if repo:
            dados = examinar(repo, sha)
            if dados:
                files, added, removed, preview, truncated = dados
                record.update({"qtd_arquivos":len(files),
                               "linhas_adicionadas":added, "linhas_removidas":removed,
                               "arquivos":" | ".join(files),
                               "patch_previa":preview,
                               "patch_truncado":str(truncated)})
            else:
                record["git_status"] = "diff_indisponivel"
        counts[record["git_status"]] += 1
        audit.append(record)
    with (saida / "auditoria.csv").open("w",encoding="utf-8",newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(audit[0]) if audit else [
            "id","repositorio","titulo","categoria_svm","categoria_ollama",
            "git_status","repo_local","qtd_arquivos","linhas_adicionadas",
            "linhas_removidas","arquivos","patch_previa","patch_truncado",
            "revisao_humana","justificativa"])
        writer.writeheader()
        writer.writerows(audit)
    summary = {"total":len(audit), "repositorios_locais":len(repos),
               "status":dict(counts),
               "observacao":"Sem classificacao automatica ou alteracao de rotulos; patch e apenas previa."}
    (saida/"resumo.json").write_text(json.dumps(summary,indent=2,
        ensure_ascii=False)+"\n",encoding="utf-8")
    report = ["# Auditoria de diffs V6","",
              f"- Casos: {len(audit)}", f"- Clones consultados: {len(repos)}",
              f"- Git encontrados: {counts['encontrado']}",
              f"- Nao encontrados: {counts['nao_encontrado_nos_clones']}",
              "", "O CSV possui previsualizacoes truncadas. Nao usar como gabarito automatico.",
              "Antes de compartilhar, revisar mensagens, nomes de arquivos e diffs.",
              "", "## Casos", ""]
    for i,r in enumerate(audit,1):
        report.append(f"{i}. {r['id'][:12]} | {r['git_status']} | "
                      f"SVM={r['categoria_svm']} / Ollama={r['categoria_ollama']} | "
                      f"{r['titulo'].replace(chr(10),' ')[:95]}")
    (saida/"relatorio.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada",type=Path,default=DEFAULT_IN)
    p.add_argument("--saida",type=Path,default=DEFAULT_OUT)
    p.add_argument("--repos",type=Path,default=Path("repos"))
    a=p.parse_args()
    try:
        print(json.dumps(analisar(a.entrada,a.saida,a.repos),indent=2,ensure_ascii=False))
    except (ValueError,OSError) as e:
        p.error(str(e))


if __name__=="__main__":
    main()
