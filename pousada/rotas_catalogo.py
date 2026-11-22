"""Rotas do catálogo de itens de consumo e do relatório de consumo (com a HORA exata dos lançamentos).

Catálogo: qualquer perfil que lança despesa LÊ os itens ativos (para escolher); só catalogo.gerir (administrador) vê os desativados,
cadastra, edita e desativa. Relatório de consumo: só despesas.hora (administrador). Nada daqui entra no histórico geral com valores.
CSRF, login e Origin são conferidos em seguranca.py antes de chegar aqui.
"""
import sqlite3
from datetime import timedelta

from flask import Blueprint, jsonify, request

from . import catalogo as cat
from .db import obter_con, transacao
from .despesas import Recusa
from .erros import ErroApi
from .historico import ator_atual
from .permissoes import exige, exigir, pode
from .regras import data_valida
from .rotas_governanca import agora

bp = Blueprint("catalogo", __name__)
MAX_DIAS_RELATORIO = 93
MAX_LINHAS_RELATORIO = 3000


def _recusa(e):
    return ErroApi(e.mensagem, e.status)


def _corpo_item(con, iid):
    return cat.publico(cat.obter(con, iid), True)


@bp.route("/api/catalogo", methods=["GET"])
@exige("despesas.lancar", "catalogo.gerir")
def listar():
    todos = request.args.get("todos") == "1"
    if todos:
        exigir("catalogo.gerir")             # desativados e versões de edição: só o administrador
    completo = pode("catalogo.gerir")
    itens = [cat.publico(l, completo) for l in cat.listar(obter_con(), so_ativos=not todos)]
    return jsonify({"itens": itens, "categorias": [[k, v[0]] for k, v in sorted(cat.CATEGORIAS.items(), key=lambda kv: kv[1][0])]})


def _gravar(operacao, status):
    """Roda a operação do catálogo numa transação, devolvendo o item (ou a recusa/duplicidade em português)."""
    con = obter_con()
    try:
        with transacao(con):
            iid = operacao(con, agora(), ator_atual())
        return jsonify(_corpo_item(con, iid)), status
    except Recusa as e:
        raise _recusa(e)
    except sqlite3.IntegrityError:
        raise ErroApi("Já existe um item com esta descrição nesta categoria e grupo", 409)


@bp.route("/api/catalogo", methods=["POST"])
@exige("catalogo.gerir")
def criar():
    d = _validar(request.get_json(silent=True))
    return _gravar(lambda con, momento, ator: cat.criar(con, d, ator, momento), 201)


def _validar(corpo):
    try:
        return cat.validar_item(corpo)
    except Recusa as e:
        raise _recusa(e)


def _versao(corpo):
    try:
        return cat.validar_versao(corpo)
    except Recusa as e:
        raise _recusa(e)


@bp.route("/api/catalogo/<int:iid>", methods=["PUT"])
@exige("catalogo.gerir")
def editar(iid):
    corpo = request.get_json(silent=True)
    d, versao = _validar(corpo), _versao(corpo)

    def op(con, momento, ator):
        cat.editar(con, iid, d, versao, ator, momento)
        return iid
    return _gravar(op, 200)


@bp.route("/api/catalogo/<int:iid>/ativo", methods=["POST"])
@exige("catalogo.gerir")
def ativar(iid):
    corpo = request.get_json(silent=True)
    versao = _versao(corpo)
    if not isinstance(corpo.get("ativo"), bool):
        raise ErroApi("Informe se o item fica ativo (true) ou desativado (false)", 400)

    def op(con, momento, ator):
        cat.definir_ativo(con, iid, corpo["ativo"], versao, ator, momento)
        return iid
    return _gravar(op, 200)


@bp.route("/api/catalogo/<int:iid>/log", methods=["GET"])
@exige("catalogo.gerir")
def log(iid):
    con = obter_con()
    if cat.obter(con, iid) is None:
        raise ErroApi("Item não encontrado", 404)
    return jsonify({"itens": cat.historico(con, iid)})


@bp.route("/api/relatorio/consumo", methods=["GET"])
@exige("despesas.hora")
def relatorio_consumo():
    """Lançamentos e estornos do período (por data do lançamento), com data+hora, apto, hóspede, item, quantidade, valor e quem lançou."""
    ini, fim = data_valida(request.args.get("inicio")), data_valida(request.args.get("fim"))
    if not ini or not fim or fim < ini:
        raise ErroApi("Informe o período (inicio e fim, AAAA-MM-DD, com o fim depois do início)", 400)
    if fim - ini > timedelta(days=MAX_DIAS_RELATORIO):
        raise ErroApi("Período grande demais (máximo %d dias)" % MAX_DIAS_RELATORIO, 400)
    sql = ("SELECT d.id, d.reserva_id, d.em, d.tipo, d.categoria, d.descricao, d.quantidade, d.valor_unit_centavos, d.total_centavos, "
           "d.usuario_login, d.item_id, d.motivo, d.transferencia_id, d.apto, r.nome AS hospede FROM despesa_lancamento d "
           "LEFT JOIN reservas r ON r.id = d.reserva_id WHERE d.em >= ? AND d.em < ? ORDER BY d.em, d.id LIMIT ?")
    linhas = obter_con().execute(sql, (ini.isoformat() + " 00:00:00", (fim + timedelta(days=1)).isoformat() + " 00:00:00",
                                       MAX_LINHAS_RELATORIO + 1)).fetchall()
    cortado = len(linhas) > MAX_LINHAS_RELATORIO
    itens = [dict(l) for l in linhas[:MAX_LINHAS_RELATORIO]]
    return jsonify({"itens": itens, "cortado": cortado, "total_centavos": sum(i["total_centavos"] for i in itens),
                    "inicio": ini.isoformat(), "fim": fim.isoformat()})
