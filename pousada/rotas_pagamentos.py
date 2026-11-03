"""Rotas de Pagamentos da conta: receber (dinheiro, Pix, cartão), estornar, listar, fechar e reabrir a conta.

PRIVACIDADE: pagamento é dado financeiro. Só sai para quem tem pagamentos.ver; o histórico recebe só a forma e a contagem
(nunca valor, motivo, NSU nem referência). NUNCA se guarda número de cartão (veja pagamentos.py). Trava de edição simultânea do
dinheiro: despesa_conta.versao (conta_versao), que sobe a cada lançamento, estorno, pagamento, fechamento e reabertura.
Duplo clique: 'chave' única por reserva. Tudo numa transação BEGIN IMMEDIATE (uma pessoa por vez mexe na conta).
"""
import sqlite3

from flask import Blueprint, current_app, g, jsonify, request

from . import despesas as desp
from . import pagamentos as pg
from .db import obter_con, transacao
from .despesas import Recusa
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import exige
from .rotas_despesas import MSG_FECHADA, _reserva
from .rotas_governanca import agora

bp = Blueprint("pagamentos", __name__)
FMT = "%Y-%m-%d %H:%M:%S"
_COLUNAS = ("reserva_id,tipo,forma,valor_centavos,recebido_centavos,troco_centavos,bandeira,modalidade,parcelas,autorizacao,"
            "referencia,itens,apto,em,usuario_id,usuario_login,chave,estorno_de,motivo,ip")


def _recusa(e):
    return ErroApi(e.mensagem, e.status)


def conferir_versao(conta, v):
    if conta["versao"] != v:
        raise ErroApi("A conta mudou desde que você a abriu. Confira os valores e tente de novo.", 409)


def conferir_conta_ativa_aberta(r, conta):
    if r["status"] != "ativa":
        raise ErroApi("Esta reserva está cancelada", 409)
    if conta["situacao"] != "aberta":
        raise ErroApi(MSG_FECHADA, 409)


def bump(con, rid):
    """Cria a conta se preciso e soma 1 na versão (mesma transação do que mudou)."""
    con.execute("INSERT OR IGNORE INTO despesa_conta (reserva_id) VALUES (?)", (rid,))
    con.execute("UPDATE despesa_conta SET versao = versao + 1 WHERE reserva_id=?", (rid,))


def _item_por_id(con, pid):
    rid = con.execute("SELECT reserva_id FROM pagamento WHERE id=?", (pid,)).fetchone()[0]
    return next(i for i in pg.itens(pg.linhas(con, rid)) if i["id"] == pid)


def _conferir_itens(con, rid, r, ids):
    for i in ids:
        if i == "diaria":
            ok = (r["diaria_centavos"] or 0) > 0
        else:
            ok = con.execute("SELECT 1 FROM despesa_lancamento WHERE id=? AND reserva_id=? AND tipo='lancamento'",
                             (int(i[1:]), rid)).fetchone() is not None
        if not ok:
            raise ErroApi("Há item da lista que não pertence a esta conta", 422)


@bp.route("/api/reservas/<int:rid>/pagamentos", methods=["GET"])
@exige("pagamentos.ver")
def listar(rid):
    con = obter_con()
    r = _reserva(con, rid)
    total, pago = pg.total_conta(con, r), pg.liquido(con, rid)
    cfg = current_app.config           # o que o formulário de recebimento precisa saber (limites do clube)
    return jsonify({"itens": pg.itens(pg.linhas(con, rid)), "conta": desp.conta(con, rid),
                    "config": {"max_parcelas": cfg["PAG_MAX_PARCELAS"], "parcela_min_centavos": cfg["PAG_PARCELA_MIN_CENTAVOS"],
                               "bandeiras": list(cfg["PAG_BANDEIRAS"])},
                    "total": {"conta_centavos": total, "pagamentos_centavos": pago, "saldo_centavos": total - pago}})


@bp.route("/api/reservas/<int:rid>/pagamentos", methods=["POST"])
@exige("pagamentos.receber")
def receber(rid):
    try:
        dados = pg.validar_recebimento(request.get_json(silent=True), current_app.config)
    except Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    try:
        with transacao(con):
            r = _reserva(con, rid)
            antigo = con.execute("SELECT id FROM pagamento WHERE reserva_id=? AND chave=?", (rid, dados["chave"])).fetchone()
            if antigo:                      # duplo clique: a mesma chave devolve o pagamento que já existe
                return jsonify(_item_por_id(con, antigo["id"])), 200
            conta = desp.conta(con, rid)
            conferir_conta_ativa_aberta(r, conta)
            if r["i"] > momento.strftime("%Y-%m-%d"):
                raise ErroApi("A hospedagem ainda não começou", 422)
            conferir_versao(conta, dados["conta_versao"])
            _conferir_itens(con, rid, r, dados["itens"])
            saldo = pg.saldo(con, r)
            if dados["valor_centavos"] > saldo:
                raise ErroApi("O valor passa do saldo a pagar (%s). Receba no máximo o saldo." % desp.reais(max(saldo, 0)), 422)
            if con.execute("SELECT COUNT(*) FROM pagamento WHERE reserva_id=? AND tipo='recebimento'", (rid,)).fetchone()[0] >= pg.MAX_PAGAMENTOS:
                raise ErroApi("Esta reserva já tem o máximo de %d pagamentos" % pg.MAX_PAGAMENTOS, 409)
            a = ator_atual()
            cur = con.execute("INSERT INTO pagamento (%s) VALUES (%s)" % (_COLUNAS, ",".join("?" * 20)),
                              (rid, "recebimento", dados["forma"], dados["valor_centavos"], dados["recebido_centavos"], dados["troco_centavos"],
                               dados["bandeira"], dados["modalidade"], dados["parcelas"], dados["autorizacao"], dados["referencia"],
                               ",".join(dados["itens"]), r["a"], momento.strftime(FMT), a["id"], a["login"], dados["chave"], None, "", a["ip"]))
            bump(con, rid)
            registrar(con, "pagamento_recebido", "reserva", rid, None, {"forma": dados["forma"], "itens": 1}, a)
            item = _item_por_id(con, cur.lastrowid)
    except sqlite3.IntegrityError:           # a mesma chave chegou em dois pedidos ao mesmo tempo
        raise ErroApi("Este pagamento já foi registrado ou a conta mudou. Confira a conta.", 409)
    return jsonify(item), 201


