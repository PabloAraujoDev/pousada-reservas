"""Rotas do estado da hospedagem: check-in efetivo (e reversão), apartamento liberado com a conta aberta, placa do veículo,
ficha de check-in FNRH e a lista de contas abertas.

Todas as mutações são JSON com {versao} (controle de edição simultânea pela versão da reserva, que sobe a cada mudança: o duplo clique
repetido recebe 409). Tudo é gravado na mesma transação do log imutável (hospedagem_evento) e do histórico, sem dado pessoal.
A contagem dos cartões Check-ins/Ocupados NÃO muda: segue calculada pelas datas. Aqui só existe o estado explícito.
"""
from flask import Blueprint, g, jsonify, request

from . import despesas as desp
from . import hospedagem as hp
from .db import obter_con, transacao
from .despesas import Recusa
from .erros import ErroApi
from .historico import registrar
from .permissoes import exige, pode
from .regras import agora as agora_texto
from .rotas_governanca import agora
from .rotas_hospedes import montar, registrar_evento, reserva_ou_erro, versao_igual

bp = Blueprint("hospedagem", __name__)
FMT = "%Y-%m-%d %H:%M:%S"


def _versao(corpo):
    v = corpo.get("versao") if isinstance(corpo, dict) else None
    if not isinstance(v, int) or isinstance(v, bool):
        raise ErroApi("Informe a versão da reserva", 400)
    return v


def _motivo(corpo):
    """Motivo OBRIGATÓRIO de reverter check-in, liberar e desfazer a liberação: texto limpo, visível, 5 a 140 caracteres, sem número de cartão.
    Ausente ou em branco = 400; o resto das regras (caracteres invisíveis, cartão, tamanho) = 422."""
    m = corpo.get("motivo") if isinstance(corpo, dict) else None
    if not isinstance(m, str) or not m.strip():
        raise ErroApi("Informe o motivo", 400)
    try:
        return desp.validar_motivo(corpo)
    except Recusa as e:
        raise ErroApi(e.mensagem, e.status)


def _bump(con, rid, sets, args):
    con.execute("UPDATE reservas SET %s, alterado=?, versao=versao+1 WHERE id=?" % sets, list(args) + [agora_texto(), rid])


def _resposta(con, rid):
    r = con.execute("SELECT * FROM reservas WHERE id=?", (rid,)).fetchone()
    return jsonify({"versao": r["versao"], "estado": hp.estado(r), "checkin_em": r["checkin_em"], "checkin_por": r["checkin_por"],
                    "conta_aberta_em": r["conta_aberta_em"], "conta_aberta_por": r["conta_aberta_por"]})


def _login():
    return g.usuario["login"]


# ---------------------------------------------------------------- check-in

@bp.route("/api/reservas/<int:rid>/checkin", methods=["POST"])
@exige("checkin.registrar")
def registrar_checkin(rid):
    versao, momento, con = _versao(request.get_json(silent=True)), agora(), obter_con()
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        versao_igual(r, versao)
        hoje = momento.strftime("%Y-%m-%d")
        if r["checkin_em"]:
            raise ErroApi("O check-in desta hospedagem já foi registrado", 409)
        if r["conta_aberta_em"]:
            raise ErroApi("O apartamento já foi liberado (conta aberta)", 409)
        if hoje < r["i"]:
            raise ErroApi("A hospedagem ainda não começou", 422)
        if hoje > r["f"]:
            raise ErroApi("A hospedagem já terminou", 422)
        _bump(con, rid, "checkin_em=?, checkin_por=?", (momento.strftime(FMT), _login()))
        registrar_evento(con, rid, "checkin", "", momento)
        registrar(con, "checkin", "reserva", rid, {"estado": "pendente"}, {"estado": "efetuado"})
        return _resposta(con, rid), 201


def _bloqueio_da_reversao(con, r):
    """Mensagem de bloqueio (ou None). Decisão: 'tem lançamento' = despesa ativa (não estornada) OU diária informada (> 0)."""
    if desp.lancamentos_ativos(con, r["id"]):
        return ("Há lançamentos de despesa ativos nesta hospedagem. Estorne todos os lançamentos antes de reverter o check-in.")
    if hp.BLOQUEIA_REVERSAO_COM_DIARIA and (r["diaria_centavos"] or 0) > 0:
        return ("Há diária informada nesta hospedagem. Limpe o valor da diária em Alterar estadia antes de reverter o check-in.")
    return None


@bp.route("/api/reservas/<int:rid>/checkin/reverter", methods=["POST"])
@exige("checkin.reverter")
def reverter_checkin(rid):
    corpo = request.get_json(silent=True)
    versao, motivo, momento, con = _versao(corpo), _motivo(corpo), agora(), obter_con()
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        versao_igual(r, versao)
        if not r["checkin_em"]:
            raise ErroApi("O check-in desta hospedagem não foi registrado", 409)
        if r["conta_aberta_em"]:
            raise ErroApi("O apartamento foi liberado com a conta aberta. Desfaça a liberação antes de reverter o check-in.", 409)
        bloqueio = _bloqueio_da_reversao(con, r)
        if bloqueio:
            raise ErroApi(bloqueio, 409)
        _bump(con, rid, "checkin_em=NULL, checkin_por=NULL", ())
        registrar_evento(con, rid, "checkin_reverter", motivo, momento)
        registrar(con, "checkin_revertido", "reserva", rid, {"estado": "efetuado"}, {"estado": "pendente", "motivo": motivo})
        return _resposta(con, rid), 200


# ---------------------------------------------------------------- apartamento liberado, conta aberta

