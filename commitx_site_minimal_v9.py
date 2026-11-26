#!/usr/bin/env python3
"""CommitX V12 — interface local minimalista do classificador FINAL.

Uso na raiz do projeto, sem instalar bibliotecas web:
    .venv/bin/python commitx_site_minimal.py
    # acesse http://127.0.0.1:8765

A demonstracao executa a funcao real commitx.v12_final.analisar_modelo.
Nao treina, nao altera bancos, nao grava rotulos, nao consulta a internet.
Somente carregue arquivos .joblib que voce treinou localmente e considera confiaveis.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Importacao real do projeto; falhas de dependencia sao mostradas no console.
from commitx.escrita import revisar_escrita
from commitx.v12_final import (
    MANIFESTO, MODEL_COM, MODEL_SEM, analisar_modelo,
)

PADRAO = RAIZ / "resultados" / "modelo-final-v12-01"
CLASSES = ("fix", "feat", "docs", "refactor", "test")

HTML = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f7f8fa">
<title>Classificação de commits</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;--ink:#1d2734;--sub:#596574;--line:#dce2e8;--background:#f7f8fa;--white:#fff;--navy:#24466c;--focus:#adc8e7}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--background);color:var(--ink);font-size:14px;line-height:1.55}
.container{width:min(960px,calc(100% - 36px));margin:0 auto}
header{background:white;border-bottom:1px solid var(--line)}
.head{min-height:70px;display:flex;gap:16px;align-items:center;justify-content:space-between}
.brand{font-size:22px;letter-spacing:-.6px;font-weight:750}.brand small{display:block;color:var(--sub);font-weight:400;font-size:12px;letter-spacing:0}
.status{font-size:12px;color:var(--sub);display:flex;align-items:center;gap:8px}
.dot{background:#9ca3af;width:8px;height:8px;border-radius:50%}.status.ready .dot{background:#327653}.status.offline .dot{background:#b14740}
main{padding:34px 0 42px}
h1{font-size:25px;line-height:1.3;letter-spacing:-.5px;font-weight:650;margin:0 0 7px}
.lead{color:var(--sub);margin:0 0 25px;font-size:14px}
.work{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel{min-width:0;background:var(--white);border:1px solid var(--line);border-radius:7px;padding:22px}
.panel h2{font-size:16px;font-weight:650;margin:0 0 18px}
label{display:block;margin:17px 0 7px;font-size:13px;font-weight:600}
label:first-of-type{margin-top:0}
textarea,select{width:100%;background:white;color:var(--ink);font:inherit;font-size:14px;border:1px solid #c8d1db;border-radius:5px;padding:11px 12px;outline:none}
textarea{resize:vertical;min-height:85px}#descricao{min-height:63px}
textarea:focus,select:focus,button:focus-visible,summary:focus-visible{border-color:#537eae;outline:3px solid var(--focus);outline-offset:1px}
select{height:44px}
.hint{font-size:12px;color:var(--sub);margin:6px 0 0}
.actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-top:19px}
button{font:inherit;cursor:pointer;border-radius:5px;padding:10px 15px;border:1px solid #bdc9d6;background:white;color:var(--ink)}
button:hover{background:#f1f4f7}
button.primary{background:var(--navy);border-color:var(--navy);color:white;font-weight:600}
button.primary:hover{background:#193957}
button:disabled{opacity:.65;cursor:wait}
.samples{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:15px}
.samples span{font-size:12px;color:var(--sub);margin-right:3px}
.samples button{padding:4px 9px;font-size:12px;background:#f9fafb}
.result-empty{height:100%;min-height:268px;display:flex;align-items:center;justify-content:center;text-align:center;color:#728095;font-size:14px;border:1px dashed var(--line);border-radius:5px}
.result{display:none}.result.visible{display:block}
.eyebrow{color:var(--sub);font-size:12px}
.category{font-size:27px;font-weight:700;line-height:1.25;margin:10px 0;color:var(--navy);overflow-wrap:anywhere}
.description{margin:0;color:var(--sub)}
.result hr{margin:19px 0;border:0;border-top:1px solid var(--line)}
.result .metadata{margin:15px 0 0;font-size:13px;color:var(--sub)}
.result .metadata span{display:block;margin:5px 0}
.inline-error{color:#a72e2c}
details{border-top:1px solid var(--line);padding-top:13px;margin-top:20px;color:var(--sub);font-size:12px}
summary{cursor:pointer;font-weight:600;color:#3c526c;user-select:none}
.details-content{padding:5px 0 0}.details-content p{margin:8px 0}
.compare{margin-top:16px;border-top:1px solid var(--line);padding-top:14px}
.compare h3{font-size:13px;margin:0 0 9px}
.compare-line{display:grid;grid-template-columns:120px 1fr;gap:8px;padding:6px 0;border-bottom:1px solid #eef0f3}
.compare-line b{font-weight:650;color:var(--navy)}
.history{margin-top:16px}.history .heading{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:9px}.history h2{margin:0}
.tiny-button{font-size:12px;padding:5px 10px}
.tablebox{width:100%;overflow-x:auto}
table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}
th{color:var(--sub);font-weight:600;background:#fafbfc;border-bottom:1px solid var(--line)}
th,td{padding:10px;border-bottom:1px solid #e9edf1;vertical-align:top}
tr:last-child td{border-bottom:0}
.col-title{width:70%}.empty-history{color:var(--sub);font-size:13px;padding:14px 0}
footer{color:var(--sub);font-size:12px;padding:18px 0 28px;border-top:1px solid var(--line)}
@media(max-width:720px){main{padding-top:24px}.work{grid-template-columns:1fr}.panel{padding:18px}.head{align-items:flex-start;padding:15px 0;min-height:70px}.result-empty{min-height:130px}.col-title{width:auto}}

/* Versão V5: tela única e objetiva, sem cabeçalho ou rodapé */
body{background:#f6f7f9}
.container{width:min(880px,calc(100% - 40px))}
main{padding:42px 0 48px}
h1{font-size:25px;margin-bottom:5px}
.lead{margin:0 0 20px}
.work{display:block}
.panel{padding:24px;border-radius:8px}
.work .panel h2{margin:0 0 18px}
.field-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}
.field{min-width:0}
.field label,.mode-field label{margin:0 0 7px}
.field textarea{min-height:91px}
#descricao{min-height:91px}
.toolbar{display:flex;align-items:end;justify-content:space-between;gap:18px;margin-top:19px}
.mode-field{width:250px;max-width:100%}
.actions{margin-top:0}
.samples{margin-top:16px}
.results-area{border-top:1px solid var(--line);padding-top:22px;margin-top:25px}
.results-area h2{font-size:16px!important;margin-bottom:14px!important}
.result.visible{display:block}
.result .category{font-size:25px;margin:5px 0 8px}
.result .metadata{margin-top:10px}
.result hr{margin:12px 0}
.history{margin-top:16px}
@media(max-width:720px){
 main{padding:27px 0 36px}
 .field-grid{grid-template-columns:1fr;gap:16px}
 .toolbar{align-items:stretch;flex-direction:column;gap:12px}
 .mode-field{width:100%}
 .actions{align-items:stretch}
 .actions button{flex:1}
 .panel{padding:18px}
}

/* V5: campo opcional só aparece ao clicar no título da seção. */
.field-grid{display:block}
.field-grid .field textarea{min-height:82px}
.optional-description{border:0;padding:0;margin:14px 0 2px;color:var(--ink);font-size:13px}
.optional-description > summary{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:550;color:var(--navy);cursor:pointer;list-style:none;padding:5px 0}
.optional-description > summary::-webkit-details-marker{display:none}
.optional-description > summary::before{content:'+';display:inline-grid;place-items:center;width:17px;height:17px;border:1px solid var(--line);border-radius:4px;font-size:15px;line-height:1;font-weight:400;color:var(--navy)}
.optional-description[open] > summary::before{content:'−'}
.optional-description[open] > summary{margin-bottom:11px}
.optional-body{padding:0 0 7px}
.optional-body label{margin:0 0 7px}
.optional-body textarea{min-height:80px}
.optional-body .hint{margin-top:4px}

/* V6 — distribuição para telas largas, sem trocar o modelo nem o HTML funcional */
:root { --background:#eff2f5; --line:#d8dee6; }
body{background:var(--background)}
main.container{
  width:min(1220px, calc(100% - 72px));
  display:grid;
  grid-template-columns:minmax(0,1.8fr) minmax(310px,.95fr);
  align-content:start;
  column-gap:20px;
  padding:38px 0 34px;
}
main.container > h1, main.container > .lead{grid-column:1 / -1}
main.container > h1{font-size:27px; margin-bottom:3px}
main.container > .lead{font-size:13px; margin-bottom:17px}
main.container > .work {grid-column:1;grid-row:3; min-width:0}
main.container > .history {grid-column:2;grid-row:3; align-self:start; margin:0; min-width:0}
.panel{padding:21px 22px; box-shadow:0 1px 2px rgba(18,32,48,.025)}
.work .panel h2{margin-bottom:14px;font-size:15px}
.field-grid .field textarea{min-height:70px;height:76px}
.optional-description{margin:9px 0 0}
.toolbar{margin-top:13px; gap:12px}
.mode-field{width:225px}
.actions{gap:8px}
.actions button{padding:9px 12px}
.samples{margin-top:13px}
.results-area{margin-top:18px;padding-top:16px}
.result .category{margin:3px 0 4px}
.history h2{font-size:15px}
.history .heading{margin-bottom:8px}
.history table{font-size:12px;table-layout:fixed}
.history th,.history td{padding:9px 8px; overflow-wrap:anywhere}
.history th:first-child,.history td:first-child{width:76%}
.history .tablebox{max-height:380px;overflow-y:auto}
.history .empty-history{padding:7px 0 0}
@media (max-width:950px){
  main.container{width:min(780px,calc(100% - 36px));display:block;padding:28px 0 32px}
  main.container > .history{margin-top:16px}
}
@media (max-width:600px){
  main.container{width:calc(100% - 24px);padding:18px 0 28px}
  .panel{padding:17px}
  main.container > h1{font-size:24px}
  .toolbar{flex-direction:column;align-items:stretch}
  .mode-field{width:100%}
  .actions{width:100%}
  .actions button{flex:1}
}

/* V7: fluxo em uma coluna, historico recolhivel e sem colunas vazias */
main.container {
  width:min(1160px,calc(100% - 56px));
  display:block;
  padding:30px 0 36px;
}
main.container > h1 {font-size:26px; margin-bottom:3px}
main.container > .lead {margin-bottom:16px}
main.container > .work {width:100%;min-width:0}
.work > .panel {padding:21px 24px}
.field-grid .field textarea {height:72px;min-height:72px}
.optional-description {margin-top:8px}
.toolbar {margin-top:11px}
.samples {margin-top:11px}
.results-area {margin-top:16px;padding-top:15px}
/* Historico compacto abaixo da analise e fechado por padrao */
details.history-toggle {
  display:block;
  margin:14px 0 0;
  padding:0;
  border:1px solid var(--line);
  border-radius:7px;
  background:white;
  box-shadow:0 1px 2px rgba(18,32,48,.025);
  color:var(--ink);
  font-size:14px;
}
.history-toggle > summary.history-summary {
  display:flex;align-items:center;justify-content:space-between;gap:14px;
  min-height:54px;padding:15px 22px;
  list-style:none;cursor:pointer;color:var(--ink);font-size:15px;font-weight:600;
}
.history-toggle > summary.history-summary::-webkit-details-marker {display:none}
.history-summary .summary-right {display:inline-flex;align-items:center;gap:15px;color:var(--sub);font-size:12px;font-weight:400}
.history-summary .summary-caret {display:inline-block;font-size:17px;line-height:1;transition:transform .15s ease}
.history-toggle[open] .summary-caret {transform:rotate(180deg)}
.history-toggle[open] > summary.history-summary {border-bottom:1px solid var(--line)}
.history-body {padding:10px 22px 14px}
.history-body .history-actions {display:flex;justify-content:flex-end;margin-bottom:9px}
.history-body .tablebox {max-height:270px;overflow:auto}
.history-body th,.history-body td {padding:9px 10px}
.history-body .empty-history {padding:4px 0 6px}
@media(max-width:800px) {
  main.container {width:calc(100% - 36px);padding:24px 0 30px}
  .work > .panel {padding:18px}
  .history-toggle > summary.history-summary {padding:14px 17px}
  .history-body {padding:10px 17px 14px}
}
@media(max-width:600px) {
  main.container {width:calc(100% - 24px);padding:18px 0 26px}
  .work > .panel {padding:16px}
  .history-summary .summary-right {gap:8px}
}

/* V8 — leitura confortável em monitores e menor margem lateral */
:root {
  --background: #eef1f4;
  --line: #d3dae3;
}
body {
  background: var(--background);
  font-size: 16px;
  line-height: 1.55;
}
main.container {
  width: min(1600px, calc(100% - clamp(28px, 4vw, 76px)));
  max-width: none;
  margin: 0 auto;
  padding: clamp(22px, 3vw, 42px) 0 40px;
}
main.container > h1 {
  font-size: clamp(28px, 2.25vw, 34px);
  line-height: 1.25;
  letter-spacing: -.35px;
  margin-bottom: 6px;
}
main.container > .lead {
  font-size: 16px;
  line-height: 1.5;
  margin-bottom: 19px;
}
.work > .panel {
  padding: clamp(22px, 2.5vw, 34px);
}
.work .panel h2,
.results-area h2 {
  font-size: 19px !important;
  line-height: 1.3;
  margin-bottom: 18px !important;
}
.field label,
.mode-field label,
.optional-body label {
  font-size: 16px;
  margin-bottom: 9px;
}
textarea, select {
  font-size: 17px;
  line-height: 1.5;
  padding: 12px 14px;
}
.field-grid .field textarea {
  height: 90px;
  min-height: 90px;
}
.optional-body textarea {
  min-height: 88px;
}
.optional-description {
  margin-top: 11px;
  font-size: 15px;
}
.optional-description > summary {
  font-size: 15px;
  padding: 8px 0;
}
.optional-description > summary::before {
  width: 20px;
  height: 20px;
  font-size: 16px;
}
.toolbar {
  margin-top: 15px;
  justify-content: flex-start;
  align-items: end;
  gap: clamp(18px, 3vw, 50px);
}
.mode-field {
  width: 280px;
  max-width: 100%;
}
select {
  min-height: 49px;
  height: 49px;
}
.actions {gap: 11px}
.actions button,
button {
  font-size: 16px;
}
.actions button {
  min-height: 49px;
  padding: 11px 19px;
}
.samples {
  gap: 9px;
  margin-top: 17px;
}
.samples span {
  font-size: 14px;
  margin-right: 2px;
}
.samples button {
  font-size: 14px;
  padding: 7px 12px;
}
.results-area {
  margin-top: 22px;
  padding-top: 21px;
}
.eyebrow {font-size: 14px}
.result .category {
  font-size: clamp(29px, 2.5vw, 34px);
  margin: 5px 0 7px;
}
.result .description {font-size: 16px}
.result .metadata {
  font-size: 15px;
  margin-top: 12px;
}
.result .metadata span {margin: 7px 0}
.result hr {margin: 17px 0}
.result details {
  font-size: 14px;
  padding-top: 15px;
  margin-top: 18px;
}
.result details summary {font-size: 14px}
.details-content p {margin: 9px 0}
.hint {font-size: 14px}
.compare h3 {font-size: 16px}
.compare-line {font-size: 15px; grid-template-columns: 155px 1fr}
details.history-toggle {margin-top: 16px}
.history-toggle > summary.history-summary {
  min-height: 67px;
  padding: 19px clamp(22px, 2.5vw, 34px);
  font-size: 17px;
}
.history-summary .summary-right {font-size: 14px;gap: 14px}
.history-summary .summary-caret {font-size: 19px}
.history-body {padding: 15px clamp(22px, 2.5vw, 34px) 20px}
.history-body table,
.history-body .empty-history {font-size: 15px}
.history-body th, .history-body td {padding: 12px 13px}
.history-body .tiny-button {font-size: 14px;padding: 7px 13px}
@media (max-width: 750px) {
  main.container {width: calc(100% - 28px);padding: 22px 0 32px}
  main.container > h1 {font-size: 26px}
  main.container > .lead {font-size: 15px}
  .work > .panel {padding: 20px}
  .toolbar {align-items: stretch; flex-direction: column;gap: 13px}
  .mode-field {width: 100%}
  .actions {width: 100%;display:flex}
  .actions button {flex: 1; min-width: 0}
  .samples {margin-top: 14px}
  .history-toggle > summary.history-summary {padding: 16px 20px}
  .history-body {padding: 10px 20px 14px}
}
@media (max-width: 420px) {
  .work > .panel {padding: 16px}
  main.container {width: calc(100% - 20px)}
  .actions {flex-direction: column}
  .history-toggle > summary.history-summary {padding: 14px 16px}
  .history-body {padding: 10px 16px 14px}
}


html, body {
    background: #ffffff !important;
}

main.container {
    background: #ffffff !important;
}

.panel, details.history {
    background: #ffffff !important;
    border: 1px solid #e2e6eb !important;
}

input, textarea, select {
    background: #ffffff !important;
}
</style>
</head>
<body>
<main class="container">
<h1>Classificação de commits</h1>
<p class="lead">Informe uma mensagem para identificar sua categoria: fix, feat, docs, refactor ou test.</p>
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
<div id="placeholder" hidden></div>
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
  $('area-resultado').hidden=false;$('placeholder').hidden=true;$('result').classList.add('visible');
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
 $('area-resultado').hidden=false;$('placeholder').hidden=true;$('result').classList.add('visible');
 $('result-label').textContent='Comparação dos modelos';$('classe').textContent='Com e sem prefixo';$('classe').classList.remove('inline-error');
 $('explicacao').textContent='Classificações para a mesma mensagem.';$('metadata').replaceChildren();$('detalhes-conteudo').replaceChildren();$('detalhes').open=false;
 $('cmp-com').textContent=d.com_prefixo?.categoria_sugerida||'Sem sugestão';$('cmp-sem').textContent=d.sem_prefixo?.categoria_sugerida||'Sem sugestão';$('comparacao').hidden=false;
 }catch(err){setResult('Não foi possível comparar',err.message,true)}finally{btn.disabled=false;btn.textContent='Comparar modelos'}
});
$('limpar').addEventListener('click',()=>{HIST.length=0;drawHistory()});
checkStatus();drawHistory();
</script>
</body>
</html>'''


def situacao(artefatos: Path) -> dict:
    """Mostra metadados apenas de manifesto local; nao carrega joblib aqui."""
    mp = artefatos / MANIFESTO
    pronto = mp.is_file() and (artefatos / MODEL_COM).is_file() and (artefatos / MODEL_SEM).is_file()
    dados = {}
    if mp.is_file():
        try:
            dados = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pronto = False
    return {
        "pronto": pronto,
        "oof": dados.get("paridade_oof", {}) if isinstance(dados, dict) else {},
    }


def classificar(dados: object, artefatos: Path) -> dict:
    if not isinstance(dados, dict):
        raise ValueError("Envie um objeto JSON.")
    titulo, descricao, modo = dados.get("titulo"), dados.get("descricao", ""), dados.get("modo", "auto")
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 500 or "\n" in titulo or "\r" in titulo:
        raise ValueError("Informe um título de uma linha, entre 1 e 500 caracteres.")
    if not isinstance(descricao, str) or len(descricao) > 2500:
        raise ValueError("Descrição inválida (máximo 2500 caracteres).")
    if modo not in ("auto", "com_prefixo", "sem_prefixo"):
        raise ValueError("Modo de classificação inválido.")
    # O motor V12 e a revisao de escrita sao exatamente os existentes no CommitX.
    classificacao = analisar_modelo(artefatos, titulo, modo)
    escrita = revisar_escrita(titulo, descricao)
    return {"classificacao": classificacao, "escrita": escrita}


def criar_handler(artefatos: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, dados: dict):
            payload = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            rota = urlsplit(self.path).path
            if rota == "/api/status":
                self._json(200, situacao(artefatos))
                return
            if rota not in ("/", "/index.html"):
                self.send_error(404)
                return
            payload = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            rota = urlsplit(self.path).path
            if rota not in ("/api/classificar", "/api/comparar"):
                self.send_error(404)
                return
            origem = self.headers.get("Origin", "")
            permitida = f"http://127.0.0.1:{self.server.server_port}"
            if origem and origem != permitida:
                self._json(403, {"erro": "Origem não permitida."})
                return
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                self._json(415, {"erro": "Content-Type deve ser application/json."})
                return
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if not 2 <= tamanho <= 8192:
                    raise ValueError("JSON vazio ou muito grande.")
                dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                if rota == "/api/comparar":
                    # Mesma entrada, pipeline real de cada modo: nenhuma predicao ficticia.
                    com = classificar({**dados, "modo": "com_prefixo"}, artefatos)["classificacao"]
                    sem = classificar({**dados, "modo": "sem_prefixo"}, artefatos)["classificacao"]
                    self._json(200, {"com_prefixo": com, "sem_prefixo": sem})
                else:
                    self._json(200, classificar(dados, artefatos))
            except (ValueError, UnicodeError, OSError) as erro:
                self._json(400, {"erro": str(erro)})
            except Exception as erro:
                # Mostrar detalhes somente no terminal, nao ao navegador.
                print(f"[Erro de classificacao] {type(erro).__name__}: {erro}", file=sys.stderr)
                self._json(500, {"erro": "Falha interna. Verifique o terminal do CommitX."})
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument("--artefatos", type=Path, default=PADRAO)
    args = parser.parse_args(argv)
    if not 1024 <= args.porta <= 65535:
        parser.error("Porta deve estar entre 1024 e 65535.")
    pasta = args.artefatos.resolve()
    if not situacao(pasta)["pronto"]:
        print("AVISO: Modelos finais V12 não encontrados na pasta:", pasta)
        print("O site abre para demonstração, mas a classificação só funcionará após restaurar os artefatos locais de treinamento.")
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), criar_handler(pasta))
    print(f"\nCommitX V12 disponível em http://127.0.0.1:{args.porta}")
    print("Sem internet. Sem treinar ou modificar dados. Ctrl+C encerra.\n", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando CommitX.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
