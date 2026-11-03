"""Histórico de auditoria. Cada registro é gravado NA MESMA transação da operação que ele descreve.

Só entram diferenças dos campos a, i, f, n, p; o nome aparece apenas como "alterado".
O tipo de hóspede (sócio/convidado) entra com antes/depois; o valor da diária aparece só como "alterado".
Extras, observações, senhas e tokens NUNCA são gravados (há uma lista de chaves permitidas como segunda barreira).
"""
import json

from flask import g, request

from .regras import agora

CAMPOS_AUDITADOS = ("a", "i", "f", "n", "p")
# Segunda barreira: qualquer outra chave que chegue por engano é descartada.
CHAVES_PERMITIDAS = frozenset(CAMPOS_AUDITADOS) | {
    "nome", "status", "lote", "criadas", "ignoradas", "removidas", "sha256", "motivo", "arquivo",
    "papel", "ativo", "pedidos", "tipo", "diaria", "unidade", "situacao",
    "categoria", "itens", "estado", "placa", "forma"}       # despesas: só a categoria e a contagem, NUNCA valor nem descrição


def ator_atual(login_digitado=None):
    """Quem está agindo (usuário logado ou, no login que falhou, o texto digitado) e de qual IP."""
    u = g.get("usuario")
    return {"id": u["id"] if u else None,
            "login": u["login"] if u else (login_digitado or "")[:80],
            "ip": request.remote_addr or ""}


def _json(d):
    if d is None:
        return None
    limpo = {k: v for k, v in d.items() if k in CHAVES_PERMITIDAS and isinstance(v, (str, int, bool, type(None)))}
    return json.dumps(limpo, ensure_ascii=False, sort_keys=True)


def registrar(con, acao, entidade, entidade_id=None, antes=None, depois=None, ator=None):
    """Acrescenta uma linha ao histórico (use dentro da transação da operação)."""
    ator = ator or ator_atual()
    con.execute("INSERT INTO historico (em, usuario_id, usuario_login, acao, entidade, entidade_id, antes, depois, ip) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (agora(), ator["id"], ator["login"], acao, entidade, entidade_id, _json(antes), _json(depois), ator["ip"]))


def resumo_reserva(r):
    """Os campos auditados de uma reserva (linha do banco ou dicionário)."""
    return {c: r[c] for c in CAMPOS_AUDITADOS}


def diferenca(antes, depois):
    """(antes, depois) só com o que mudou nos campos auditados; nome mudou => depois['nome'] = 'alterado'.

    Tipo e diária só são comparados se 'depois' os trouxer (edição que não os enviou não mexe neles).
    A diária nunca é registrada com o número: só depois['diaria'] = 'alterado'."""
    a, d = {}, {}
    for c in CAMPOS_AUDITADOS:
        if antes[c] != depois[c]:
            a[c], d[c] = antes[c], depois[c]
    if antes["nome"] != depois["nome"]:
        d["nome"] = "alterado"
    if "tipo" in depois and antes["tipo"] != depois["tipo"]:
        a["tipo"], d["tipo"] = antes["tipo"], depois["tipo"]
    if "diaria_centavos" in depois and antes["diaria_centavos"] != depois["diaria_centavos"]:
        d["diaria"] = "alterado"
    return a, d
