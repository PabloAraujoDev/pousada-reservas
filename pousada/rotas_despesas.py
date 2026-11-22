"""Rotas de Despesas (conta da reserva): listar, lançar, estornar e contar contas abertas.

PRIVACIDADE: o valor só sai AQUI, para quem tem despesas.ver. O histórico recebe só categoria e "itens"; descrição,
motivo e valores nunca vão para o histórico, para logs nem para mensagens de erro.
CSRF, login e Origin são conferidos em seguranca.py antes de chegar aqui.
"""
import sqlite3

from flask import Blueprint, jsonify, request

from . import catalogo as cat
from . import despesas as desp
from . import pagamentos as pg
from .db import obter_con, transacao
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import exige, exigir, pode
from .regras import MAX_LANCAMENTOS
from .rotas_governanca import agora
from .rotas_hospedagem import contas_abertas

bp = Blueprint("despesas", __name__)
MSG_FECHADA = "A conta já foi fechada."


def _recusa(e):
    return ErroApi(e.mensagem, e.status)


def _reserva(con, rid):
    """Reserva existente; cancelada some (404) para quem não pode ver canceladas."""
    r = con.execute("SELECT id, a, i, f, status, diaria_centavos FROM reservas WHERE id=?", (rid,)).fetchone()
    if not r or (r["status"] != "ativa" and not pode("reservas.ver_canceladas")):
        raise ErroApi("Reserva não encontrada", 404)
    return r


def _corpo_totais(con, r):
    soma, _ = desp.saldo(con, r["id"])
    t = desp.totais(soma, desp.noites(r["i"], r["f"]), r["diaria_centavos"], pode("valores.ver"))
    if pode("pagamentos.ver") and pode("valores.ver"):       # crédito (pagamentos líquidos) e saldo a pagar; total sempre = diárias + despesas
        total, pago = pg.total_conta(con, r), pg.liquido(con, r["id"])
        t.update({"conta_centavos": total, "pagamentos_centavos": pago, "saldo_centavos": total - pago})
    return t


@bp.route("/api/reservas/<int:rid>/despesas", methods=["GET"])
@exige("despesas.ver")
def listar(rid):
    con = obter_con()
    r = _reserva(con, rid)
    return jsonify({"conta": desp.conta(con, rid), "itens": desp.itens(desp.linhas_da_reserva(con, rid), pode("despesas.hora")),
                    "totais": _corpo_totais(con, r), "reserva": {"a": r["a"], "i": r["i"], "f": r["f"], "status": r["status"]}})


def _item_por_id(con, lid):
    linhas = desp.linhas_da_reserva(con, con.execute("SELECT reserva_id FROM despesa_lancamento WHERE id=?",
                                                     (lid,)).fetchone()[0])
    return next(i for i in desp.itens(linhas, pode("despesas.hora")) if i["id"] == lid)


def _conferir_pode_lancar(con, r, conta):
    """Reserva ativa que já começou e conta aberta."""
    if r["status"] != "ativa":
        raise ErroApi("Esta reserva está cancelada", 409)
    if r["i"] > agora().strftime("%Y-%m-%d"):
        raise ErroApi("A hospedagem ainda não começou", 422)
    if conta["situacao"] != "aberta":
        raise ErroApi(MSG_FECHADA, 409)


def _dados_do_item(con, d):
    """Congela descrição e preço do item no lançamento. Item desativado ou com preço mudado desde que a tela abriu é recusado."""
    it = cat.obter(con, d["item_id"])
    if it is None:
        raise ErroApi("Item não encontrado", 404)
    if not it["ativo"]:
        raise ErroApi("Este item foi desativado. Atualize a lista de itens.", 409)
    if it["versao"] != d["item_versao"]:
        raise ErroApi("O item foi alterado (preço ou nome). Atualize a lista de itens e confira o valor.", 409)
    return {"categoria": cat.CATEGORIAS[it["categoria"]][1], "descricao": it["descricao"], "quantidade": d["quantidade"],
            "valor_unit_centavos": it["preco_centavos"], "chave": d["chave"], "item_id": it["id"]}


def gravar(con, rid, r, dados, tipo, momento, estorno_de=None, motivo="", transferencia_id=None):
    """Acrescenta a linha ao log, cria a conta se preciso e soma 1 na versão da conta (mesma transação)."""
    a = ator_atual()
    total = dados["quantidade"] * dados["valor_unit_centavos"]
    cur = con.execute(
        "INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,"
        "apto,em,usuario_id,usuario_login,chave,estorno_de,motivo,ip,transferencia_id,item_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, tipo, dados["categoria"], dados["descricao"], dados["quantidade"], dados["valor_unit_centavos"],
         total if tipo == "lancamento" else -total, r["a"], momento.strftime("%Y-%m-%d %H:%M:%S"),
         a["id"], a["login"], dados.get("chave"), estorno_de, motivo, a["ip"], transferencia_id, dados.get("item_id")))
    con.execute("INSERT OR IGNORE INTO despesa_conta (reserva_id) VALUES (?)", (rid,))
    con.execute("UPDATE despesa_conta SET versao = versao + 1 WHERE reserva_id=?", (rid,))
    registrar(con, "despesa_lancada" if tipo == "lancamento" else "despesa_estornada", "reserva", rid, None,
              {"categoria": dados["categoria"], "itens": 1}, a)
    return cur.lastrowid


