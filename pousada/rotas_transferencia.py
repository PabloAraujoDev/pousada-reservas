"""Transferência de despesas entre hospedagens, busca do destino e "zerar a diária" informada.

Transferir = na MESMA transação: estorno com motivo "Transferido para #X" na origem, lançamento equivalente no destino, os dois
com o vínculo transferencia_id, e a linha do cabeçalho em 'transferencia'. A diária informada (campo da reserva) vira UM
lançamento de categoria "outros" no destino e a origem tem a diária zerada, com motivo, em conta_evento. Nada se apaga.
Decisão do clube pendente: só admin e atendente (despesas.transferir); a recepção não transfere.
"""
import sqlite3
import unicodedata

from flask import Blueprint, jsonify, request

from . import despesas as desp
from . import pagamentos as pg
from .db import obter_con, transacao
from .despesas import Recusa
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import exige, exigir
from .regras import MAX_DESPESA_UNIT, MAX_LANCAMENTOS, MAX_DESPESA_QTD, agora as agora_texto
from .rotas_despesas import _reserva, gravar
from .rotas_governanca import agora
from .rotas_pagamentos import FMT, _recusa, bump, conferir_conta_ativa_aberta, conferir_versao

bp = Blueprint("transferencia", __name__)


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFKD", str(t).casefold()) if not unicodedata.combining(c))


def _elegiveis(con, hoje, excluir):
    """Reservas ativas em andamento (ou liberadas com a conta aberta), de conta aberta."""
    sql = ("SELECT r.id, r.a, r.nome, r.i, r.f, r.conta_aberta_em FROM reservas r LEFT JOIN despesa_conta c ON c.reserva_id = r.id "
           "WHERE r.status='ativa' AND r.id<>? AND r.i<=? AND (r.f>=? OR r.conta_aberta_em IS NOT NULL) "
           "AND COALESCE(c.situacao,'aberta')='aberta' ORDER BY r.a, r.id")
    return con.execute(sql, (excluir, hoje, hoje)).fetchall()


@bp.route("/api/reservas/<int:rid>/destinos", methods=["GET"])
@exige("despesas.transferir")
def destinos(rid):
    exigir("reservas.ver")
    q = request.args.get("q", "")
    if len(q) > 60 or any(ord(c) < 32 for c in q):
        raise ErroApi("Busca inválida", 422)
    con = obter_con()
    _reserva(con, rid)
    q = _sem_acento(q.strip())
    achados = [l for l in _elegiveis(con, agora().strftime("%Y-%m-%d"), rid) if not q or q in _sem_acento(l["nome"]) or q in _sem_acento(l["a"])]
    return jsonify({"itens": [{"id": l["id"], "a": l["a"], "nome": l["nome"], "i": l["i"], "f": l["f"],
                               "liberado": bool(l["conta_aberta_em"])} for l in achados[:20]], "total": len(achados)})


