import argparse
import json
import re
from pathlib import Path

import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

# 50 exemplos SINTÉTICOS. Formato: categoria|título|descrição.
# Os rótulos foram definidos na criação e precisam de revisão humana.
DADOS = """
fix|fix(admin): corrigir paginação de usuários|A segunda página repetia os registros da primeira.
fix|Impedir divisão por zero no cálculo da média|A lista vazia causava uma exceção.
fix|fix(login): renovar sessão expirada|O usuário era desconectado durante a navegação.
fix|Corrigir desconto aplicado duas vezes no carrinho|
fix|fix(api): tratar resposta nula do servidor|A tela travava quando o serviço não retornava dados.
fix|Corrigir data exibida com um dia de atraso|
fix|fix(upload): impedir perda de arquivos com nomes iguais|Preserva ambos os arquivos usando identificadores únicos.
fix|Restaurar botão de salvar que parou de responder|
fix|fix(busca): corrigir resultados com acentos|A busca não encontrava palavras acentuadas.
fix|Corrigir bug que permitia estoque negativo|Bloqueia a venda quando não há unidades disponíveis.
feat|feat(conta): adicionar recuperação de senha|Permite solicitar um link por email.
feat|Permitir exportação dos relatórios em PDF|
feat|feat(perfil): permitir envio de foto|O usuário pode escolher uma imagem para o perfil.
feat|Adicionar filtro de produtos por faixa de preço|
feat|feat(chat): permitir envio de mensagens de voz|Disponibiliza gravação e reprodução de áudio.
feat|Criar opção de pagamento com Pix|
feat|feat(painel): incluir gráfico de vendas mensais|Mostra os totais agrupados por mês.
feat|Disponibilizar autenticação em duas etapas|Solicita um código adicional no acesso.
feat|feat(agenda): enviar lembretes de compromissos|Notifica o usuário antes do horário marcado.
feat|Adicionar suporte ao idioma espanhol|
docs|docs(readme): explicar instalação do projeto|Descreve as dependências necessárias.
docs|Documentar parâmetros da API de pagamentos|
docs|docs(guia): incluir exemplo de autenticação|Mostra como informar o token na requisição.
docs|Corrigir link do manual de configuração|
docs|docs: descrever variáveis de ambiente|Explica a finalidade de cada configuração.
docs|Traduzir instruções de contribuição para português|
docs|docs(api): atualizar exemplos de resposta|Alinha a documentação ao formato já utilizado.
docs|Acrescentar instruções para executar os testes|Documenta os comandos disponíveis no projeto.
docs|docs: explicar arquitetura no guia técnico|Apresenta a responsabilidade dos módulos.
docs|Revisar erros de digitação na documentação|
refactor|refactor(auth): extrair validação para função própria|Mantém as regras e o resultado do login.
refactor|Renomear variáveis do cálculo de frete|Torna os nomes descritivos sem alterar o cálculo.
refactor|refactor(api): remover duplicação entre controladores|Compartilha a lógica existente preservando as respostas.
refactor|Separar acesso ao banco da lógica de negócio|Preserva o comportamento das operações.
refactor|refactor(carrinho): simplificar condicionais|Mantém os mesmos descontos em cada situação.
refactor|Dividir classe de relatórios em módulos menores|Não altera os relatórios produzidos.
refactor|refactor: centralizar constantes de configuração|Substitui valores repetidos sem mudar seus valores.
refactor|Extrair formatação de moeda para função compartilhada|
refactor|refactor(busca): reorganizar construção da consulta|Mantém os mesmos filtros e resultados.
refactor|Remover função interna sem referências no código|
test|test(auth): cobrir tentativa de login inválido|Verifica a resposta para senha incorreta.
test|Adicionar testes unitários do cálculo de frete|
test|test(api): verificar resposta para recurso inexistente|Confere o código HTTP e a mensagem retornada.
test|Criar teste de integração do cadastro de usuários|
test|test(carrinho): testar combinação de cupons|Inclui cenários com descontos simultâneos.
test|Adicionar casos de teste para datas bissextas|
test|test(upload): simular falha na transferência|Verifica o tratamento de interrupção da conexão.
test|Substituir serviço externo por mock nos testes|Evita chamadas reais durante a suíte.
test|test: verificar ordenação dos resultados da busca|Confere a sequência de itens retornados.
test|Corrigir expectativa desatualizada no teste de estoque|
"""

CLASSES = ["fix", "feat", "docs", "refactor", "test"]
PREFIXO = re.compile(r"^[a-zA-Z]+(?:\([^()]+\))?!?:[ \t]*")