@bp.route("/api/reservas/<int:rid>/despesas", methods=["POST"])
@exige("despesas.lancar")
def lancar(rid):
    corpo = request.get_json(silent=True)
    por_item = isinstance(corpo, dict) and "item_id" in corpo
    if not por_item:
        exigir("catalogo.gerir")           # avulso (preço digitado) só o administrador: os demais perfis escolhem item do catálogo
    try:
        dados = desp.validar_por_item(corpo) if por_item else desp.validar_lancamento(corpo)
    except desp.Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    with transacao(con):
        r = _reserva(con, rid)
        if dados["chave"]:           # duplo clique: a mesma chave devolve o lançamento que já existe
            antigo = con.execute("SELECT id FROM despesa_lancamento WHERE reserva_id=? AND chave=?",
                                 (rid, dados["chave"])).fetchone()
            if antigo:
                return jsonify(_item_por_id(con, antigo["id"])), 200
        _conferir_pode_lancar(con, r, desp.conta(con, rid))
        if por_item:
            dados = _dados_do_item(con, dados)
        soma, linhas = desp.saldo(con, rid)
        if linhas >= MAX_LANCAMENTOS:
            raise ErroApi("Esta reserva já tem o máximo de %d lançamentos" % MAX_LANCAMENTOS, 409)
        try:
            desp.conferir_saldo(soma, dados["quantidade"] * dados["valor_unit_centavos"])
        except desp.Recusa as e:
            raise _recusa(e)
        lid = gravar(con, rid, r, dados, "lancamento", momento)
        item = _item_por_id(con, lid)
    return jsonify(item), 201


def _estornavel(con, lid):
    """Lançamento a estornar (devolve a linha e a reserva) ou o erro correspondente."""
    antigo = con.execute("SELECT * FROM despesa_lancamento WHERE id=?", (lid,)).fetchone()
    if not antigo:
        raise ErroApi("Lançamento não encontrado", 404)
    r = _reserva(con, antigo["reserva_id"])
    if antigo["tipo"] == "estorno":
        raise ErroApi("Este lançamento já é um estorno e não pode ser estornado", 409)
    if con.execute("SELECT 1 FROM despesa_lancamento WHERE estorno_de=?", (lid,)).fetchone():
        raise ErroApi("Este lançamento já foi estornado", 409)
    if desp.conta(con, antigo["reserva_id"])["situacao"] != "aberta":
        raise ErroApi(MSG_FECHADA, 409)
    return antigo, r


@bp.route("/api/despesas/<int:lid>/estorno", methods=["POST"])
@exige("despesas.estornar")
def estornar(lid):
    try:
        motivo = desp.validar_motivo(request.get_json(silent=True))
    except desp.Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    try:
        with transacao(con):
            antigo, r = _estornavel(con, lid)
            try:             # o total da conta não pode ficar abaixo do que já foi pago
                pg.conferir_total_cobre_pagamentos(con, r, pg.total_conta(con, r) - antigo["total_centavos"])
            except desp.Recusa as e:
                raise _recusa(e)
            novo = gravar(con, r["id"], r, dict(antigo, chave=None), "estorno", momento, estorno_de=lid, motivo=motivo)
            item = _item_por_id(con, novo)
    except sqlite3.IntegrityError:           # outra pessoa estornou no mesmo instante (índice único uq_desp_estorno)
        raise ErroApi("Este lançamento já foi estornado", 409)
    return jsonify(item), 201


@bp.route("/api/despesas/resumo", methods=["GET"])
@exige("despesas.ver")
def resumo():
    """Só a contagem de contas abertas com saldo (sem nenhum valor)."""
    hoje = agora().strftime("%Y-%m-%d")
    abertas = [(rid, f) for rid, f, situacao in desp.reservas_com_saldo(obter_con()) if situacao == "aberta"]
    return jsonify({"contas_abertas": len(abertas), "pendentes_fechamento": sum(1 for _, f in abertas if f < hoje),
                    "ids": [rid for rid, _ in abertas],
                    "liberadas": len(contas_abertas(obter_con()))})       # apartamento liberado com a conta ainda aberta (sem valores)