def _corpo(c):
    if not isinstance(c, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    d = c.get("destino_id")
    if not pg.inteiro(d) or d < 1:
        raise Recusa("Escolha o apartamento de destino")
    itens = pg.validar_itens(c.get("itens"))
    if not itens:
        raise Recusa("Selecione ao menos um item para transferir")
    return {"destino_id": d, "itens": itens, "chave": pg.chave_valida(c.get("chave")), "conta_versao": pg.versao_valida(c.get("conta_versao"))}


def _linhas_a_mover(con, rid, r, ids):
    """(lançamentos ativos escolhidos, incluir_diaria). Recusa o que já foi estornado ou não é desta conta."""
    despesas, diaria = [], False
    for i in ids:
        if i == "diaria":
            if (r["diaria_centavos"] or 0) <= 0:
                raise ErroApi("Não há diária informada para transferir", 409)
            diaria = True
            continue
        l = con.execute("SELECT * FROM despesa_lancamento WHERE id=? AND reserva_id=? AND tipo='lancamento'", (int(i[1:]), rid)).fetchone()
        if not l:
            raise ErroApi("Há item que não pertence a esta conta", 422)
        if con.execute("SELECT 1 FROM despesa_lancamento WHERE estorno_de=?", (l["id"],)).fetchone():
            raise ErroApi("Há item que já foi estornado ou transferido", 409)
        despesas.append(l)
    return despesas, diaria


def _resposta(t):
    return {"id": t["id"], "origem_id": t["origem_id"], "destino_id": t["destino_id"], "apto_destino": t["apto_destino"],
            "itens": t["itens"], "total_centavos": t["total_centavos"], "com_diaria": bool(t["com_diaria"])}


def _linha_da_diaria(r, n):
    if n > MAX_DESPESA_QTD or r["diaria_centavos"] > MAX_DESPESA_UNIT:
        raise ErroApi("Diária grande demais para transferir (máximo %d noites e %s por noite)." % (MAX_DESPESA_QTD, desp.reais(MAX_DESPESA_UNIT)), 422)
    return {"categoria": "outros", "quantidade": n, "valor_unit_centavos": r["diaria_centavos"], "chave": None,
            "descricao": "Diária da reserva #%d (%d %s)" % (r["id"], n, "noite" if n == 1 else "noites")}


def zerar_diaria(con, r, motivo, momento, transferencia_id=None, chave=None):
    """Zera a diária informada (reserva.diaria_centavos = 0) e registra o evento com motivo. Devolve o total zerado."""
    n = desp.noites(r["i"], r["f"])
    total = r["diaria_centavos"] * n
    a = ator_atual()
    con.execute("UPDATE reservas SET diaria_centavos=0, alterado=?, versao=versao+1 WHERE id=?", (agora_texto(), r["id"]))
    con.execute("INSERT INTO conta_evento (reserva_id,acao,motivo,valor_centavos,noites,transferencia_id,em,usuario_id,usuario_login,chave,ip) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (r["id"], "diaria_zerar", motivo, total, n, transferencia_id, momento.strftime(FMT),
                                                    a["id"], a["login"], chave, a["ip"]))
    registrar(con, "diaria_zerada", "reserva", r["id"], None, {"itens": 1}, a)
    return total


