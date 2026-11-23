"""Versao final (congelada) do CommitX V12: treinar, verificar e inferir.

Este modulo NAO seleciona hiperparametros. Reproduz a variante exploratoria
v12_extra_030 (C=0.3, sinais V11=0.5, extras V12=0.30), com 397 rotulos.
O conjunto de teste e as particoes reservadas NUNCA sao acessados.

Uso, na raiz do CommitX::
    python -m commitx.v12_final treinar
    python -m commitx.v12_final analisar 'refactor: Extract method'
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn
from scipy.sparse import csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from .comparacao_prefixos import CLASSES, prefixo, raw_titles
from .escrita import parse_cabecalho, texto_modelo
from .experimento_v3 import carregar_treino, componentes
from .foco_docs_refactor_v10 import pesos_do_fold
from .sinais_semanticos_v11 import SinaisSemanticos

ENTRADA_PADRAO = Path('resultados/preparacao-inicial/commits_preparados.csv')
BANCO_PADRAO = Path('resultados/rotulagem/avaliacoes.sqlite3')
REF_COM_PADRAO = Path('resultados/experimento-v12-paridade-corrigida-01/previsoes_oof.csv')
REF_SEM_PADRAO = Path('resultados/experimento-v12-sem-prefixos-01/previsoes_oof.csv')
SAIDA_PADRAO = Path('resultados/modelo-final-v12-01')
MODEL_COM = 'v12_com_prefixo.joblib'
MODEL_SEM = 'v12_sem_prefixo.joblib'
MANIFESTO = 'manifesto.json'
SEMENTE = 42

# Exatamente os padroes da variante v12_extra_030 previamente verificada.
PADROES_EXTRAS = {
    'troca_implementacao': r'\b(?:instead of|replace\b.{0,65}\bwith|convert\b.{0,65}\bto|newer method|use ordereddict)\b',
    'reestrutura_interna': r'\b(?:extract\w*|restructur\w*|reorganiz\w*|simplif\w*|refactor\w*|rework)\b',
    'limpeza_remocao': r'\b(?:remove (?:unused|unnecessary)|drop\b.{0,40}\bcolumn|delete\b.{0,40}\bcondition|reduce the name)\b',
    'objeto_estrutural': r'\b(?:method|function|class|dispatcher|framework|properties|inherit|helper)\b',
    'fix_contexto': r'\b(?:fix|bug|crash|broken|error|failure|incorrect)\b',
    'feat_contexto': r'\b(?:add|implement|introduce|support|create|new migration)\b',
    'test_contexto': r'\b(?:test\w*|assert\w*|coverage|pytest|unittest|specs?)\b',
    'docs_objeto': r'\b(?:readme|documentation|docstrings?|guides?|tutorials?|changelog)\b',
    'migracao': r'\b(?:migrat\w*|database schema)\b',
}
COMPILADOS_EXTRAS = tuple(re.compile(v, re.I) for v in PADROES_EXTRAS.values())


class SinaisContextuaisV12(BaseEstimator, TransformerMixin):
    """Transformador importavel: permite salvar e recarregar sem __main__."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return csr_matrix(np.asarray([
            [float(bool(p.search(texto))) for p in COMPILADOS_EXTRAS]
            for texto in X
        ], dtype=np.float64).reshape(-1, len(COMPILADOS_EXTRAS)))


def novo_modelo_v12(pesos):
    """Reproduz EXATAMENTE o pipeline 'v12_extra_030'."""
    features = FeatureUnion([
        ('palavras', TfidfVectorizer(
            ngram_range=(1, 2), strip_accents='unicode',
            sublinear_tf=True, max_features=50000,
        )),
        ('sinais_v11', SinaisSemanticos()),
        ('sinais_extra_v12', SinaisContextuaisV12()),
    ], transformer_weights={
        'palavras': 1.0,
        'sinais_v11': 0.5,
        'sinais_extra_v12': 0.30,
    })
    return Pipeline([
        ('tfidf', features),
        ('model', LinearSVC(C=0.3, class_weight=pesos, random_state=SEMENTE)),
    ])


def _ler_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as arq:
        return list(csv.DictReader(arq))


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as arq:
        for bloco in iter(lambda: arq.read(1024 * 1024), b''):
            digest.update(bloco)
    return digest.hexdigest()


