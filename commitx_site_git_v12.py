#!/usr/bin/env python3
"""Interface CommitX com comparação entre a V12 e os indícios do diff Git."""

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from commitx_site_git_v10 import PADRAO, RAIZ, criar_handler as criar_handler_v10


HTML = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Classificação de commits</title>
<style>
:root {
  color-scheme: light;
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  --ink: #1d2734;
  --sub: #4e5c6c;
  --line: #dce2e8;
  --navy: #24466c;
  --light: #f6f8fa;
}
* {box-sizing: border-box}
[hidden] {display: none !important}
body {margin: 0; background: #fff; color: var(--ink)}
.container {width: min(1120px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 44px}
h1, h2, h3, h4 {line-height: 1.3; margin: 0 0 12px}
h1 {font-size: clamp(26px, 4vw, 34px); margin-bottom: 18px}
h2, h3 {font-size: 19px}
h4 {font-size: 16px; margin-bottom: 6px}
p {margin: 0 0 10px}
.panel, .git-section, .history-toggle {border: 1px solid var(--line); border-radius: 8px}
.panel, .git-inside, .history-body {padding: clamp(14px, 3vw, 24px)}
.git-section, .history-toggle {margin-top: 14px}
summary {cursor: pointer; font-weight: 650; color: var(--navy)}
.git-section > summary, .history-toggle > summary {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 15px clamp(14px, 3vw, 24px); list-style: none;
}
.git-section > summary::-webkit-details-marker, .history-toggle > summary::-webkit-details-marker {display: none}
.git-section[open] > summary, .history-toggle[open] > summary {border-bottom: 1px solid var(--line)}
.git-section[open] > summary > span:last-child, .history-toggle[open] .summary-caret {
  display: inline-block; transform: rotate(180deg);
}
label {display: block; font-weight: 600; margin-bottom: 5px}
textarea, select, input, button {font: inherit; color: inherit}
textarea, select, input {
  display: block; width: 100%; padding: 9px 12px; border: 1px solid #aebbc9; border-radius: 5px;
  background: #fff;
}
textarea {min-height: 72px; resize: vertical}
.optional-description, .git-report details, #detalhes {margin-top: 12px}
.optional-body {margin: 8px 0}
.hint, .summary-right, .metadata, .description, .empty-history {color: var(--sub)}
.hint, .summary-right, .eyebrow {font-size: 14px}
.summary-caret {margin-left: 8px}
.toolbar, .git-toolbar {display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-top: 14px}
.mode-field, .git-input {width: min(100%, 270px)}
.git-ast-option {
  display: flex; align-items: center; gap: 8px; width: fit-content;
  margin: 8px 0 0; min-height: 36px; color: var(--sub); font-weight: 400;
}
.git-ast-option input {width: 1rem; height: 1rem; margin: 0; flex: none; accent-color: var(--navy)}
.actions, .samples {display: flex; flex-wrap: wrap; align-items: center; gap: 8px}
.samples {margin-top: 14px; font-size: 14px}
button {
  cursor: pointer; min-height: 44px; padding: 8px 14px; border: 1px solid #aebbc9;
  border-radius: 5px; background: #fff;
}
button.primary {background: var(--navy); color: #fff; border-color: var(--navy); font-weight: 650}
button:hover {filter: brightness(.94)}
button:disabled {opacity: .65; cursor: default}
.samples button, .tiny-button {min-height: 34px; padding: 4px 10px}
:focus-visible {outline: 3px solid #537eae; outline-offset: 2px}
.results-area, .git-report {border-top: 1px solid var(--line); padding-top: 16px; margin-top: 16px}
.category {font-size: 24px; font-weight: 700; color: var(--navy); overflow-wrap: anywhere}
.inline-error {color: #a72e2c; margin-top: 10px}
.metadata span {display: block}
.compare {margin-top: 12px}
.compare-line {display: flex; gap: 14px; margin-bottom: 4px}
.git-report, .tablebox {overflow-wrap: anywhere}
.git-comparison {margin: 14px 0; padding-left: 12px; border-left: 3px solid #acbccd}
.git-report ul {margin: 0 0 12px; padding-left: 24px; max-height: 15rem; overflow: auto}
.git-report pre {max-height: 20rem; overflow: auto; border: 1px solid var(--line); padding: 12px; background: var(--light)}
.history-actions {margin-bottom: 8px}
.tablebox {max-height: 17rem; overflow: auto}
table {width: 100%; border-collapse: collapse; text-align: left}
th, td {padding: 8px; border-bottom: 1px solid var(--line)}
</style>
</head>
<body>
<main class="container">
<h1>Classificação de commits</h1>
<div class="work">
<section class="panel" aria-labelledby="form-heading">
<h2 id="form-heading">Analisar mensagem</h2>
<form id="form">
<div class="field-grid">
<div class="field"><label for="titulo">Título do commit</label>
<textarea id="titulo" maxlength="500" required spellcheck="false">refactor: Extract helper method</textarea></div>
</div>
<details class="optional-description" id="descricao-toggle">
<summary>Adicionar descrição (opcional)</summary>
<div class="optional-body">
<label for="descricao">Descrição do commit</label>
<textarea id="descricao" maxlength="2500" placeholder="Detalhes da alteração"></textarea>
<p class="hint">Usada somente na revisão de escrita.</p>
</div>
</details>
<div class="toolbar"><div class="mode-field"><label for="modo">Modo de classificação</label>
<select id="modo"><option value="auto">Automático</option><option value="com_prefixo">Com prefixo</option><option value="sem_prefixo">Sem prefixo</option></select></div>
<div class="actions"><button class="primary" id="enviar" type="submit">Classificar</button><button type="button" id="comparar">Comparar modelos</button></div></div>
<div class="samples"><span>Exemplos:</span><button type="button" data-msg="fix: Correct pagination bug">fix</button><button type="button" data-msg="feat: Add login endpoint">feat</button><button type="button" data-msg="docs: Update installation guide">docs</button><button type="button" data-msg="refactor: Extract helper method">refactor</button><button type="button" data-msg="test: Add regression test for parser">test</button></div>
</form>
<div class="results-area" id="area-resultado" aria-labelledby="result-heading" hidden>
<h2 id="result-heading">Resultado da análise</h2>
<div class="result" id="result" role="status" aria-live="polite">
<div class="eyebrow" id="result-label">Categoria prevista</div>
<div class="category" id="classe"></div>
<p class="description" id="explicacao"></p>
<div class="metadata" id="metadata"></div>
<div class="compare" id="comparacao" hidden><h3>Comparação de modelos</h3><div class="compare-line"><span>Com prefixo</span><b id="cmp-com">—</b></div><div class="compare-line"><span>Sem prefixo</span><b id="cmp-sem">—</b></div><p class="hint">Resultados distintos não indicam, por si só, qual está correto.</p></div>
<details id="detalhes"><summary>Detalhes técnicos</summary><div class="details-content" id="detalhes-conteudo"></div></details>
</div>
</div>
</section>
</div>

<details class="git-section" id="git-section">
  <summary><span>Analisar um commit existente do Git</span><span aria-hidden="true">⌄</span></summary>
  <div class="git-inside">
    <div class="git-toolbar">
      <div class="git-input"><label for="git-ref">Commit (HEAD ou SHA)</label><input id="git-ref" type="text" value="HEAD" maxlength="50" spellcheck="false" placeholder="HEAD"></div>
      <button type="button" class="primary" id="git-analisar">Analisar commit Git</button>
    </div>
    <label class="git-ast-option"><input id="git-incluir-ast" type="checkbox"> Incluir análise estrutural de arquivos Python</label>
    <div id="git-report" class="git-report" hidden aria-live="polite">
      <h3>Alterações encontradas</h3>
      <div id="git-summary"></div>
      <p id="git-category"></p>
      <div class="git-comparison">
        <h4 id="git-status"></h4>
        <p id="git-explanation"></p>
      </div>
      <h4>Indícios no código</h4>
      <div id="git-evidence"></div>
      <h4>Arquivos alterados</h4>
      <div id="git-files"></div>
      <details id="git-diff-toggle"><summary>Ver trecho do diff</summary><pre id="git-diff"></pre></details>
      <details id="git-ast-toggle" hidden><summary id="git-ast-heading">Evidências estruturais</summary>
        <div id="git-ast-result" class="optional-body"></div>
      </details>
    </div>
    <p id="git-error" class="inline-error" role="alert" hidden></p>
  </div>
</details>

<details class="history history-toggle" id="history-toggle">
  <summary class="history-summary"><span id="history-heading">Histórico da sessão</span><span class="summary-right"><span id="history-count">0 análises</span><span class="summary-caret" aria-hidden="true">⌄</span></span></summary>
  <div class="history-body">
    <div class="history-actions"><button type="button" class="tiny-button" id="limpar">Limpar</button></div>
    <div id="historico" class="tablebox"><p class="empty-history">Nenhum commit classificado.</p></div>
  </div>
</details>
</main>
<script>
const $=id=>document.getElementById(id);
const DESC={fix:'Correção de comportamento incorreto.',feat:'Adição de funcionalidade.',docs:'Alteração na documentação.',refactor:'Reorganização interna do código.',test:'Criação ou alteração de testes.'};
const HIST=[];
function appendText(to,tag,value){const el=document.createElement(tag);el.textContent=String(value);to.appendChild(el);return el}
function setResult(category,description,error=false){
  $('area-resultado').hidden=false;$('result').classList.add('visible');
  $('result-label').textContent=error?'Erro na análise':'Categoria prevista';
  $('classe').textContent=category;$('classe').classList.toggle('inline-error',error);
  $('explicacao').textContent=description;
  $('metadata').replaceChildren();$('detalhes-conteudo').replaceChildren();$('detalhes').open=false;
  $('comparacao').hidden=true;
}
async function getJson(url,opts){const r=await fetch(url,opts);const d=await r.json();if(!r.ok)throw Error(d.erro||'Erro de comunicação com o servidor');return d}
async function checkStatus(){
 try{
  const d=await getJson('/api/status',{cache:'no-store'});
  if(!d.pronto){$('enviar').disabled=true;$('comparar').disabled=true;setResult('Modelo indisponível','Verifique os arquivos do modelo no terminal.',true)}
 }catch(e){$('enviar').disabled=true;$('comparar').disabled=true;setResult('Falha de conexão',e.message,true)}
}
function renderAnalysis(d){
 const c=d.classificacao||{},w=d.escrita||{};
 setResult(c.categoria_sugerida||'Sem sugestão',DESC[c.categoria_sugerida]||'A mensagem requer revisão humana.');
 const meta=$('metadata');appendText(meta,'span','Modo utilizado: '+(c.modo||'não aplicável'));
 const tech=$('detalhes-conteudo');
 appendText(tech,'p','Tipo declarado: '+(c.tipo_declarado||'nenhum'));
 if(typeof c.margem_svm==='number')appendText(tech,'p','Margem SVM: '+c.margem_svm.toFixed(4)+' (não é probabilidade)');
 for(const aviso of c.avisos||[])appendText(tech,'p',aviso);
 for(const alerta of w.alertas||[])appendText(tech,'p','Escrita: '+(alerta.mensagem||'')+' '+(alerta.sugestao||''));
 if(!((w.alertas||[]).length))appendText(tech,'p','Revisão de escrita: nenhum alerta das regras simples.');
}
function drawHistory(){
 $('history-count').textContent=HIST.length+' '+(HIST.length===1?'análise':'análises');
 const root=$('historico');root.replaceChildren();
 if(!HIST.length){appendText(root,'p','Nenhum commit classificado.').className='empty-history';return}
 const table=document.createElement('table');const thead=document.createElement('thead');const tr=document.createElement('tr');
 for(const h of ['Mensagem','Categoria'])appendText(tr,'th',h);
 thead.appendChild(tr);table.appendChild(thead);const body=document.createElement('tbody');
 for(const item of HIST.slice().reverse().slice(0,8)){
   const r=document.createElement('tr');appendText(r,'td',item.title);appendText(r,'td',item.category);body.appendChild(r);
 }
 table.appendChild(body);root.appendChild(table);
}
for(const b of document.querySelectorAll('[data-msg]'))b.addEventListener('click',()=>{$('titulo').value=b.dataset.msg;$('titulo').focus()});
$('form').addEventListener('submit',async e=>{
 e.preventDefault();const b=$('enviar');b.disabled=true;b.textContent='Analisando...';
 try{const d=await getJson('/api/classificar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({titulo:$('titulo').value,descricao:$('descricao').value,modo:$('modo').value})});
 renderAnalysis(d);const c=d.classificacao||{};HIST.push({title:$('titulo').value.trim(),category:c.categoria_sugerida||'Sem sugestão',mode:c.modo||'—'});if(HIST.length>50)HIST.shift();drawHistory();
 }catch(err){setResult('Não foi possível classificar',err.message,true)}finally{b.disabled=false;b.textContent='Classificar'}
});
$('comparar').addEventListener('click',async()=>{
 const btn=$('comparar');btn.disabled=true;btn.textContent='Comparando...';
 try{const d=await getJson('/api/comparar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({titulo:$('titulo').value,descricao:$('descricao').value})});
 $('area-resultado').hidden=false;$('result').classList.add('visible');
 $('result-label').textContent='Comparação dos modelos';$('classe').textContent='Com e sem prefixo';$('classe').classList.remove('inline-error');
 $('explicacao').textContent='Classificações para a mesma mensagem.';$('metadata').replaceChildren();$('detalhes-conteudo').replaceChildren();$('detalhes').open=false;
 $('cmp-com').textContent=d.com_prefixo?.categoria_sugerida||'Sem sugestão';$('cmp-sem').textContent=d.sem_prefixo?.categoria_sugerida||'Sem sugestão';$('comparacao').hidden=false;
 }catch(err){setResult('Não foi possível comparar',err.message,true)}finally{btn.disabled=false;btn.textContent='Comparar modelos'}
});
$('limpar').addEventListener('click',()=>{HIST.length=0;drawHistory()});

const STATUS_GIT = new Map([
  ['compativel', 'Indícios compatíveis'],
  ['possivel_divergencia', 'Possível divergência'],
  ['inconclusivo', 'Não foi possível determinar'],
]);
const TIPO_INDICIO = new Map([
  ['caminho', 'Tipo de arquivo'],
  ['tratamento_excecao', 'Tratamento de exceção'],
  ['validacao', 'Validação'],
  ['condicao_alterada', 'Condição alterada'],
  ['verificacao_nulo', 'Verificação de valor nulo'],
  ['declaracao', 'Declaração nova'],
  ['endpoint', 'Rota nova'],
  ['arquivo_novo', 'Arquivo de implementação novo'],
  ['movimentacao_funcao', 'Função movida'],
  ['extracao_funcao', 'Função extraída'],
]);

const TIPO_AST = new Map([
  ['funcao_adicionada', 'Função adicionada'],
  ['funcao_removida', 'Função removida'],
  ['classe_adicionada', 'Classe adicionada'],
  ['classe_removida', 'Classe removida'],
  ['assinatura_modificada', 'Assinatura modificada'],
  ['decoradores_modificados', 'Decoradores modificados'],
  ['docstring_alterada', 'Docstring alterada'],
  ['condicao_modificada', 'Condição modificada'],
  ['condicao_adicionada', 'Condição adicionada'],
  ['condicao_removida', 'Condição removida'],
  ['tratamento_excecao_modificado', 'Tratamento de exceção modificado'],
  ['tratamento_excecao_adicionado', 'Tratamento de exceção adicionado'],
  ['tratamento_excecao_removido', 'Tratamento de exceção removido'],
  ['corpo_modificado', 'Corpo da função modificado'],
  ['possivel_extracao', 'Possível extração de função'],
  ['possivel_movimentacao', 'Possível movimentação de função'],
]);
const LIMITE_AST = new Map([
  ['erro_sintaxe', 'Erro de sintaxe'],
  ['binario', 'Arquivo binário'],
  ['utf8_invalido', 'Codificação incompatível'],
  ['tipo_nao_suportado', 'Tipo de arquivo não suportado'],
  ['limite_bytes_arquivo', 'Limite de tamanho por arquivo excedido'],
  ['limite_bytes_totais', 'Limite total de leitura excedido'],
  ['limite_bytes', 'Limite de tamanho da versão excedido'],
  ['limite_arquivos', 'Limite de quantidade de arquivos atingido'],
  ['limite_tempo', 'Tempo de leitura excedido'],
  ['limite_complexidade', 'Limite de complexidade excedido'],
  ['limite_profundidade', 'Limite de profundidade excedido'],
  ['declaracoes_homonimas', 'Declarações com o mesmo nome no escopo'],
]);

function localAst(local) {
  if (!local) return '';
  const escopo = local.escopo && local.escopo !== '<modulo>' ? local.escopo : '';
  return [local.arquivo, escopo, local.linha ? 'linha ' + local.linha : ''].filter(Boolean).join(' · ');
}

function renderAst(resultado, solicitado) {
  const painel = $('git-ast-toggle');
  const corpo = $('git-ast-result');
  painel.open = false;
  painel.hidden = !solicitado;
  corpo.replaceChildren();
  if (!solicitado) return;

  const cobertura = resultado?.cobertura;
  let aviso = '';
  if (cobertura === 'parcial') aviso = 'Cobertura parcial';
  else if (cobertura === 'erro_sintaxe') aviso = 'Erro de sintaxe';
  else if (cobertura !== 'completa') aviso = 'Análise indisponível';
  $('git-ast-heading').textContent = 'Evidências estruturais' + (aviso ? ' · ' + aviso : '');
  if (aviso) appendText(corpo, 'p', 'Resultado inconclusivo para as versões que ficaram sem análise.').className = 'hint';

  const evidencias = resultado?.evidencias || [];
  const arquivos = resultado?.arquivos || [];
  if (evidencias.length) {
    const lista = document.createElement('ul');
    for (const fato of evidencias) {
      const antes = localAst(fato.anterior);
      const depois = localAst(fato.posterior);
      const local = antes && depois && antes !== depois
        ? 'Antes: ' + antes + ' / Depois: ' + depois : antes || depois;
      const tipo = TIPO_AST.get(fato.tipo) || 'Estrutura modificada';
      appendText(lista, 'li', tipo + (local ? ' — ' + local : ''));
    }
    corpo.appendChild(lista);
    if (evidencias.some(fato => fato.limitacao)) {
      appendText(corpo, 'p', 'As relações sugeridas pelo código podem mudar conforme o contexto e precisam de revisão.').className = 'hint';
    }
  } else if (cobertura === 'completa') {
    appendText(corpo, 'p', arquivos.length ? 'Nenhuma diferença estrutural encontrada.' : 'Nenhum arquivo Python alterado.');
  }

  const motivosPorArquivo = new Set();
  const avisos = [];
  for (const arquivo of arquivos) {
    for (const limite of arquivo.limitacoes || []) {
      motivosPorArquivo.add(limite.motivo);
      const motivo = LIMITE_AST.get(limite.motivo) || 'Versão indisponível';
      const lado = limite.lado === 'anterior' ? 'versão anterior' : 'versão posterior';
      const linha = limite.linha ? ' · linha ' + limite.linha : '';
      avisos.push(motivo + ' — ' + arquivo.caminho + ' · ' + lado + linha);
    }
  }
  for (const limite of resultado?.limitacoes || []) {
    if (!motivosPorArquivo.has(limite)) avisos.push(LIMITE_AST.get(limite) || 'Uma parte da análise ficou indisponível.');
  }
  if (avisos.length) {
    const lista = document.createElement('ul');
    for (const item of new Set(avisos)) appendText(lista, 'li', item);
    corpo.appendChild(lista);
  }
}

function renderGit(dados) {
  const git = dados.git;
  const comparacao = dados.analise_codigo?.comparacao;
  const classificacao = dados.analise?.classificacao;
  const summary = $('git-summary');
  summary.replaceChildren();
  appendText(summary, 'p', 'Mensagem: ' + git.titulo);
  appendText(summary, 'p', 'Commit: ' + git.commit.slice(0, 12));
  appendText(summary, 'p', `+${git.linhas_adicionadas} linhas / −${git.linhas_removidas} linhas`);
  if (git.merge) appendText(summary, 'p', 'Diff comparado ao primeiro pai do merge.');

  const categoria = classificacao?.categoria_sugerida;
  $('git-category').textContent = 'Categoria prevista pela V12: ' +
    (categoria || (classificacao ? 'Sem sugestão' : 'Indisponível'));
  $('git-status').textContent = STATUS_GIT.get(comparacao?.status) || 'Não foi possível determinar';
  $('git-explanation').textContent = comparacao?.explicacao || 'A comparação do código está indisponível.';

  const evidence = $('git-evidence');
  evidence.replaceChildren();
  const categorias = comparacao?.categorias_codigo || [];
  if (categorias.length) appendText(evidence, 'p', 'Categorias sugeridas pelo diff: ' + categorias.join(', '));
  const indicios = comparacao?.evidencias || [];
  if (indicios.length) {
    const lista = document.createElement('ul');
    for (const item of indicios) {
      const tipo = TIPO_INDICIO.get(item.tipo) || 'Alteração observada';
      const local = item.arquivo + (item.linha ? ' · linha ' + item.linha : '');
      const categorias = item.categorias || (item.categoria ? [item.categoria] : []);
      const sufixo = categorias.length ? ' (' + categorias.join(', ') + ')' : '';
      appendText(lista, 'li', tipo + sufixo + ' — ' + local);
    }
    evidence.appendChild(lista);
  } else {
    appendText(evidence, 'p', 'Nenhum indício disponível para este commit.');
  }

  const files = $('git-files');
  files.replaceChildren();
  if (git.arquivos.length) {
    const lista = document.createElement('ul');
    for (const arquivo of git.arquivos) {
      const contagem = arquivo.adicionadas === null && arquivo.removidas === null
        ? 'binário'
        : `+${arquivo.adicionadas ?? '?'} / −${arquivo.removidas ?? '?'}`;
      appendText(lista, 'li', arquivo.arquivo + ' (' + contagem + ')');
    }
    files.appendChild(lista);
  } else {
    appendText(files, 'p', 'Nenhum arquivo alterado.');
  }

  $('git-diff-toggle').open = false;
  $('git-diff').textContent = (git.diff_previa || 'Sem diff textual.') +
    (git.diff_truncado ? '\n\n[Prévia truncada]' : '');
  $('git-report').hidden = false;
}

$('git-analisar').addEventListener('click', async () => {
  const botao = $('git-analisar');
  const incluirAst = $('git-incluir-ast').checked;
  const pedido = {commit: $('git-ref').value.trim()};
  if (incluirAst) pedido.analise_estrutural = true;
  botao.disabled = true;
  botao.textContent = 'Lendo commit...';
  $('git-error').hidden = true;
  $('git-report').hidden = true;
  try {
    const dados = await getJson('/api/git/analisar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(pedido),
    });
    renderGit(dados);
    renderAst(dados.analise_estrutural, incluirAst);
    $('titulo').value = dados.git.titulo;
    $('descricao').value = dados.git.descricao;
    if (dados.analise) {
      renderAnalysis(dados.analise);
      HIST.push({
        title: dados.git.titulo,
        category: dados.analise.classificacao?.categoria_sugerida || 'Sem sugestão',
      });
      if (HIST.length > 50) HIST.shift();
      drawHistory();
    } else {
      setResult('Categoria indisponível', 'Consulte a análise Git para ver os indícios do commit.', true);
    }
  } catch (erro) {
    $('git-error').textContent = erro.message;
    $('git-error').hidden = false;
  } finally {
    botao.disabled = false;
    botao.textContent = 'Analisar commit Git';
  }
});

checkStatus();drawHistory();
</script>
</body>
</html>'''


def criar_handler(artefatos: Path, repositorio: Path):
    class Handler(criar_handler_v10(artefatos, repositorio)):
        def do_GET(self):
            if urlsplit(self.path).path not in ("/", "/index.html"):
                return super().do_GET()

            payload = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--artefatos", type=Path, default=PADRAO)
    parser.add_argument("--repositorio", type=Path, default=RAIZ, help="Repositório Git local")
    args = parser.parse_args(argv)
    if not 1024 <= args.porta <= 65535:
        parser.error("Porta deve estar entre 1024 e 65535.")

    artefatos = args.artefatos.expanduser().resolve()
    repositorio = args.repositorio.expanduser().resolve()
    with ThreadingHTTPServer(("127.0.0.1", args.porta), criar_handler(artefatos, repositorio)) as servidor:
        print(f"CommitX disponível em http://127.0.0.1:{args.porta}", flush=True)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