def _unidade_suja(con, unidade, momento):
    """Governança: o apartamento liberado volta como SUJA (a mesma ação 'suja' da equipe, no log da governança)."""
    reg = con.execute("SELECT situacao FROM governanca_unidade WHERE unidade=?", (unidade,)).fetchone()
    if not reg or reg["situacao"] == "suja":
        return
    em = momento.strftime(FMT)
    con.execute("UPDATE governanca_unidade SET situacao='suja', situacao_em=?, situacao_por=?, versao=versao+1 WHERE unidade=?",
                (em, g.usuario["id"], unidade))
    con.execute("INSERT INTO governanca_evento (em, unidade, usuario_id, usuario_login, acao, de, para, lote, ip) "
                "VALUES (?,?,?,?,'suja',?,'suja','conta_aberta',?)",
                (em, unidade, g.usuario["id"], g.usuario["login"], reg["situacao"], request.remote_addr or ""))


@bp.route("/api/reservas/<int:rid>/liberar", methods=["POST"])
@exige("conta.liberar")
def liberar(rid):
    corpo = request.get_json(silent=True)
    versao, motivo, momento, con = _versao(corpo), _motivo(corpo), agora(), obter_con()
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        versao_igual(r, versao)
        if r["conta_aberta_em"]:
            raise ErroApi("O apartamento já foi liberado", 409)
        if momento.strftime("%Y-%m-%d") < r["i"]:
            raise ErroApi("A hospedagem ainda não começou", 422)
        _bump(con, rid, "conta_aberta_em=?, conta_aberta_por=?", (momento.strftime(FMT), _login()))
        _unidade_suja(con, r["a"], momento)
        registrar_evento(con, rid, "liberar", motivo, momento)
        registrar(con, "conta_liberada", "reserva", rid, {"estado": hp.estado(r)}, {"estado": "conta_aberta", "motivo": motivo})
        return _resposta(con, rid), 200


@bp.route("/api/reservas/<int:rid>/liberar/reverter", methods=["POST"])
@exige("conta.liberar")
def desfazer_liberacao(rid):
    corpo = request.get_json(silent=True)
    versao, motivo, momento, con = _versao(corpo), _motivo(corpo), agora(), obter_con()
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        versao_igual(r, versao)
        if not r["conta_aberta_em"]:
            raise ErroApi("O apartamento não está liberado", 409)
        _bump(con, rid, "conta_aberta_em=NULL, conta_aberta_por=NULL", ())
        registrar_evento(con, rid, "liberar_reverter", motivo, momento)
        registrar(con, "conta_reaberta", "reserva", rid, {"estado": "conta_aberta"},
                  {"estado": hp.estado({**dict(r), "conta_aberta_em": None}), "motivo": motivo})
        return _resposta(con, rid), 200


# ---------------------------------------------------------------- placa do veículo (dado pessoal)

@bp.route("/api/reservas/<int:rid>/placa", methods=["PUT"])
@exige("veiculo.editar")
def placa(rid):
    corpo = request.get_json(silent=True)
    versao, momento, con = _versao(corpo), agora(), obter_con()
    if "placa" not in corpo:
        raise ErroApi("Informe a placa (ou null para remover)", 400)
    try:
        nova = hp.normalizar_placa(corpo.get("placa"))
    except Recusa as e:
        raise ErroApi(e.mensagem, e.status)
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        versao_igual(r, versao)
        if nova != r["placa"]:
            _bump(con, rid, "placa=?", (nova,))
            acao = "removida" if nova is None else ("definida" if r["placa"] is None else "alterada")
            registrar_evento(con, rid, "placa", acao, momento)
            registrar(con, "placa_alterada", "reserva", rid, None, {"placa": acao})        # nunca o número da placa
        atual = con.execute("SELECT versao, placa FROM reservas WHERE id=?", (rid,)).fetchone()
    return jsonify({"versao": atual["versao"], "placa": hp.formatar_placa(atual["placa"])})


# ---------------------------------------------------------------- ficha de check-in FNRH

@bp.route("/api/reservas/<int:rid>/ficha", methods=["POST"])
@exige("ficha.imprimir")
def ficha(rid):
    """Dados completos para imprimir a ficha. É POST de propósito: cada emissão de dados pessoais fica no log da hospedagem."""
    momento, con = agora(), obter_con()
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        dados = montar(con, r, True)
        registrar_evento(con, rid, "ficha", "", momento)
    faltam = max(0, r["n"] - 1 - len(dados["acompanhantes"]))
    return jsonify({"reserva": {"id": r["id"], "a": r["a"], "i": r["i"], "f": r["f"], "n": r["n"], "estado": hp.estado(r),
                                "placa": hp.formatar_placa(r["placa"]), "emitido_em": momento.strftime(FMT)},
                    "titular": dados["titular"], "acompanhantes": dados["acompanhantes"], "em_branco": faltam})


# ---------------------------------------------------------------- contas abertas (apartamento liberado, conta ainda aberta)

def contas_abertas(con):
    """Reservas ativas liberadas cuja conta de despesas não foi fechada. Nunca devolve valores."""
    sql = ("SELECT r.id, r.a, r.nome, r.i, r.f, r.conta_aberta_em, r.conta_aberta_por FROM reservas r "
           "LEFT JOIN despesa_conta c ON c.reserva_id = r.id WHERE r.status='ativa' AND r.conta_aberta_em IS NOT NULL "
           "AND COALESCE(c.situacao,'aberta') = 'aberta' ORDER BY r.conta_aberta_em, r.id")
    return [dict(l) for l in con.execute(sql)]


@bp.route("/api/contas-abertas", methods=["GET"])
@exige("reservas.ver")
def listar_contas_abertas():
    itens = contas_abertas(obter_con())
    return jsonify({"contas_abertas": len(itens), "itens": itens})