def carregar_gold(entrada=ENTRADA_PADRAO, banco=BANCO_PADRAO):
    """Apenas particao de treino e rótulos existentes, sem escrever no SQLite."""
    registros = carregar_treino(entrada, banco)
    ids = [r['id'] for r in registros]
    if len(ids) != 397 or len(set(ids)) != 397:
        raise ValueError('V12 congelada exige exatamente os 397 IDs originais, sem duplicatas.')
    titulos = raw_titles(entrada, set(ids))
    x_com = [titulos[uid] for uid in ids]
    x_sem = [texto_modelo(t, '') for t in x_com]
    y = np.asarray([r['categoria'] for r in registros])
    grupos = componentes(registros)
    if len(set(grupos)) != 310 or set(y) != set(CLASSES):
        raise ValueError('Os grupos/classes diferem da base congelada da V12.')
    if any(not t.strip() for t in x_com + x_sem):
        raise ValueError('Título vazio após o pré-processamento.')
    return ids, x_com, x_sem, y, grupos


def verificar_paridade(ids, x_com, x_sem, y, grupos, referencia_com, referencia_sem):
    """Exige previsões idênticas às V12 COM e SEM prefixos, em OOF.

    Retorna métricas exploratórias guardadas no manifesto. O treino final é
    realizado APENAS depois dessa verificação e não usa os folds como teste.
    """
    refs_com = _ler_csv(referencia_com)
    refs_sem = _ler_csv(referencia_sem)
    if (len(refs_com) != len(ids) or len(refs_sem) != len(ids) or
            len({r['id'] for r in refs_com}) != len(ids) or
            len({r['id'] for r in refs_sem}) != len(ids)):
        raise ValueError('Referências OOF incompletas ou duplicadas.')
    a = {r['id']: r for r in refs_com}
    b = {r['id']: r for r in refs_sem}
    if set(ids) != set(a) or set(ids) != set(b):
        raise ValueError('IDs da V12 e das referências não coincidem.')
    for uid, xc, xs, label, grupo in zip(ids, x_com, x_sem, y, grupos):
        rc, rs = a[uid], b[uid]
        if (rc.get('titulo') != xc or rc.get('rotulo_registrado') != label or
                rc.get('grupo') != str(grupo) or
                rs.get('titulo_original') != xc or
                rs.get('titulo_sem_prefixo') != xs or
                rs.get('real') != label or rs.get('grupo') != str(grupo) or
                rc.get('v12_extra_030') != rs.get('v12_com_prefixo')):
            raise ValueError(f'Título, grupo, rótulo ou referência alterado: {uid}')
    folds = list(StratifiedGroupKFold(
        n_splits=5, shuffle=True, random_state=SEMENTE,
    ).split(np.zeros(len(ids)), y, grupos))
    previsto_com = [None] * len(ids)
    previsto_sem = [None] * len(ids)
    for n, (it, iv) in enumerate(folds, 1):
        if set(grupos[it]) & set(grupos[iv]):
            raise ValueError('Vazamento de grupo no fold de referência.')
        if set(y[it]) != set(CLASSES) or set(y[iv]) != set(CLASSES):
            raise ValueError('Fold de referência sem todas as classes.')
        pesos = pesos_do_fold(y[it], 1.75, 1.50)
        for textos, destino in ((x_com, previsto_com), (x_sem, previsto_sem)):
            m = novo_modelo_v12(pesos)
            m.fit([textos[int(i)] for i in it], y[it])
            for j, pred in zip(iv, m.predict([textos[int(i)] for i in iv])):
                if destino[int(j)] is not None:
                    raise ValueError('Previsão OOF duplicada.')
                destino[int(j)] = str(pred)
        print(f'Paridade V12: fold {n}/5', flush=True)
    dif_com = [uid for i, uid in enumerate(ids) if previsto_com[i] != a[uid].get('v12_extra_030')]
    dif_sem = [uid for i, uid in enumerate(ids) if previsto_sem[i] != b[uid].get('v12_sem_prefixo')]
    if dif_com or dif_sem:
        raise ValueError(
            f'Paridade falhou: COM={len(dif_com)}/397 divergências; '
            f'SEM={len(dif_sem)}/397. Exemplos: {(dif_com + dif_sem)[:3]}'
        )
    print('Paridade confirmada: 397/397 previsões COM e 397/397 SEM prefixos.')
    return {
        modo: {
            'acuracia_oof': float(accuracy_score(y, pred)),
            'macro_f1_oof': float(f1_score(y, pred, labels=list(CLASSES), average='macro', zero_division=0)),
            'previsoes_iguais': len(ids),
        }
        for modo, pred in [('com_prefixo', previsto_com), ('sem_prefixo', previsto_sem)]
    }