@bp.route("/api/reservas/<int:rid>/transferir", methods=["POST"])
@exige("despesas.transferir")
def transferir(rid):
    try:
        d = _corpo(request.get_json(silent=True))
    except Recusa as e:
        raise _recusa(e)
    if "diaria" in d["itens"]:
        exigir("valores.editar")
    if d["destino_id"] == rid:
        raise ErroApi("Não é possível transferir para a mesma reserva", 422)
    con, momento = obter_con(), agora()
    try:
        with transacao(con):
            r = _reserva(con, rid)
            ja = con.execute("SELECT * FROM transferencia WHERE origem_id=? AND chave=?", (rid, d["chave"])).fetchone()
            if ja:                              # duplo clique: devolve a transferência que já existe
                return jsonify(_resposta(ja)), 200
            conta = desp.conta(con, rid)
            conferir_conta_ativa_aberta(r, conta)
            conferir_versao(conta, d["conta_versao"])
            dest = next((l for l in _elegiveis(con, momento.strftime("%Y-%m-%d"), rid) if l["id"] == d["destino_id"]), None)
            if not dest:
                raise ErroApi("O destino precisa ser uma hospedagem em andamento, ou liberada com a conta aberta", 422)
            despesas, com_diaria = _linhas_a_mover(con, rid, r, d["itens"])
            n = desp.noites(r["i"], r["f"])
            linha_diaria = _linha_da_diaria(r, n) if com_diaria else None
            total = sum(l["total_centavos"] for l in despesas) + (r["diaria_centavos"] * n if com_diaria else 0)
            if total <= 0:
                raise ErroApi("Nada com valor para transferir", 422)
            pg.conferir_total_cobre_pagamentos(con, r, pg.total_conta(con, r) - total)
            dr = dict(dest, status="ativa", diaria_centavos=None)
            soma_d, qtd_d = desp.saldo(con, dest["id"])
            if qtd_d + len(despesas) + (1 if com_diaria else 0) > MAX_LANCAMENTOS:
                raise ErroApi("O destino passaria do máximo de %d lançamentos" % MAX_LANCAMENTOS, 409)
            desp.conferir_saldo(soma_d, total)
            a = ator_atual()
            cur = con.execute("INSERT INTO transferencia (origem_id,destino_id,apto_origem,apto_destino,total_centavos,itens,com_diaria,em,"
                              "usuario_id,usuario_login,chave,ip) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              (rid, dest["id"], r["a"], dest["a"], total, len(despesas) + (1 if com_diaria else 0), int(com_diaria),
                               momento.strftime(FMT), a["id"], a["login"], d["chave"], a["ip"]))
            tid = cur.lastrowid
            motivo = "Transferido para #%d (apto %s)" % (dest["id"], dest["a"])
            for l in despesas:
                gravar(con, rid, r, dict(l, chave=None), "estorno", momento, estorno_de=l["id"], motivo=motivo, transferencia_id=tid)
                gravar(con, dest["id"], dr, dict(l, chave=None), "lancamento", momento, transferencia_id=tid)
            if com_diaria:
                zerar_diaria(con, r, motivo, momento, tid)
                gravar(con, dest["id"], dr, linha_diaria, "lancamento", momento, transferencia_id=tid)
            bump(con, rid)
            bump(con, dest["id"])
            registrar(con, "despesas_transferidas", "reserva", rid, None, {"itens": len(despesas) + (1 if com_diaria else 0)}, a)
            registrar(con, "despesas_recebidas", "reserva", dest["id"], None, {"itens": len(despesas) + (1 if com_diaria else 0)}, a)
            resp = _resposta(con.execute("SELECT * FROM transferencia WHERE id=?", (tid,)).fetchone())
    except desp.Recusa as e:
        raise _recusa(e)
    except sqlite3.IntegrityError:               # outra pessoa estornou/transferiu o mesmo item no mesmo instante
        raise ErroApi("Há item que já foi estornado ou transferido. Confira a conta.", 409)
    return jsonify(resp), 201


@bp.route("/api/reservas/<int:rid>/diaria/zerar", methods=["POST"])
@exige("despesas.estornar")
def zerar(rid):
    exigir("valores.editar")
    c = request.get_json(silent=True)
    try:
        motivo = desp.validar_motivo(c)
        chave, versao = pg.chave_valida(c.get("chave")), c.get("versao")
        if not pg.inteiro(versao):
            raise Recusa("Informe a versão da reserva", 400)
    except Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    try:
        with transacao(con):
            r = _reserva(con, rid)
            if con.execute("SELECT 1 FROM conta_evento WHERE reserva_id=? AND chave=?", (rid, chave)).fetchone():
                return jsonify({"versao": con.execute("SELECT versao FROM reservas WHERE id=?", (rid,)).fetchone()[0], "diaria_centavos": 0}), 200
            full = con.execute("SELECT versao FROM reservas WHERE id=?", (rid,)).fetchone()
            conferir_conta_ativa_aberta(r, desp.conta(con, rid))
            if full["versao"] != versao:
                raise ErroApi("Esta reserva foi alterada por outra pessoa", 409)
            if (r["diaria_centavos"] or 0) <= 0:
                raise ErroApi("Não há diária informada para zerar", 409)
            pg.conferir_total_cobre_pagamentos(con, r, pg.total_conta(con, r) - r["diaria_centavos"] * desp.noites(r["i"], r["f"]))
            zerar_diaria(con, r, motivo, momento, None, chave)
            bump(con, rid)
            nova = con.execute("SELECT versao FROM reservas WHERE id=?", (rid,)).fetchone()[0]
    except desp.Recusa as e:
        raise _recusa(e)
    except sqlite3.IntegrityError:
        raise ErroApi("A diária já foi zerada. Confira a conta.", 409)
    return jsonify({"versao": nova, "diaria_centavos": 0}), 201
