"""Demonstracao academica local do CommitX (sem retreinamento).

Executar:
  python -m commitx.demo_local --porta 8765
Abrir no navegador: http://127.0.0.1:8765

Carrega SOMENTE arquivos joblib locais confiaveis. Sem acesso a internet.
Nao usa a particao teste. Acuracia nao e medida por este painel.
"""
import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from joblib import load

from .academico import analisar

PADRAO = {
    "original": Path("resultados/academico-simples-01/modelo.joblib"),
    "pseudo": Path("resultados/academico-pseudo-02/modelo.joblib"),
}
RESUMOS = {
    "original": Path("resultados/academico-simples-01/resumo.json"),
    "pseudo": Path("resultados/academico-pseudo-02/resumo.json"),
}
CLASSES = ("fix", "feat", "docs", "refactor", "test")

HTML = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CommitX — Demonstracao academica</title>
<style>
:root{font-family:system-ui,Arial,sans-serif;color-scheme:dark}
body{background:#101827;color:#ecf2fb;margin:0}
main{max-width:940px;margin:auto;padding:35px 20px 65px}
p,small{color:#b4c3d8;line-height:1.55}
header{padding:12px 0 24px}
h1{font-size:2.6rem;margin:0}h2{margin-top:36px}
.panel,.metric{background:#1b2b43;border:1px solid #314563;border-radius:14px;padding:20px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.metric strong{display:block;font-size:1.9rem;margin-top:8px}
label{display:block;margin:14px 0 7px;font-weight:600}
textarea,select{box-sizing:border-box;background:#0e1a2c;border:1px solid #50617b;color:#fff;border-radius:8px;padding:12px;font:inherit;width:100%}
textarea{min-height:105px;resize:vertical}
button{margin-top:16px;padding:12px 24px;background:#60a5fa;color:#0b1829;border:0;border-radius:8px;font-weight:bold;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
#resultado{margin-top:16px;white-space:pre-wrap;line-height:1.6}
.fig{padding:14px 0;border-bottom:1px solid #35455d}
.barrow{display:flex;align-items:center;gap:8px;margin:7px 0}
.barrow span{width:75px;color:#b4c3d8;font-size:.88rem}
.barbg{flex:1;background:#0d1929;border-radius:6px;height:19px;overflow:hidden}
.bar{height:100%;background:#60a5fa;border-radius:6px}
.bar.pseudo{background:#34d399}
.barrow b{width:70px;text-align:right;font-size:.87rem}
.notice{border-left:3px solid #fbbf24;padding-left:15px}
</style>
</head>
<body><main>
<header><h1>CommitX</h1><p>Classificacao de mensagens Git — demonstracao academica local</p></header>
<div class="metrics">
<div class="metric">Commits processados<strong id="total">—</strong></div>
<div class="metric">Rotulos de treino<strong id="treino">—</strong></div>
<div class="metric">Pseudorrotulos<strong id="pseudo">—</strong></div>
</div>
<h2>Experimente uma mensagem</h2>
<div class="panel">
<label for="titulo">Mensagem de commit</label>
<textarea id="titulo" maxlength="1000" placeholder="Exemplo: fix: correct authentication error">fix: correct authentication error</textarea>
<label for="modelo">Modelo</label>
<select id="modelo"><option value="original">SVM original</option><option value="pseudo">SVM com pseudorrotulos</option></select>
<button id="rodar" type="button">Classificar commit</button>
<div id="resultado" aria-live="polite"></div>
</div>
<h2>Distribuicao dos 97.001 commits</h2>
<p>Essas barras mostram as categorias <strong>previstas</strong>, nao o numero de acertos.</p>
<div class="panel" id="grafico">Carregando resultados...</div>
<h2>Como interpretar</h2>
<p class="notice">As previsoes sao automaticas e podem estar erradas. A margem SVM nao e probabilidade calibrada. Este painel nao mede acuracia nem verifica generalizacao em novos repositorios.</p>
</main>
<script>
const fmt = new Intl.NumberFormat("pt-BR");
async function carregar(){
  try{
    const r=await fetch("/api/resumo");const d=await r.json();
    if(!r.ok)throw new Error(d.erro||"Falha no resumo");
    const a=d.original||{},b=d.pseudo||{};
    document.getElementById("total").textContent=fmt.format(a.total_classificado||0);
    document.getElementById("treino").textContent=fmt.format(a.treino_humano_assistido||0);
    document.getElementById("pseudo").textContent=fmt.format(b.pseudo_rotulos_adicionados||0);
    const dados=[a.categorias_previstas||{},b.categorias_previstas||{}];
    const categorias=["fix","feat","docs","refactor","test"];
    const maior=Math.max(1,...dados.flatMap(x=>Object.values(x).map(Number)));
    const grafico=document.getElementById("grafico");grafico.replaceChildren();
    for(const nome of categorias){
      const figura=document.createElement("div");figura.className="fig";
      const titulo=document.createElement("strong");titulo.textContent=nome;figura.appendChild(titulo);
      ["Original","Pseudo"].forEach((rotulo,i)=>{
        const linha=document.createElement("div");linha.className="barrow";
        const texto=document.createElement("span");texto.textContent=rotulo;
        const fundo=document.createElement("div");fundo.className="barbg";
        const barra=document.createElement("div");barra.className="bar"+(i?" pseudo":"");
        const valor=Number(dados[i][nome]||0);barra.style.width=(100*valor/maior)+"%";
        fundo.appendChild(barra);
        const num=document.createElement("b");num.textContent=fmt.format(valor);
        linha.append(texto,fundo,num);figura.appendChild(linha);
      });
      grafico.appendChild(figura);
    }
  }catch(e){document.getElementById("grafico").textContent="Erro: "+e.message;}
}
document.getElementById("rodar").addEventListener("click",async()=>{
  const botao=document.getElementById("rodar");botao.disabled=true;
  const out=document.getElementById("resultado");out.textContent="Classificando...";
  try{
    const r=await fetch("/api/classificar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
      titulo:document.getElementById("titulo").value,modelo:document.getElementById("modelo").value
    })});
    const d=await r.json();if(!r.ok)throw new Error(d.erro||"Erro");
    out.textContent="Categoria: "+(d.categoria_prevista||"indeterminada")+
      "\nSegunda opcao: "+(d.segunda_opcao||"—")+
      "\nMargem SVM: "+(d.margem_svm??"—")+
      "\n"+d.aviso;
  }catch(e){out.textContent="Erro: "+e.message}
  finally{botao.disabled=false}
});
carregar();
</script></body></html>"""


def obter_resumos(caminhos=None):
    caminhos = caminhos or RESUMOS
    saida = {}
    for nome, arquivo in caminhos.items():
        arquivo = Path(arquivo)
        if not arquivo.is_file():
            raise FileNotFoundError(f"Resumo nao encontrado: {arquivo}")
        d = json.loads(arquivo.read_text(encoding="utf-8"))
        saida[nome] = {
            "total_classificado": d.get("total_classificado", 0),
            "treino_humano_assistido": d.get("treino_humano_assistido", 0),
            "pseudo_rotulos_adicionados": d.get("pseudo_rotulos_adicionados", 0),
            "categorias_previstas": {
                c: d.get("categorias_previstas", {}).get(c, 0) for c in CLASSES
            },
        }
    return saida


def prever(dados, modelos):
    if not isinstance(dados, dict):
        raise ValueError("Envie objeto JSON")
    nome = dados.get("modelo")
    titulo = dados.get("titulo")
    if nome not in modelos:
        raise ValueError("Modelo invalido")
    if not isinstance(titulo, str) or not titulo.strip() or len(titulo) > 1000:
        raise ValueError("Titulo deve ter entre 1 e 1000 caracteres")
    resultado = analisar(modelos[nome], titulo)
    return {
        "categoria_prevista": resultado.get("categoria_prevista", ""),
        "segunda_opcao": resultado.get("segunda_opcao", ""),
        "margem_svm": resultado.get("margem_svm", ""),
        "aviso": "Predicao automatica, nao gabarito. Sem teste independente.",
    }


def criar_handler(modelos, resumos):
    class Handler(BaseHTTPRequestHandler):
        def responder(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            rota = urlsplit(self.path).path
            if rota == "/api/resumo":
                self.responder(200, resumos)
                return
            if rota not in ("/", "/index.html"):
                self.send_error(404)
                return
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if urlsplit(self.path).path != "/api/classificar":
                self.send_error(404)
                return
            origin = self.headers.get("Origin", "")
            allowed = f"http://127.0.0.1:{self.server.server_port}"
            if origin and origin != allowed:
                self.responder(403, {"erro": "Origem nao permitida"})
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self.responder(415, {"erro": "Use JSON"})
                return
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if tamanho < 2 or tamanho > 4096:
                    raise ValueError("JSON muito grande ou vazio")
                dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                self.responder(200, prever(dados, modelos))
            except (ValueError, UnicodeError, json.JSONDecodeError) as erro:
                self.responder(400, {"erro": str(erro)})
            except Exception:
                self.responder(500, {"erro": "Falha ao analisar o commit. Consulte o terminal."})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--original", type=Path, default=PADRAO["original"])
    parser.add_argument("--pseudo", type=Path, default=PADRAO["pseudo"])
    args = parser.parse_args(argv)
    if not 1024 <= args.porta <= 65535:
        parser.error("Porta deve estar entre 1024 e 65535")
    caminhos = {"original": args.original, "pseudo": args.pseudo}
    for nome, arquivo in caminhos.items():
        if not arquivo.is_file():
            parser.error(f"Modelo {nome} nao encontrado: {arquivo}")
    # Arquivos joblib: carregar SOMENTE modelos gerados localmente e confiaveis.
    modelos = {nome: load(arquivo) for nome, arquivo in caminhos.items()}
    try:
        resumos = obter_resumos()
    except (OSError, ValueError) as erro:
        parser.error(str(erro))
    server = ThreadingHTTPServer(("127.0.0.1", args.porta), criar_handler(modelos, resumos))
    print(f"CommitX: http://127.0.0.1:{args.porta}", flush=True)
    print("Pressione Ctrl+C para encerrar. Nenhum modelo sera treinado.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando servidor.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
