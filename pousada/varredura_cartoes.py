"""Varredura SOMENTE LEITURA dos textos já gravados à procura de números de cartão.

Uso (pelo dono, com o sistema parado ou não: o banco é aberto só para leitura):
    python app.py varrer-cartoes

O relatório traz apenas tabela, número (id) e campo. O número encontrado NUNCA é impresso nem guardado.
A limpeza é manual: abra a reserva, apague os números e escreva, por exemplo, "pago no cartão (final 1234)".
"""
import sqlite3

from .cartao import contem_numero_cartao

# (tabela, colunas de texto livre). Tabelas ausentes (banco mais antigo) são ignoradas.
CAMPOS_TEXTO = (
    ("reservas", ("nome", "extras", "o", "grupo", "motivo_cancelamento")),
    ("pedidos", ("nome", "contato", "observacao")),
    ("governanca_unidade", ("obs", "manutencao_motivo")),
    ("nota", ("texto", "motivo")),                        # logs imutáveis (013/012): só entram se alguém burlou a validação
    ("despesa_lancamento", ("descricao", "motivo")),
)
CHAVE = {"governanca_unidade": "unidade"}      # as demais usam "id"


def abrir_somente_leitura(caminho):
    """Conexão que não consegue gravar (modo ro do SQLite)."""
    uri = "file:%s?mode=ro" % caminho.replace("\\", "/").replace("?", "%3f").replace("#", "%23")
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def varrer(con):
    """Lista de achados: {"tabela", "id", "campo"}. Não devolve o texto."""
    achados = []
    for tabela, campos in CAMPOS_TEXTO:
        try:
            chave = CHAVE.get(tabela, "id")
            linhas = con.execute("SELECT %s, %s FROM %s" % (chave, ", ".join(campos), tabela)).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in linhas:
            for campo in campos:
                if contem_numero_cartao(r[campo]):
                    achados.append({"tabela": tabela, "id": r[chave], "campo": campo})
    return achados


def relatorio(achados):
    """Texto do relatório (sem nenhum conteúdo dos campos)."""
    if not achados:
        return "Nenhum número de cartão encontrado."
    linhas = ["%d campo(s) com aparência de número de cartão (apague os números e escreva só 'final 1234'):" % len(achados)]
    linhas += ["  %s nº %s, campo '%s'" % (a["tabela"], a["id"], a["campo"]) for a in achados]
    return "\n".join(linhas)


def executar(caminho_banco):
    """Abre o banco só para leitura, varre e devolve o relatório."""
    con = abrir_somente_leitura(caminho_banco)
    try:
        return relatorio(varrer(con))
    finally:
        con.close()