@bp.route("/api/pagamentos/<int:pid>/estorno", methods=["POST"])
@exige("pagamentos.estornar")
def estornar(pid):
    try:
        motivo = desp.validar_motivo(request.get_json(silent=True))
    except Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    try:
        with transacao(con):
            o = con.execute("SELECT * FROM pagamento WHERE id=?", (pid,)).fetchone()
            if not o:
                raise ErroApi("Pagamento não encontrado", 404)
            r = _reserva(con, o["reserva_id"])
            if o["tipo"] == "estorno":
                raise ErroApi("Este lançamento já é um estorno e não pode ser estornado", 409)
            if con.execute("SELECT 1 FROM pagamento WHERE estorno_de=?", (pid,)).fetchone():
                raise ErroApi("Este pagamento já foi estornado", 409)
            conferir_conta_ativa_aberta(r, desp.conta(con, r["id"]))
            a = ator_atual()
            cur = con.execute("INSERT INTO pagamento (%s) VALUES (%s)" % (_COLUNAS, ",".join("?" * 20)),
                              (r["id"], "estorno", o["forma"], -o["valor_centavos"], None, None, o["bandeira"], o["modalidade"], o["parcelas"],
                               o["autorizacao"], o["referencia"], "", r["a"], momento.strftime(FMT), a["id"], a["login"], None, pid, motivo, a["ip"]))
            bump(con, r["id"])
            registrar(con, "pagamento_estornado", "reserva", r["id"], None, {"forma": o["forma"], "itens": 1}, a)
            item = _item_por_id(con, cur.lastrowid)
    except sqlite3.IntegrityError:
        raise ErroApi("Este pagamento já foi estornado", 409)
    return jsonify(item), 201


# ---------------------------------------------------------------- fechar e reabrir a conta

def _versao_do_corpo(corpo):
    try:
        return pg.versao_valida(corpo.get("conta_versao") if isinstance(corpo, dict) else None)
    except Recusa as e:
        raise _recusa(e)


@bp.route("/api/reservas/<int:rid>/conta/fechar", methods=["POST"])
@exige("despesas.conta")
def fechar(rid):
    versao, momento, con = _versao_do_corpo(request.get_json(silent=True)), agora(), obter_con()
    with transacao(con):
        r = _reserva(con, rid)
        conta = desp.conta(con, rid)
        conferir_conta_ativa_aberta(r, conta)
        conferir_versao(conta, versao)
        saldo = pg.saldo(con, r)
        if saldo != 0:
            raise ErroApi("A conta só pode ser fechada com saldo zero (saldo atual: %s)." % desp.reais(abs(saldo)), 409)
        con.execute("INSERT OR IGNORE INTO despesa_conta (reserva_id) VALUES (?)", (rid,))
        em, uid = momento.strftime(FMT), g.usuario["id"]
        con.execute("UPDATE despesa_conta SET situacao='fechada', quitacao='quitada', fechada_em=?, fechada_por=?, quitada_em=?, "
                    "quitada_por=?, versao=versao+1 WHERE reserva_id=?", (em, uid, em, uid, rid))
        a = ator_atual()
        con.execute("INSERT INTO conta_evento (reserva_id,acao,em,usuario_id,usuario_login,ip) VALUES (?,?,?,?,?,?)",
                    (rid, "fechar", em, a["id"], a["login"], a["ip"]))
        registrar(con, "conta_fechada", "reserva", rid, {"situacao": "aberta"}, {"situacao": "fechada"}, a)
        return jsonify({"conta": desp.conta(con, rid)}), 200


@bp.route("/api/reservas/<int:rid>/conta/reabrir", methods=["POST"])
@exige("conta.reabrir")
def reabrir(rid):
    corpo = request.get_json(silent=True)
    try:
        motivo = desp.validar_motivo(corpo)
    except Recusa as e:
        raise _recusa(e)
    versao, momento, con = _versao_do_corpo(corpo), agora(), obter_con()
    with transacao(con):
        r = _reserva(con, rid)
        conta = desp.conta(con, rid)
        if r["status"] != "ativa":
            raise ErroApi("Esta reserva está cancelada", 409)
        if conta["situacao"] != "fechada":
            raise ErroApi("A conta não está fechada", 409)
        conferir_versao(conta, versao)
        con.execute("UPDATE despesa_conta SET situacao='aberta', quitacao='pendente', fechada_em=NULL, fechada_por=NULL, "
                    "quitada_em=NULL, quitada_por=NULL, versao=versao+1 WHERE reserva_id=?", (rid,))
        a = ator_atual()
        con.execute("INSERT INTO conta_evento (reserva_id,acao,motivo,em,usuario_id,usuario_login,ip) VALUES (?,?,?,?,?,?,?)",
                    (rid, "reabrir", motivo, momento.strftime(FMT), a["id"], a["login"], a["ip"]))
        registrar(con, "conta_reaberta_fechamento", "reserva", rid, {"situacao": "fechada"}, {"situacao": "aberta"}, a)
        return jsonify({"conta": desp.conta(con, rid)}), 200