def preparar(titulo, descricao=""):
    # Exclui o prefixo para o modelo não apenas copiar o rótulo.
    return (PREFIXO.sub("", titulo.strip()) + " " + descricao).strip()


def criar_modelo():
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            strip_accents="unicode", ngram_range=(1, 2)
        )),
        ("modelo", LogisticRegression(max_iter=1000, random_state=42)),
    ])


def avaliar(textos, rotulos):
    treino, teste = train_test_split(
        list(range(len(textos))), test_size=0.2,
        random_state=42, stratify=rotulos,
    )
    modelo = criar_modelo()
    modelo.fit([textos[i] for i in treino], [rotulos[i] for i in treino])
    reais = [rotulos[i] for i in teste]
    previstos = modelo.predict([textos[i] for i in teste])

    maioria = DummyClassifier(strategy="most_frequent")
    maioria.fit([[0]] * len(treino), [rotulos[i] for i in treino])
    referencia = maioria.predict([[0]] * len(teste))

    relatorio = {
        "origem": "50 exemplos sintéticos; avaliação apenas didática",
        "sklearn": sklearn.__version__,
        "semente": 42,
        "ids_treino": treino,
        "ids_teste": teste,
        "macro_f1": f1_score(reais, previstos, average="macro"),
        "macro_f1_maioria": f1_score(
            reais, referencia, labels=CLASSES,
            average="macro", zero_division=0,
        ),
        "por_classe": classification_report(
            reais, previstos, labels=CLASSES,
            output_dict=True, zero_division=0,
        ),
        "ordem_matriz": CLASSES,
        "matriz_linhas_reais_colunas_previstas": confusion_matrix(
            reais, previstos, labels=CLASSES
        ).tolist(),
        "previsoes": [
            {"texto": textos[i], "real": real, "prevista": str(prevista)}
            for i, real, prevista in zip(teste, reais, previstos)
        ],
    }
    pasta = Path("resultados")
    pasta.mkdir(exist_ok=True)
    (pasta / "relatorio.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(classification_report(reais, previstos, zero_division=0))
    print(f"Macro-F1: {relatorio['macro_f1']:.3f}")
    print(f"Referência de maioria: {relatorio['macro_f1_maioria']:.3f}")
    print("Relatório salvo em resultados/relatorio.json")
    print("Teste com apenas 10 exemplos sintéticos. Não mede desempenho real.")


def analisar(textos, rotulos, titulo, descricao):
    modelo = criar_modelo().fit(textos, rotulos)
    texto = preparar(titulo, descricao)
    cabecalho = re.fullmatch(
        r"([a-zA-Z]+)(?:\([^()]+\))?!?:[ \t]+\S.*", titulo.strip()
    )
    declarado = cabecalho.group(1) if cabecalho else None
    print("Tipo declarado:", declarado or "não identificado")

    if modelo.named_steps["tfidf"].transform([texto]).nnz:
        print("Categoria sugerida:", modelo.predict([texto])[0])
    else:
        print("Categoria sugerida: sem termos conhecidos para classificar.")

    print("A previsão pode errar. O modelo conhece apenas:", ", ".join(CLASSES))
    print("\nRevisão de escrita por regras; não é uma nota de clareza:")
    if not cabecalho:
        print("- Se adotar Conventional Commits, use tipo(escopo): resumo.")
    if re.search(r"\b(bug|bugs|ajustes?|melhorias?|coisas?)\b", titulo.lower()):
        print("- Confira se a expressão vaga identifica um comportamento específico.")
    if not descricao.strip():
        print("- Se o título não bastar, acrescente o problema e o resultado esperado.")
    print("- Revise se a mensagem informa o que mudou e, quando necessário, por quê.")
    print("Só o diff permite verificar se a mensagem corresponde ao código.")
    print("Ausência de alertas não comprova clareza.")


def main():
    parser = argparse.ArgumentParser(description="Analisador didático de commits")
    parser.add_argument("comando", choices=["avaliar", "analisar"])
    parser.add_argument("titulo", nargs="?")
    parser.add_argument("--descricao", default="")
    args = parser.parse_args()
    linhas = [linha.split("|", 2) for linha in DADOS.strip().splitlines()]
    textos = [preparar(titulo, corpo) for _, titulo, corpo in linhas]
    rotulos = [categoria for categoria, _, _ in linhas]

    if args.comando == "avaliar":
        avaliar(textos, rotulos)
    else:
        if not args.titulo or not args.titulo.strip():
            parser.error("Informe um título entre aspas após analisar.")
        if not preparar(args.titulo):
            parser.error("Descreva a mudança após o prefixo.")
        analisar(textos, rotulos, args.titulo, args.descricao)


if __name__ == "__main__":
    main()
