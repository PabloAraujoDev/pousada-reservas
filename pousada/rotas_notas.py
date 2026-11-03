"""Rotas das Notas: anotações com autor e data da reserva (escopo 'reserva') e do apartamento (escopo 'unidade').

PRIVACIDADE: o texto só sai AQUI. O histórico recebe apenas "nota adicionada/corrigida/ocultada" (sem texto); a camareira
nunca lê notas de reserva e, nas do apartamento, recebe só o texto passado por observacao_segura (sem autor).
CSRF, login e Origin são conferidos em seguranca.py antes de chegar aqui.
"""
import sqlite3

from flask import Blueprint, jsonify, request

from . import notas as nt
from .camareiras import observacao_segura
from .db import obter_con, transacao
from .despesas import Recusa
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import exige, pode
from .regras import UNIDADES
from .rotas_governanca import agora

bp = Blueprint("notas", __name__)
MSG_MUDOU = "Esta nota foi alterada por outra pessoa. Recarregue e confira."
CAP_ESCRITA = {"reserva": "notas.escrever", "unidade": "notas.escrever_unidade"}


def _recusa(e):
    return ErroApi(e.mensagem, e.status)


def _reserva(con, rid):
    """Reserva existente; cancelada some (404) para quem não pode ver canceladas."""
    r = con.execute("SELECT id, status FROM reservas WHERE id=?", (rid,)).fetchone()
    if not r or (r["status"] != "ativa" and not pode("reservas.ver_canceladas")):
        raise ErroApi("Reserva não encontrada", 404)
    return r


def _unidade(u):
    if u not in UNIDADES:
        raise ErroApi("Unidade não encontrada", 404)
    return u


def _pode_mexer(n, momento):
    """Corrigir/ocultar: precisa poder escrever no escopo E (editar reservas OU ser o autor dentro da janela)."""
    if not pode(CAP_ESCRITA[n["escopo"]]):
        return False
    if pode("reservas.editar"):
        return True
    a = ator_atual()
    return a["id"] is not None and a["id"] == n["autor_id"] and nt.dentro_da_janela(n, momento)


def _saida(n, momento, com_ocultas):
    """Nota -> dict da API (quem lê, o que vê). 'anteriores' e dados da ocultação só com notas.ver_ocultas."""
    v, p = n["versoes"], n["versoes"][0]
    d = {"id": n["id"], "texto": v[-1]["texto"], "por": p["por"], "em": p["em"], "versao": len(v),
         "modificado_por": v[-1]["por"] if len(v) > 1 else None, "modificado_em": v[-1]["em"] if len(v) > 1 else None,
         "pode_corrigir": not n["oculta"] and _pode_mexer(n, momento)}
    d["pode_ocultar"] = d["pode_corrigir"]
    if com_ocultas:
        d.update(oculta=n["oculta"], oculta_por=n["oculta_por"], oculta_em=n["oculta_em"], oculta_motivo=n["oculta_motivo"],
                 anteriores=v[:-1])
    return d


def _lista(con, reserva_id=None, unidade=None):
    todas = nt.montar(nt.linhas_do_escopo(con, reserva_id, unidade))
    momento, com = agora(), pode("notas.ver_ocultas") and request.args.get("ocultas") == "1"
    if not pode("reservas.ver"):         # camareira: só a nota do apartamento, saneada, sem autor nem ações
        limpas = [(n, observacao_segura(n["versoes"][-1]["texto"])) for n in todas if not n["oculta"]]
        itens = [{"id": n["id"], "texto": t, "em": n["versoes"][0]["em"]} for n, t in limpas if t]
        return {"notas": itens, "total": len(itens), "limite": nt.MAX_NOTAS, "pode_escrever": False}
    visiveis = [n for n in todas if com or not n["oculta"]]
    return {"notas": [_saida(n, momento, com) for n in visiveis], "total": sum(1 for n in todas if not n["oculta"]),
            "limite": nt.MAX_NOTAS, "pode_escrever": pode(CAP_ESCRITA["unidade" if unidade else "reserva"])}


@bp.route("/api/reservas/<int:rid>/notas", methods=["GET"])
@exige("reservas.ver")
def listar_reserva(rid):
    con = obter_con()
    _reserva(con, rid)
    return jsonify(_lista(con, reserva_id=rid))


@bp.route("/api/unidades/<unidade>/notas", methods=["GET"])
@exige("reservas.ver", "governanca.ver")
def listar_unidade(unidade):
    return jsonify(_lista(obter_con(), unidade=_unidade(unidade)))


