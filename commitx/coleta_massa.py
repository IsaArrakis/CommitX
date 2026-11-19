"""Coletor de commits em massa com SQLite, Git local e CommitPackFT (streaming).

Uso: python -m commitx.coleta_massa --help
"""
import argparse
import csv
import hashlib
from pathlib import Path
import sqlite3
import subprocess

CAMPOS = ["id", "titulo", "descricao", "categoria", "grupo", "origem", "tipo_declarado"]
ESQUEMA = """
CREATE TABLE IF NOT EXISTS commits (
 id TEXT PRIMARY KEY,
 repositorio TEXT NOT NULL,
 sha TEXT NOT NULL,
 titulo TEXT NOT NULL,
 descricao TEXT NOT NULL,
 fonte TEXT NOT NULL,
 linguagem TEXT NOT NULL DEFAULT '',
 licenca TEXT NOT NULL DEFAULT '',
 inserido_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fonte ON commits(fonte);
"""

def abrir_banco(caminho):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(caminho)
    db.executescript(ESQUEMA)
    return db

def dividir_mensagem(mensagem, assunto=""):
    mensagem = (mensagem or "").replace("\r\n", "\n").strip()
    assunto = (assunto or "").strip()
    if mensagem:
        titulo, separador, corpo = mensagem.partition("\n")
        if titulo.strip():
            return titulo.strip(), corpo.strip() if separador else ""
    return assunto, ""

def registrar(db, *, repositorio, sha, mensagem, fonte, assunto="", linguagem="", licenca=""):
    """Deduplica por repositório e SHA; rótulos não são inferidos."""
    repositorio = (repositorio or "").strip()
    sha = (sha or "").strip().lower()
    titulo, descricao = dividir_mensagem(mensagem, assunto)
    if not repositorio or not sha or not titulo:
        return False
    if len(titulo) > 20000 or len(descricao) > 200000:
        return False
    uid = hashlib.sha256((repositorio.casefold() + "\0" + sha).encode()).hexdigest()
    cursor = db.execute(
        "INSERT OR IGNORE INTO commits "
        "(id, repositorio, sha, titulo, descricao, fonte, linguagem, licenca) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, repositorio, sha, titulo, descricao, fonte, linguagem, licenca),
    )
    return cursor.rowcount == 1

def importar_hf(db, *, limite, splits, lote=500, carregador=None):
    """Itera splits do CommitPackFT e grava somente novos commits."""
    if carregador is None:
        try:
            from datasets import load_dataset
        except ImportError as erro:
            raise RuntimeError(
                "Dependência opcional ausente: .venv/bin/python -m pip install datasets"
            ) from erro
        carregador = load_dataset
    novos = 0
    vistos = 0
    for split in splits:
        for linha in carregador("bigcode/commitpackft", split=split, streaming=True):
            vistos += 1
            if registrar(
                db,
                repositorio=str(linha.get("repos") or ""),
                sha=str(linha.get("commit") or ""),
                mensagem=linha.get("message") or linha.get("subject") or "",
                assunto=str(linha.get("subject") or ""),
                fonte="huggingface:bigcode/commitpackft",
                linguagem=str(linha.get("lang") or ""),
                licenca=str(linha.get("license") or ""),
            ):
                novos += 1
                if novos % lote == 0:
                    db.commit()
                    print(f"HF: {novos} novos / {vistos} lidos", flush=True)
                if novos >= limite:
                    db.commit()
                    return novos, vistos
    db.commit()
    return novos, vistos

