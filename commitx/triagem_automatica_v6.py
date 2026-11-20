"""CommitX V6: triagem automatica local, SEM fabricar gabarito.

Usa os rotulos assistidos de treino da V5 para montar uma SVM provisoria,
classifica commits ainda nao rotulados da particao TREINO e consulta um modelo
Ollama (localhost) em um conjunto pequeno e balanceado por repositorio.

Os resultados sao PALPITES, nao "rotulos humanos". Nao toca no banco V5,
na validacao, no teste reservado, nos repositorios Git nem em dados antigos.

Uso: python -m commitx.triagem_automatica_v6 --quantidade-ollama 60
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .revisao_git_v5 import BANCO, ENTRADA, PLANO, CATEGORIAS, CLAREZAS, abrir

SAIDA = Path("resultados/triagem-automatica-v6-01")
CATEGORIAS_TEXTO = ", ".join(CATEGORIAS)
CLAREZAS_TEXTO = ", ".join(CLAREZAS)
PROMPT_VERSAO = "v6-locais-titulo-corpo-paths-01"
BANCO_NOVO = "palpites_v6.sqlite3"

SCHEMA_OLLAMA = {
    "type": "object",
    "properties": {
        "categoria": {"type": "string", "enum": list(CATEGORIAS)},
        "clareza": {"type": "string", "enum": list(CLAREZAS)},
        "duvida": {"type": "boolean"},
        "motivo": {"type": "string"},
    },
    "required": ["categoria", "clareza", "duvida", "motivo"],
    "additionalProperties": False,
}


class OllamaIndisponivel(ValueError):
    """Falha de conexao com Ollama: interromper apenas a consulta remota."""




def _texto_linha(r):
    """Mesmo tratamento para inferencia e treinamento; prefixo nao vira etiqueta."""
    titulo = re.sub(r"^(fix|feat|docs|refactor|test)(?:\([^)]+\))?!?:\s*", "", r["titulo"], flags=re.I)
    # Evita inferir classe a partir de prefixo de mensagem e evita repetir paths imensos.
    nomes = [Path(s.strip()).name for s in r.get("arquivos", "").split("|") if s.strip()]
    return " ".join([titulo, r.get("descricao", "")[:300], " ".join(nomes[:18])])[:1800]


def _rotulos_anteriores(rows, dados, banco):
    ids = {r["id"]: r for r in rows}
    with sqlite3.connect(banco) as con:
        encontrados = con.execute("SELECT id, categoria FROM avaliacoes").fetchall()
    rotulos = {}
    for uid, cat in encontrados:
        r = ids.get(uid)
        if r is None:
            raise ValueError("Banco V5 contem id nao presente no CSV atual")
        if dados["repositorios"][r["repositorio"]] != "treino":
            raise ValueError("Banco V5 contem rotulo fora do treino; bloqueado")
        if cat not in CATEGORIAS:
            raise ValueError("Categoria V5 desconhecida: " + str(cat))
        rotulos[uid] = cat
    return rotulos


def _treinar_svm(rows, rotulos):
    if len(rotulos) < 20 or len(set(rotulos.values())) < 2:
        raise ValueError("Treino V5 insuficiente para SVM (20 exemplos, 2 classes)")
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_pipeline
        from sklearn.svm import LinearSVC
    except ImportError as ex:
        raise ValueError("Instale scikit-learn no ambiente virtual") from ex
    treino = [r for r in rows if r["id"] in rotulos]
    x = [_texto_linha(r) for r in treino]
    y = [rotulos[r["id"]] for r in treino]
    if not any(x):
        raise ValueError("Textos vazios no treinamento")
    pipe = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=24000),
        LinearSVC(class_weight="balanced", random_state=42),
    )
    pipe.fit(x, y)
    return pipe


def _avaliar_margem(modelo, rows):
    if not rows:
        return []
    x = [_texto_linha(r) for r in rows]
    previsoes = modelo.predict(x)
    margens = modelo.decision_function(x)
    saida = []
    for i, r in enumerate(rows):
        vetor = margens[i]
        if hasattr(vetor, "__len__"):
            ordenado = sorted((float(p) for p in vetor), reverse=True)
            margem = ordenado[0] - ordenado[1] if len(ordenado) >= 2 else 0.0
        else:
            margem = abs(float(vetor)) * 2  # caso binario
        saida.append({"id": r["id"], "categoria_svm": str(previsoes[i]),
                      "margem_svm": round(margem, 5)})
    return saida


def _selecionar_diversos(rows, margens, humanos, concluidos, n):
    """Intercala repositorios; inclui maior incerteza SVM primeiro em cada um."""
    por_repo = defaultdict(list)
    for r in rows:
        if r["id"] not in concluidos:
            por_repo[r["repositorio"]].append(r)
    for grupo in por_repo.values():
        grupo.sort(key=lambda r: (margens[r["id"]]["margem_svm"], r["id"]))
    humanos_por_repo = Counter(r["repositorio"] for r in rows if r["id"] in humanos)
    # Prefere projetos ainda pouco rotulados, para evitar repetir TypeScript.
    ordem = sorted(por_repo, key=lambda repo: (humanos_por_repo[repo], repo))
    escolhidos = []
    while len(escolhidos) < n:
        alterou = False
        for repo in ordem:
            if por_repo[repo]:
                escolhidos.append(por_repo[repo].pop(0))
                alterou = True
                if len(escolhidos) >= n:
                    break
        if not alterou:
            break
    return escolhidos


def _prompt(r):
    dados = {
        "titulo": r["titulo"][:280],
        "descricao": r.get("descricao", "")[:900],
        "arquivos": [s.strip() for s in r.get("arquivos", "").split("|") if s.strip()][:20],
        "arquivos_modificados": r.get("arquivos_modificados", ""),
        "linhas_adicionadas": r.get("linhas_adicionadas", ""),
        "linhas_removidas": r.get("linhas_removidas", ""),
    }
    return (
        "Voce e um auditor de commits Git. Classifique pela INTENCAO PRINCIPAL "
        "da alteracao, nao por prefixos nem apenas pela extensao do arquivo. "
        "Nao assuma que arquivos de teste tornam um bugfix em 'test'. "
        "Use: fix (corrige defeito), feat (capacidade nova), "
        "docs (documentacao principal), refactor (reestruturacao sem mudar comportamento), "
        "test (apenas testes), fora_escopo (mudanca administrativa sem enquadramento "
        "no conjunto), indeterminado (evidencia insuficiente). "
        "Clareza: vago (nao diz o que mudou), parcial, claro, indeterminado. "
        "Se nao houver contexto bastante, sinalize duvida, NUNCA invente diff. "
        "Retorne SOMENTE JSON com campos categoria, clareza, duvida (booleano) e "
        "motivo (ate 160 caracteres). Categorias permitidas: " + CATEGORIAS_TEXTO
        + ". Clarezas permitidas: " + CLAREZAS_TEXTO + ".\n"
        + json.dumps(dados, ensure_ascii=False)
    )


def consultar_ollama(r, modelo, *, endpoint="http://127.0.0.1:11434/api/generate"):
    """Solicita JSON estruturado e tenta novamente uma vez se for invalido."""
    erro_final = None
    for tentativa in range(2):
        req = Request(
            endpoint,
            data=json.dumps({
                "model": modelo, "prompt": _prompt(r),
                "stream": False, "format": SCHEMA_OLLAMA,
                "options": {"temperature": 0, "num_predict": 240},
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urlopen(req, timeout=100) as resp:
                resposta = json.loads(resp.read(160000).decode("utf-8"))
        except (TimeoutError, URLError, HTTPError, OSError) as err:
            raise OllamaIndisponivel(
                "Ollama local nao respondeu: " + str(err)[:150]
            ) from err
        try:
            j = json.loads(resposta["response"])
            if not isinstance(j, dict):
                raise ValueError("JSON nao e um objeto")
            cat, cla = j["categoria"], j["clareza"]
            duvida, motivo = j["duvida"], j["motivo"]
            if not isinstance(cat, str) or not isinstance(cla, str):
                raise ValueError("Categoria ou clareza nao sao texto")
            # Normalizar caixa e espacos, sem adivinhar categorias desconhecidas.
            cat, cla = cat.strip().lower(), cla.strip().lower()
            if cat not in CATEGORIAS or cla not in CLAREZAS:
                raise ValueError("Resposta fora do vocabulario")
            if not isinstance(duvida, bool) or not isinstance(motivo, str):
                raise ValueError("Tipos incorretos para duvida/motivo")
            return cat, cla, duvida, motivo[:160]
        except (KeyError, TypeError, ValueError) as err:
            erro_final = err
            if tentativa == 0:
                print("JSON do Ollama invalido; repetindo consulta uma vez...")
    raise ValueError(
        "Resposta invalida apos 2 tentativas: " + str(erro_final)[:150]
    )


def _banco_v6(caminho):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.execute("""CREATE TABLE IF NOT EXISTS palpites (
        id TEXT PRIMARY KEY, categoria_ollama TEXT NOT NULL,
        clareza_ollama TEXT NOT NULL, duvida INTEGER NOT NULL,
        motivo TEXT NOT NULL, modelo TEXT NOT NULL,
        prompt TEXT NOT NULL, criado_em TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS falhas (
        id TEXT PRIMARY KEY, erro TEXT NOT NULL, criado_em TEXT NOT NULL
    )""")
    return con


def _prioridade(r, svm, ollama):
    if ollama is None:
        return ("somente_svm", 9)
    discordancia = svm["categoria_svm"] != ollama["categoria_ollama"]
    duvida = bool(ollama["duvida"]) or ollama["categoria_ollama"] == "indeterminado"
    if discordancia and duvida:
        return ("discordancia_e_duvida", 0)
    if discordancia:
        return ("discordancia", 1)
    if duvida:
        return ("duvida_ollama", 2)
    return ("concordancia_nao_validada", 4)


def executar(*, entrada=ENTRADA, plano=PLANO, banco_v5=BANCO,
             saida=SAIDA, quantidade_ollama=60, modelo_ollama="qwen2.5:3b-instruct",
             cliente=consultar_ollama, sem_ollama=False):
    if not 0 <= quantidade_ollama <= 1000:
        raise ValueError("--quantidade-ollama deve ser entre 0 e 1000")
    rows, dados = abrir(entrada=entrada, plano=plano, banco=banco_v5)
    rotulos = _rotulos_anteriores(rows, dados, banco_v5)
    treino = [r for r in rows if dados["repositorios"][r["repositorio"]] == "treino"]
    pendentes = [r for r in treino if r["id"] not in rotulos]
    modelo = _treinar_svm(rows, rotulos)
    preds = {p["id"]: p for p in _avaliar_margem(modelo, pendentes)}
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    with _banco_v6(saida / BANCO_NOVO) as con:
        # Banco reaproveitado apenas com o MESMO snapshot e MESMO modelo Ollama.
        meta = saida / "metadados.json"
        esperado = {
            "sha256_entrada": dados["sha256_entrada"],
            "modelo_ollama": modelo_ollama,
            "prompt": PROMPT_VERSAO,
        }
        if meta.exists():
            anterior = json.loads(meta.read_text(encoding="utf-8"))
            if anterior != esperado:
                raise ValueError("Saida V6 criada com CSV ou modelo diferente; escolha outra --saida")
        else:
            if con.execute("SELECT COUNT(*) FROM palpites").fetchone()[0]:
                raise ValueError("Banco V6 existente sem metadados; interrompido")
            meta.write_text(json.dumps(esperado, indent=2) + "\n", encoding="utf-8")
        ja = {t[0] for t in con.execute("SELECT id FROM palpites")}
        falhas_anteriores = {t[0] for t in con.execute("SELECT id FROM falhas")}
        if any(uid not in preds for uid in ja | falhas_anteriores):
            raise ValueError("Banco V6 contem ID fora dos commits pendentes de treino")
        selecionados = _selecionar_diversos(
            pendentes, preds, rotulos, ja | falhas_anteriores,
            0 if sem_ollama else quantidade_ollama,
        )
        realizados = 0
        pulados = 0
        for i, r in enumerate(selecionados, 1):
            try:
                cat, cla, duvida, motivo = cliente(r, modelo_ollama)
            except (OllamaIndisponivel, OSError) as err:
                print(f"Ollama indisponivel no commit {i}/{len(selecionados)}: {err}")
                print("Palpites anteriores preservados. Rode novamente quando estiver disponivel.")
                break
            except ValueError as err:
                with con:
                    con.execute(
                        "INSERT OR REPLACE INTO falhas VALUES (?,?,?)",
                        (r["id"], str(err)[:350], datetime.now(timezone.utc).isoformat()),
                    )
                pulados += 1
                print(f"Commit {i}/{len(selecionados)} pulado: JSON invalido; seguindo.")
                continue
            with con:
                con.execute(
                    "INSERT INTO palpites VALUES (?,?,?,?,?,?,?,?)",
                    (r["id"], cat, cla, int(duvida), motivo, modelo_ollama,
                     PROMPT_VERSAO, datetime.now(timezone.utc).isoformat()),
                )
            realizados += 1
            if realizados % 10 == 0:
                print(f"Ollama: {realizados}/{len(selecionados)} novos palpites salvos")
        falhas_total = con.execute("SELECT COUNT(*) FROM falhas").fetchone()[0]
        resultado_ollama = {
            uid: {
                "categoria_ollama": cat, "clareza_ollama": cla, "duvida": duvida,
                "motivo": motivo,
            }
            for uid, cat, cla, duvida, motivo in con.execute(
                "SELECT id,categoria_ollama,clareza_ollama,duvida,motivo FROM palpites"
            )
        }
    saida_csv = saida / "triagem.csv"
    campos = ("id", "repositorio", "titulo", "categoria_svm", "margem_svm",
              "categoria_ollama", "clareza_ollama", "duvida_ollama",
              "prioridade", "motivo", "proveniencia", "rotulo_humano")
    ordenados = []
    for r in pendentes:
        a = preds[r["id"]]
        b = resultado_ollama.get(r["id"])
        prioridade, rank = _prioridade(r, a, b)
        ordenados.append((
            rank, a["margem_svm"],
            {
                "id": r["id"], "repositorio": r["repositorio"],
                "titulo": r["titulo"], "categoria_svm": a["categoria_svm"],
                "margem_svm": a["margem_svm"],
                "categoria_ollama": b["categoria_ollama"] if b else "",
                "clareza_ollama": b["clareza_ollama"] if b else "",
                "duvida_ollama": bool(b["duvida"]) if b else "",
                "prioridade": prioridade,
                "motivo": b["motivo"] if b else "",
                "proveniencia": "PALPITE_AUTOMATICO_NAO_VERIFICADO",
                "rotulo_humano": "",
            },
        ))
    ordenados.sort(key=lambda x: (x[0], x[1], x[2]["id"]))
    with saida_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(t[2] for t in ordenados)
    contagem = Counter(r[2]["prioridade"] for r in ordenados)
    resumo = {
        "protocolo": "v6-triagem-automatica-local-sem-rotulo-humano",
        "treino_v5_assistido_reutilizado": len(rotulos),
        "commits_na_particao_treino": len(treino),
        "pendentes_treino": len(pendentes),
        "svm_previsoes_provisorias": len(preds),
        "ollama_palpite_armazenado": len(resultado_ollama),
        "ollama_novos_nesta_execucao": realizados,
        "ollama_respostas_invalidas_puladas_nesta_execucao": pulados,
        "ollama_respostas_invalidas_total": falhas_total,
        "modelo_ollama": modelo_ollama,
        "triagem_por_prioridade": dict(contagem),
        "validação_foi_lida_para_classificar": False,
        "teste_foi_lido_para_classificar": False,
        "observacoes": [
            "Nao e uma medicao de acuracia: nenhuma previsao automatica e gabarito.",
            "Treino usa 120 ou mais rotulos V5 que podem ter sido assistidos por IA.",
            "Concordancia entre SVM e Ollama NAO implica que ambos estejam certos.",
            "Respostas invalidas do Ollama sao puladas e registradas em SQLite separado.",
            "Sem calibracao de margens ou probabilidades.",
            "Nenhum registro de validacao/teste usado na inferencia.",
            "Nenhum rotulo V5, repo Git ou modelo anterior foi alterado.",
            "Arquivo triagem.csv pode conter textos privados; nao enviar sem revisar.",
        ],
        "saida": str(saida_csv),
    }
    (saida / "resumo.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return resumo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--plano", type=Path, default=PLANO)
    parser.add_argument("--banco-v5", type=Path, default=BANCO)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--quantidade-ollama", type=int, default=60)
    parser.add_argument("--modelo-ollama", default="qwen2.5:3b-instruct")
    parser.add_argument("--sem-ollama", action="store_true")
    args = parser.parse_args(argv)
    try:
        resultado = executar(
            entrada=args.entrada, plano=args.plano, banco_v5=args.banco_v5,
            saida=args.saida, quantidade_ollama=args.quantidade_ollama,
            modelo_ollama=args.modelo_ollama, sem_ollama=args.sem_ollama,
        )
    except (OSError, ValueError, sqlite3.Error) as ex:
        parser.error(str(ex))
    print("== TRIAGEM V6 (nao sao rotulos humanos) ==")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