def _gravar(con, escopo, rid, un, tipo, ref, texto, motivo, chave, momento):
    """Acrescenta a linha ao log e o aviso (sem texto) ao histórico, na mesma transação."""
    a = ator_atual()
    cur = con.execute(
        "INSERT INTO nota (escopo,reserva_id,unidade,tipo,nota_ref,texto,motivo,em,usuario_id,usuario_login,chave,ip) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (escopo, rid, un, tipo, ref, texto, motivo, momento.strftime(nt.FORMATO), a["id"], a["login"], chave, a["ip"]))
    acao = {"nota": "nota_adicionada", "correcao": "nota_corrigida", "ocultar": "nota_ocultada"}[tipo]
    registrar(con, acao, "reserva" if rid else "unidade", rid, None, None if rid else {"unidade": un}, a)
    return cur.lastrowid


def _nova(escopo, rid, un):
    """Cria nota nova (reserva ou unidade). Mesma chave repetida devolve a nota original (200)."""
    corpo = request.get_json(silent=True)
    try:
        texto, chave = nt.validar_texto(corpo), nt.validar_chave(corpo)
    except Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    with transacao(con):
        if rid is not None and _reserva(con, rid)["status"] != "ativa":
            raise ErroApi("Esta reserva está cancelada", 409)
        if chave:
            ant = con.execute("SELECT id FROM nota WHERE chave=? AND IFNULL(reserva_id,0)=? AND IFNULL(unidade,'')=?",
                              (chave, rid or 0, un or "")).fetchone()
            if ant:
                return jsonify(_saida(nt.buscar(con, ant["id"])[0], momento, False)), 200
        if nt.contagem(con, rid, un) >= nt.MAX_NOTAS:
            raise ErroApi("Este %s já tem o máximo de %d notas" % ("apartamento" if un else "registro", nt.MAX_NOTAS), 409)
        nid = _gravar(con, escopo, rid, un, "nota", None, texto, "", chave, momento)
        saida = _saida(nt.buscar(con, nid)[0], momento, False)
    return jsonify(saida), 201


@bp.route("/api/reservas/<int:rid>/notas", methods=["POST"])
@exige("notas.escrever")
def nova_reserva(rid):
    return _nova("reserva", rid, None)


@bp.route("/api/unidades/<unidade>/notas", methods=["POST"])
@exige("notas.escrever_unidade")
def nova_unidade(unidade):
    return _nova("unidade", None, _unidade(unidade))


def _alteravel(con, nid, corpo, momento):
    """Nota a corrigir/ocultar, já conferidas permissão, janela, versão e estado. Devolve (nota, linha original)."""
    try:
        v = nt.validar_versao(corpo)
    except Recusa as e:
        raise _recusa(e)
    n, ref = nt.buscar(con, nid)
    if not n:
        raise ErroApi("Nota não encontrada", 404)
    if ref["reserva_id"] is not None and _reserva(con, ref["reserva_id"])["status"] != "ativa":
        raise ErroApi("Esta reserva está cancelada", 409)
    if not pode(CAP_ESCRITA[n["escopo"]]):
        raise ErroApi("Seu perfil não pode alterar esta nota", 403)
    if not _pode_mexer(n, momento):
        raise ErroApi("Só quem criou a nota (até 24 horas depois) ou a administração pode alterá-la", 403)
    if n["oculta"]:
        raise ErroApi("Esta nota já foi ocultada", 409)
    if v != nt.versao(n):
        raise ErroApi(MSG_MUDOU, 409)
    return n, ref


def _alterar(nid, tipo):
    corpo = request.get_json(silent=True)
    try:
        texto = nt.validar_texto(corpo) if tipo == "correcao" else ""
        motivo = nt.validar_motivo(corpo) if tipo == "ocultar" else ""
    except Recusa as e:
        raise _recusa(e)
    con, momento = obter_con(), agora()
    try:
        with transacao(con):
            n, ref = _alteravel(con, nid, corpo, momento)
            if tipo == "correcao" and nt.versao(n) > nt.MAX_CORRECOES:
                raise ErroApi("Esta nota já foi corrigida muitas vezes; oculte-a e crie outra", 409)
            _gravar(con, ref["escopo"], ref["reserva_id"], ref["unidade"], tipo, nid, texto, motivo, None, momento)
            saida = _saida(nt.buscar(con, nid)[0], momento, False)
    except sqlite3.IntegrityError:           # outra pessoa ocultou no mesmo instante (índice único / trigger)
        raise ErroApi(MSG_MUDOU, 409)
    return jsonify(saida), 200


@bp.route("/api/notas/<int:nid>/corrigir", methods=["POST"])
@exige("notas.escrever", "notas.escrever_unidade")
def corrigir(nid):
    return _alterar(nid, "correcao")


@bp.route("/api/notas/<int:nid>/ocultar", methods=["POST"])
@exige("notas.escrever", "notas.escrever_unidade")
def ocultar(nid):
    return _alterar(nid, "ocultar")