def ler_git(repositorio, max_por_repo):
    """Lê o histórico completo da mensagem, sem commits de merge."""
    comando = [
        "git", "-C", str(repositorio), "log", "--no-merges", "-z",
        "--format=%H%x00%B", f"--max-count={max_por_repo}", "HEAD", "--",
    ]
    try:
        resultado = subprocess.run(
            comando, check=True, capture_output=True, timeout=120
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as erro:
        raise RuntimeError(f"Falha ao ler Git em '{repositorio}': {erro}") from erro
    partes = resultado.stdout.split(b"\0")
    if partes and partes[-1] == b"":
        partes.pop()
    if len(partes) % 2:
        raise RuntimeError(f"Histórico Git inválido: {repositorio}")
    for pos in range(0, len(partes), 2):
        yield (
            partes[pos].decode("ascii", errors="replace"),
            partes[pos + 1].decode("utf-8", errors="replace"),
        )

def importar_git(db, *, repositorios, limite, max_por_repo=3000, lote=500):
    novos = 0
    vistos = 0
    for repositorio in repositorios:
        pasta = Path(repositorio).expanduser().resolve()
        if not pasta.is_dir():
            raise ValueError(f"Repositório não encontrado: {pasta}")
        for sha, mensagem in ler_git(pasta, max_por_repo):
            vistos += 1
            if registrar(
                db, repositorio=f"git:{pasta}", sha=sha,
                mensagem=mensagem, fonte="git:local",
            ):
                novos += 1
                if novos % lote == 0:
                    db.commit()
                    print(f"Git: {novos} novos / {vistos} lidos", flush=True)
                if novos >= limite:
                    db.commit()
                    return novos, vistos
    db.commit()
    return novos, vistos

def exportar_csv(db, saida):
    """Exporta mensagens não rotuladas; nunca sobrescreve um CSV revisado."""
    from .escrita import parse_cabecalho
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with saida.open("x", encoding="utf-8", newline="") as arq:
        escritor = csv.DictWriter(arq, fieldnames=CAMPOS)
        escritor.writeheader()
        for uid, titulo, descricao, repositorio, sha, fonte in db.execute(
            "SELECT id, titulo, descricao, repositorio, sha, fonte FROM commits ORDER BY id"
        ):
            cabecalho = parse_cabecalho(titulo)
            escritor.writerow({
                "id": uid,
                "titulo": titulo,
                "descricao": descricao,
                "categoria": "",
                "grupo": f"{repositorio}:{sha}",
                "origem": f"{fonte}:{repositorio}",
                "tipo_declarado": cabecalho["tipo"] if cabecalho else "",
            })
            total += 1
    return total

def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--banco", type=Path, default=Path("resultados/coleta/commits.sqlite3")
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    hf = sub.add_parser("hf", help="Lê CommitPackFT via streaming.")
    hf.add_argument("--limite", type=int, default=70000)
    hf.add_argument(
        "--splits", nargs="+", default=["python", "javascript", "java", "markdown"]
    )
    git = sub.add_parser("git", help="Importa vários Git locais.")
    git.add_argument("--repos", type=Path, required=True)
    git.add_argument("--limite", type=int, default=30000)
    git.add_argument("--max-por-repo", type=int, default=3000)
    exp = sub.add_parser("exportar", help="Exporta CSV sem rótulos.")
    exp.add_argument("--saida", type=Path, required=True)
    sub.add_parser("status", help="Conta commits únicos por fonte.")
    return parser.parse_args()

def main():
    args = argumentos()
    if hasattr(args, "limite") and args.limite < 1:
        raise SystemExit("--limite precisa ser positivo")
    if hasattr(args, "max_por_repo") and args.max_por_repo < 1:
        raise SystemExit("--max-por-repo precisa ser positivo")
    with abrir_banco(args.banco) as db:
        if args.comando == "hf":
            novos, vistos = importar_hf(
                db, limite=args.limite, splits=args.splits
            )
            print(f"HF concluído: {novos} novos / {vistos} linhas lidas")
        elif args.comando == "git":
            pastas = [
                l.strip() for l in args.repos.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.lstrip().startswith("#")
            ]
            if not pastas:
                raise SystemExit("Nenhum caminho encontrado no arquivo --repos")
            novos, vistos = importar_git(
                db, repositorios=pastas,
                limite=args.limite, max_por_repo=args.max_por_repo,
            )
            print(f"Git concluído: {novos} novos / {vistos} linhas lidas")
        elif args.comando == "exportar":
            quantidade = exportar_csv(db, args.saida)
            print(f"Exportados {quantidade} commits para {args.saida} (sem rótulos)")
        elif args.comando == "status":
            for fonte, n in db.execute(
                "SELECT fonte, COUNT(*) FROM commits GROUP BY fonte ORDER BY fonte"
            ):
                print(f"{fonte}: {n}")
            total = db.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
            print(f"TOTAL: {total} commits únicos")

if __name__ == "__main__":
    main()