def treinar_e_salvar(saida=SAIDA_PADRAO, entrada=ENTRADA_PADRAO,
                     banco=BANCO_PADRAO, referencia_com=REF_COM_PADRAO,
                     referencia_sem=REF_SEM_PADRAO):
    """Congela dois modelos V12 com todos os 397 rótulos originais.

    Não sobrescreve caminhos existentes e não altera o SQLite. OOF não é
    acurácia do artefato final, treinado com TODOS os 397 registros.
    """
    saida = Path(saida)
    if saida.exists() or saida.is_symlink():
        raise FileExistsError(f'Não sobrescrever a pasta existente: {saida}')
    ids, x_com, x_sem, y, grupos = carregar_gold(entrada, banco)
    resultados = verificar_paridade(ids, x_com, x_sem, y, grupos,
                                    referencia_com, referencia_sem)
    pesos = pesos_do_fold(y, 1.75, 1.50)
    modelos = {
        'com_prefixo': novo_modelo_v12(pesos).fit(x_com, y),
        'sem_prefixo': novo_modelo_v12(pesos).fit(x_sem, y),
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.v12-final-', dir=saida.parent))
    try:
        arquivos = {}
        for nome, arq in (('com_prefixo', MODEL_COM), ('sem_prefixo', MODEL_SEM)):
            joblib.dump(modelos[nome], tmp / arq)
            arquivos[arq] = _sha256(tmp / arq)
        manifest = {
            'projeto': 'CommitX',
            'versao': 'V12-final-v12_extra_030',
            'modelo': 'TF-IDF palavra 1-2 + sinais V11 + sinais V12 + LinearSVC',
            'configuracao_congelada': {
                'C': 0.3, 'random_state': 42,
                'peso_sinais_v11': 0.5, 'peso_sinais_v12': 0.30,
                'fatores_peso_docs_refactor': [1.75, 1.50],
                'tfidf_ngram_range': [1, 2], 'tfidf_max_features': 50000,
            },
            'commits_rotulados': len(ids), 'grupos': len(set(grupos)),
            'classes': list(CLASSES),
            'contagem_por_classe': {c: int(sum(y == c)) for c in CLASSES},
            'preprocessamento': {
                'com_prefixo': 'titulo original como recebido',
                'sem_prefixo': 'texto_modelo(titulo, "")',
                'descricao_no_modelo': False,
            },
            'paridade_oof': resultados,
            'artefatos_sha256': arquivos,
            'entrada_sha256': _sha256(entrada),
            'referencias_sha256': {
                'com_prefixo': _sha256(referencia_com),
                'sem_prefixo': _sha256(referencia_sem),
            },
            'ambiente': {'python': sys.version.split()[0], 'scikit_learn': sklearn.__version__,
                         'numpy': np.__version__, 'joblib': joblib.__version__},
            'criado_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'limitacoes': [
                'Resultados OOF exploratorios: sinais e modelos foram escolhidos apos examinar a mesma base.',
                'Nao existe evidencia de acuracia em repositorios novos ou de confianca calibrada.',
                'Modelo COM prefixo pode reproduzir tipo declarado sem conhecer o codigo.',
                'A classificacao usa titulo, nao descricao nem diff.',
                '1603 candidatos com rotulos gerados por IA nao foram usados.',
                'Nao carregar joblib nao confiavel; pode executar codigo arbitrario.',
            ],
        }
        (tmp / MANIFESTO).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                                      encoding='utf-8')
        # Nome novo + comportamento sem sobrescrita. Nao alterar resultados anteriores.
        os.rename(tmp, saida)
        print('Modelo V12 final treinado e salvo em:', saida)
        return manifest
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def analisar_modelo(artefatos=SAIDA_PADRAO, titulo='', modo='auto'):
    """Retorna categoria e avisos sem falsificar probabilidades ou prova de intenção."""
    artefatos = Path(artefatos)
    titulo = titulo.strip()
    if not titulo:
        raise ValueError('Informe o título do commit.')
    if modo not in ('auto', 'com_prefixo', 'sem_prefixo'):
        raise ValueError('Modo inválido: auto, com_prefixo ou sem_prefixo.')
    tipo = parse_cabecalho(titulo)
    declarado = tipo['tipo'] if tipo else None
    avisos = [
        'Previsão baseada apenas no título; não confirma o diff nem a intenção real.',
        'A classe está limitada a fix, feat, docs, refactor e test.',
    ]
    if declarado and declarado not in CLASSES:
        avisos.append(f'Tipo declarado "{declarado}" está fora das cinco classes; sem sugestão.')
        return {'categoria_sugerida': None, 'tipo_declarado': declarado,
                'modo': None, 'margem_svm': None, 'avisos': avisos}
    escolhido = ('com_prefixo' if prefixo(titulo) else 'sem_prefixo') if modo == 'auto' else modo
    texto = titulo if escolhido == 'com_prefixo' else texto_modelo(titulo, '')
    if not texto.strip():
        avisos.append('Texto vazio após remover prefixo; sem sugestão.')
        return {'categoria_sugerida': None, 'tipo_declarado': declarado,
                'modo': escolhido, 'margem_svm': None, 'avisos': avisos}
    manifest_path = artefatos / MANIFESTO
    if not manifest_path.is_file():
        raise FileNotFoundError('Modelo V12 não treinado: ' + str(manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('versao') != 'V12-final-v12_extra_030':
        raise ValueError('Manifesto de modelo incompatível com V12 final.')
    nome = MODEL_COM if escolhido == 'com_prefixo' else MODEL_SEM
    caminho = artefatos / nome
    if not caminho.is_file() or _sha256(caminho) != manifest.get('artefatos_sha256', {}).get(nome):
        raise ValueError('Artefato ausente ou alterado: ' + str(caminho))
    # ATENCAO: joblib.load pode executar codigo; carregar somente artefato LOCAL confiavel.
    modelo = joblib.load(caminho)
    if modelo.named_steps['tfidf'].transform([texto]).nnz == 0:
        avisos.append('Nenhuma característica conhecida foi encontrada; sem sugestão.')
        return {'categoria_sugerida': None, 'tipo_declarado': declarado,
                'modo': escolhido, 'margem_svm': None, 'avisos': avisos}
    categoria = str(modelo.predict([texto])[0])
    pontuacoes = np.asarray(modelo.decision_function([texto]))[0]
    ordem = np.argsort(pontuacoes)[::-1]
    margem = float(pontuacoes[ordem[0]] - pontuacoes[ordem[1]])
    if declarado and declarado != categoria:
        avisos.append('Prefixo declarado e previsão divergem; isso não prova erro do autor.')
    if escolhido == 'com_prefixo':
        avisos.append('O modelo com prefixo pode usar o tipo declarado como atalho.')
    avisos.append('Margem SVM não é probabilidade nem confiança calibrada.')
    return {
        'categoria_sugerida': categoria, 'tipo_declarado': declarado,
        'modo': escolhido, 'margem_svm': round(margem, 4), 'avisos': avisos,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='acao', required=True)
    tr = sub.add_parser('treinar', help='Verificar paridade e salvar modelos V12 finais.')
    tr.add_argument('--saida', type=Path, default=SAIDA_PADRAO)
    tr.add_argument('--entrada', type=Path, default=ENTRADA_PADRAO)
    tr.add_argument('--banco', type=Path, default=BANCO_PADRAO)
    tr.add_argument('--ref-com', type=Path, default=REF_COM_PADRAO)
    tr.add_argument('--ref-sem', type=Path, default=REF_SEM_PADRAO)
    an = sub.add_parser('analisar', help='Classificar título com modelo V12 final salvo.')
    an.add_argument('titulo')
    an.add_argument('--artefatos', type=Path, default=SAIDA_PADRAO)
    an.add_argument('--modo', choices=('auto', 'com_prefixo', 'sem_prefixo'), default='auto')
    args = parser.parse_args(argv)
    try:
        if args.acao == 'treinar':
            res = treinar_e_salvar(args.saida, args.entrada, args.banco, args.ref_com, args.ref_sem)
            print('Paridade confirmada:', res['paridade_oof'])
        else:
            res = analisar_modelo(args.artefatos, args.titulo, args.modo)
            print(json.dumps(res, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as erro:
        parser.error(str(erro))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
