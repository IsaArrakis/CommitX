"""Leitura de dados rotulados e coleta local de mensagens do Git."""

import csv
from pathlib import Path
import re
import subprocess
import unicodedata

from .escrita import parse_cabecalho, texto_modelo


CLASSES = ["fix", "feat", "docs", "refactor", "test"]
CAMPOS = ["id", "titulo", "descricao", "categoria", "grupo", "origem"]


def _normalizar(texto):
    """Ignora caixa, acentos e espaços ao procurar exemplos repetidos."""
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def carregar_dados(caminho):
    """Carrega um CSV rotulado; colunas extras, como tipo_declarado, são aceitas.

    Cada grupo deve identificar exemplos relacionados. A coluna ``texto`` contém
    título e descrição preparados para o modelo, sem o prefixo convencional.
    A quantidade mínima de grupos por classe é verificada pela avaliação.
    """
    caminho = Path(caminho)
    try:
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            faltantes = [campo for campo in CAMPOS if campo not in (leitor.fieldnames or [])]
            if faltantes:
                raise ValueError("CSV sem colunas obrigatórias: " + ", ".join(faltantes) + ".")
            linhas = list(leitor)
    except (OSError, UnicodeError, csv.Error) as erro:
        raise ValueError(f"Não foi possível ler o CSV '{caminho}': {erro}") from erro

    if not linhas:
        raise ValueError("A base está vazia. Adicione exemplos rotulados antes do treinamento.")

    ids = set()
    textos = {}
    dados = []
    for numero, linha in enumerate(linhas, start=2):
        if None in linha or any(linha.get(campo) is None for campo in CAMPOS):
            raise ValueError(f"Linha {numero}: quantidade de campos inválida; confira as vírgulas e aspas do CSV.")
        registro = {campo: linha[campo].strip() for campo in CAMPOS}
        for campo in ("id", "titulo", "grupo", "origem"):
            if not registro[campo]:
                raise ValueError(f"Linha {numero}: o campo '{campo}' não pode ficar vazio.")
        if not registro["categoria"]:
            raise ValueError(
                f"Linha {numero}: categoria não preenchida. Rotule as mensagens manualmente antes de treinar; "
                "não copie automaticamente o tipo declarado no título."
            )
        if registro["categoria"] not in CLASSES:
            raise ValueError(f"Linha {numero}: categoria inválida. Use uma destas: {', '.join(CLASSES)}.")
        if registro["id"] in ids:
            raise ValueError(f"Linha {numero}: id repetido '{registro['id']}'. Cada exemplo precisa de um id único.")
        ids.add(registro["id"])
        registro["texto"] = texto_modelo(registro["titulo"], registro["descricao"])
        normalizado = _normalizar(registro["texto"])
        if not normalizado:
            raise ValueError(f"Linha {numero}: a mensagem não tem conteúdo após remover o prefixo.")
        if normalizado in textos:
            raise ValueError(
                f"Linha {numero}: mensagem duplicada da linha {textos[normalizado]}. "
                "Remova a duplicata; prefixos, acentos e espaços não tornam o exemplo diferente."
            )
        textos[normalizado] = numero
        dados.append(registro)

    ausentes = [categoria for categoria in CLASSES if categoria not in {r["categoria"] for r in dados}]
    if ausentes:
        raise ValueError("A base precisa das cinco classes. Faltam exemplos de: " + ", ".join(ausentes) + ".")
    return dados


def _executar_git(repositorio, argumentos):
    """Executa comandos somente de leitura, sem shell e com limite de tempo."""
    try:
        return subprocess.run(
            ["git", "-C", str(repositorio), *argumentos],
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        ).stdout
    except FileNotFoundError as erro:
        raise ValueError("Git não encontrado. Instale o Git e confira se o comando está disponível no terminal.") from erro
    except subprocess.TimeoutExpired as erro:
        raise ValueError("A leitura do Git excedeu 30 segundos. Tente um limite menor de commits.") from erro


def coletar_git(repositorio, saida, limite=100):
    """Exporta mensagens do histórico HEAD, sem merges, para rotulação manual.

    Categoria fica vazia mesmo quando há um tipo declarado no título. Inicialmente
    cada SHA é um grupo: antes de avaliar, agrupe manualmente paráfrases, commits
    relacionados ou repositórios conforme o objetivo da avaliação. A origem usa
    apenas o nome da pasta local; nenhum remote ou credencial é consultado.
    """
    if isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 1000:
        raise ValueError("O limite deve ser um número inteiro entre 1 e 1000.")
    repositorio = Path(repositorio).expanduser().resolve()
    saida = Path(saida).expanduser()
    if not repositorio.is_dir():
        raise ValueError(f"A pasta do repositório não existe: {repositorio}")
    if saida.exists() or saida.is_symlink():
        raise ValueError(f"O arquivo de saída já existe: {saida}. Escolha outro nome para preservar os rótulos.")
    try:
        _executar_git(repositorio, ["rev-parse", "--git-dir"])
    except subprocess.CalledProcessError as erro:
        raise ValueError("A pasta informada não é um repositório Git acessível.") from erro
    try:
        _executar_git(repositorio, ["rev-parse", "--verify", "HEAD"])
    except subprocess.CalledProcessError as erro:
        raise ValueError("O repositório não tem commits acessíveis em HEAD.") from erro
    try:
        historico = _executar_git(
            repositorio,
            ["log", "--no-merges", f"--max-count={limite}", "--encoding=UTF-8", "-z",
             "--format=%H%x00%B", "HEAD", "--"],
        )
    except subprocess.CalledProcessError as erro:
        raise ValueError("Não foi possível ler as mensagens do histórico Git.") from erro

    partes = historico.split("\0")
    if partes and partes[-1] == "":
        partes.pop()
    if not historico or not partes:
        raise ValueError("Nenhum commit sem merge foi encontrado no histórico HEAD.")
    if len(partes) % 2:
        raise ValueError("O histórico Git retornou mensagens em um formato inesperado.")
    registros = []
    for indice in range(0, len(partes), 2):
        sha, mensagem = partes[indice:indice + 2]
        # %B preserva as linhas; %s achataria todo o primeiro parágrafo.
        titulo, _, descricao = mensagem.partition("\n")
        if descricao.startswith("\n"):
            descricao = descricao[1:]  # Separador convencional entre título e corpo.
        cabecalho = parse_cabecalho(titulo) if titulo.strip() else None
        registros.append({
            "id": sha,
            "titulo": titulo,
            "descricao": descricao,
            "categoria": "",
            "grupo": sha,
            "origem": f"git:{repositorio.name}",
            "tipo_declarado": cabecalho["tipo"] if cabecalho else "",
        })
    try:
        saida.parent.mkdir(parents=True, exist_ok=True)
        # O modo 'x' também evita sobrescrita se o arquivo surgir durante a coleta.
        with saida.open("x", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS + ["tipo_declarado"])
            escritor.writeheader()
            escritor.writerows(registros)
    except FileExistsError as erro:
        raise ValueError(f"O arquivo de saída já existe: {saida}. Escolha outro nome para preservar os rótulos.") from erro
    except OSError as erro:
        raise ValueError(f"Não foi possível salvar o CSV: {erro}") from erro
    return len(registros)
