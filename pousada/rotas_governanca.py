"""Rotas da Governança: GET /api/governanca, POST /api/governanca/acao e GET /api/governanca/<unidade>/eventos.

O servidor decide o que cada perfil recebe: a camareira NUNCA recebe nome, reserva, grupo, pagamento, tipo,
valor, telefone nem extras (só situação, horários, nº de pessoas, dias sem arrumação e a observação já saneada).
CSRF, login e Origin são conferidos para todas as rotas em seguranca.py (antes de chegar aqui).
"""
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request

from . import governanca as gov
from . import notas as nt
from .camareiras import observacao_segura
from .db import obter_con, transacao
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import capacidades, exige, exigir, pode
from .regras import OCUPADAS, UNIDADES, agora_local, data_valida

bp = Blueprint("governanca", __name__)
MAX_EVENTOS = 50
MAX_OBS_RESERVA = 140
DIAS_A_FRENTE = 7
CAMPOS_REG = ("unidade", "situacao", "situacao_em", "situacao_por", "pronto_em", "iniciada_em", "saida_confirmada",
              "manutencao", "manutencao_motivo", "obs", "versao")


def agora():
    """Hora LOCAL do servidor (a da pousada). Os testes fixam config AGORA."""
    return current_app.config.get("AGORA") or agora_local()


def _quem():
    u = g.usuario
    return {"id": u["id"], "papel": u["papel"], "caps": capacidades(u["papel"])}


def _erro(e):
    return ErroApi(e.mensagem, e.status, **e.extra)


# ---------------------------------------------------------------- leitura do banco

def _registros(con, unidades=None):
    sql = "SELECT %s FROM governanca_unidade" % ", ".join(CAMPOS_REG)
    args = []
    if unidades is not None:
        sql += " WHERE unidade IN (%s)" % ",".join("?" * len(unidades))
        args = list(unidades)
    return {r["unidade"]: dict(r) for r in con.execute(sql, args)}


def _reservas_do_dia(con, dia):
    """Reservas ativas que tocam o dia (entram, ficam ou saem), por unidade.

    Apartamento LIBERADO com a conta aberta (conta_aberta_em) já não está ocupado: a reserva sai da derivação (a unidade fica
    livre e suja, a conta continua nas Despesas). As contagens do Mapa/Calendário seguem pelas datas e não passam por aqui."""
    por_unidade = {}
    for r in con.execute("SELECT id, a, nome, n, i, f, o, grupo FROM reservas WHERE status='ativa' AND conta_aberta_em IS NULL "
                         "AND i <= ? AND f >= ? ORDER BY id", (dia, dia)):
        por_unidade.setdefault(r["a"], []).append(dict(r))
    return por_unidade


def _ultimas_saidas(con, hoje):
    """L de cada unidade: a maior saída (de reserva ativa) que já ocorreu ou ocorre hoje."""
    return {r[0]: r[1] for r in con.execute("SELECT a, MAX(f) FROM reservas WHERE status='ativa' AND f <= ? GROUP BY a", (hoje,))}


def _ultimos_eventos(con):
    """Quem mexeu por último em cada unidade e quando (login e hora, nada mais)."""
    sql = ("SELECT unidade, usuario_login, em FROM governanca_evento "
           "WHERE id IN (SELECT MAX(id) FROM governanca_evento GROUP BY unidade)")
    return {r["unidade"]: (r["usuario_login"], r["em"]) for r in con.execute(sql)}


def _estado(u, reg, reservas_hoje, ultimas, momento, par):
    """Estado de UMA unidade (camadas A e B) como o dict que governanca.avaliar espera."""
    hoje = momento.strftime("%Y-%m-%d")
    der = gov.derivar(reservas_hoje.get(u, []), hoje)
    situacao, origem = gov.situacao_efetiva(reg, der, ultimas.get(u), momento, par, u)
    return {"u": u, "reg": reg, "der": der, "situacao": situacao, "origem": origem,
            "saida_hoje": hoje if der["saida"] else None}


# ---------------------------------------------------------------- GET /api/governanca

def _dia_pedido(hoje):
    dia = request.args.get("dia")
    if dia is None:
        return hoje
    d = data_valida(dia)
    ate = (datetime.strptime(hoje, "%Y-%m-%d") + timedelta(days=DIAS_A_FRENTE)).strftime("%Y-%m-%d")
    if not d or not hoje <= dia <= ate:
        raise ErroApi("Dia inválido: use uma data de hoje até %d dias à frente" % DIAS_A_FRENTE, 422)
    return dia


def _reserva_principal(der):
    return der["chegada"] or der["estadia"] or der["saida"]


def _movimento(res, hora, com_hospede, extra_pessoas=False):
    """Bloco de saída/chegada. Nome e id da reserva só para quem pode ver reservas."""
    if not res:
        return None
    d = {"hora": hora}
    if extra_pessoas:
        d["pessoas"] = res["n"]
    if com_hospede:
        d["nome"], d["reserva_id"] = res["nome"], res["id"]
    return d


def _item(estado, der_dia, dia, momento, par, ctx):
    """Um cartão da lista, já filtrado para o perfil (ctx['hospede'] = quem pode ver reservas)."""
    u, reg, situacao = estado["u"], estado["reg"], estado["situacao"]
    eh_hoje = dia == momento.strftime("%Y-%m-%d")
    dias = gov.dias_sem_arrumacao(reg, estado["der"], momento.strftime("%Y-%m-%d"))
    enxoval, pronta_ha = gov.alertas_de_tempo(situacao, estado["der"], dias, par)
    principal = _reserva_principal(der_dia)
    ultimo = ctx["eventos"].get(u)
    atual = der_dia["estadia"]
    item = {
        "u": u, "andar": gov.andar_de(u), "situacao": situacao,
        "suja_origem": estado["origem"] if situacao == "suja" else None,
        "ocupacao": "hospedada" if estado["der"]["estadia"] else "vaga",
        "saida_hoje": _movimento(der_dia["saida"], par["hora_saida"], ctx["hospede"]),
        "chegada_hoje": _movimento(der_dia["chegada"], par["hora_entrada"], ctx["hospede"], True),
        "troca_hoje": der_dia["troca"],
        "atrasada": gov.atrasada(situacao, der_dia, momento, par, eh_hoje),
        "pessoas": atual["n"] if atual else None,
        "dias_sem_arrumacao": dias if dias >= 1 else None,
        "alerta_enxoval": enxoval, "pronta_ha_dias": pronta_ha,
        "obs": reg["obs"], "manutencao_motivo": reg["manutencao_motivo"] if reg["manutencao"] else "",
        "obs_reserva": observacao_segura(principal["o"])[:MAX_OBS_RESERVA] if principal else "",
        "versao": reg["versao"],
        "atualizado_em": (ultimo[1] if ultimo else reg["situacao_em"])[11:16],
        "atualizado_por": ultimo[0] if ultimo else None,
        "pode": gov.acoes_possiveis(estado, ctx["quem"], momento, par) if eh_hoje else [],
    }
    if ctx["hospede"] and atual:
        item["hospede"] = {"nome": atual["nome"], "reserva_id": atual["id"]}
    if ctx["hospede"]:
        item["tem_nota_unidade"] = u in ctx["notas_un"]         # só sim/não: a camareira não recebe (nem lê notas pela lista)
    if ctx["hospede"] and principal and principal["grupo"]:
        item["grupo_reserva"] = principal["grupo"]
    return item


def _totais(itens):
    t = {"saida_hoje": 0, "chegada_hoje": 0, "troca_hoje": 0}
    for s in ("suja", "em_arrumacao", "pronta", "hospedada", "aguardando_saida", "manutencao", "interditada"):
        t[s] = 0
    for i in itens:
        t[i["situacao"]] += 1
        t["saida_hoje"] += bool(i["saida_hoje"])
        t["chegada_hoje"] += bool(i["chegada_hoje"])
        t["troca_hoje"] += i["troca_hoje"]
    return t


@bp.route("/api/governanca", methods=["GET"])
@exige("governanca.ver")
def listar():
    momento, con, par = agora(), obter_con(), gov.parametros(current_app.config)
    hoje = momento.strftime("%Y-%m-%d")
    dia = _dia_pedido(hoje)
    registros, res_hoje = _registros(con), _reservas_do_dia(con, hoje)
    res_dia = res_hoje if dia == hoje else _reservas_do_dia(con, dia)
    ultimas = _ultimas_saidas(con, hoje)
    ctx = {"quem": _quem(), "hospede": pode("reservas.ver"), "eventos": _ultimos_eventos(con)}
    ctx["notas_un"] = nt.unidades_com_nota(con) if ctx["hospede"] else set()
    itens = []
    for u in UNIDADES:
        estado = _estado(u, registros[u], res_hoje, ultimas, momento, par)
        der_dia = estado["der"] if dia == hoje else gov.derivar(res_dia.get(u, []), dia)
        itens.append(_item(estado, der_dia, dia, momento, par, ctx))
    return jsonify({"hoje": hoje, "dia": dia, "agora": momento.strftime("%H:%M"),
                    "parametros": {"dias_troca": par["dias_troca"], "dias_vaga": par["dias_vaga"],
                                   "janela_desfazer_min": par["janela_min"]},
                    "totais": _totais(itens), "unidades": itens})


# ---------------------------------------------------------------- POST /api/governanca/acao

def _unidade_do_pedido(entrada, vistas):
    if not isinstance(entrada, dict):
        raise ErroApi("Cada unidade deve ser um objeto com u e versao", 422)
    u, versao = entrada.get("u"), entrada.get("versao")
    if not isinstance(u, str) or u not in UNIDADES:
        raise ErroApi("Unidade inexistente", 422)
    if u in vistas:
        raise ErroApi("Unidade repetida no pedido: %s" % u, 422)
    if u in OCUPADAS:
        raise ErroApi("Unidade interditada: %s" % u, 422)
    if not isinstance(versao, int) or isinstance(versao, bool):
        raise ErroApi("Informe a versão da unidade %s" % u, 422)
    vistas.add(u)
    return u, versao


def _validar_pedido(corpo):
    """Corpo da ação -> (acao, [(unidade, versao)], dados). Qualquer problema: 422 em português, antes de tocar no banco."""
    if not isinstance(corpo, dict):
        raise ErroApi("Envie os dados em um objeto JSON", 422)
    acao, lista = corpo.get("acao"), corpo.get("unidades")
    if not isinstance(acao, str) or acao not in gov.ACOES:
        raise ErroApi("Ação desconhecida", 422)
    if not isinstance(lista, list) or not 1 <= len(lista) <= len(UNIDADES):
        raise ErroApi("Informe de 1 a %d unidades" % len(UNIDADES), 422)
    vistas = set()
    unidades = [_unidade_do_pedido(e, vistas) for e in lista]
    confirmou = corpo.get("confirmou_saida", False)
    if not isinstance(confirmou, bool):
        raise ErroApi("confirmou_saida deve ser verdadeiro ou falso", 422)
    try:
        obs = gov.texto_curto(corpo.get("obs", ""), "Observação") if acao == "observacao" else ""
        motivo = gov.texto_curto(corpo.get("motivo", ""), "Motivo") if acao == "manutencao_abrir" else ""
    except gov.Recusa as e:
        raise _erro(e)
    if acao == "manutencao_abrir" and not motivo:
        raise ErroApi("Informe o motivo da manutenção", 422)
    return acao, unidades, {"id_usuario": g.usuario["id"], "confirmou_saida": confirmou, "obs": obs, "motivo": motivo}


def _conflito(estado, versao_atual, eventos):
    ultimo = eventos.get(estado["u"])
    return {"u": estado["u"], "situacao_atual": estado["situacao"], "versao": versao_atual,
            "por": ultimo[0] if ultimo else None, "em": (ultimo[1] if ultimo else estado["reg"]["situacao_em"])[11:16]}


def _planejar(con, acao, unidades, dados, momento, par):
    """Fase de LEITURA, dentro da transação: avalia todas as unidades. Retorna [(estado, resultado, campos)].

    Recusas de perfil/estado (403/422) interrompem na hora; conflitos de versão são juntados e viram um 409."""
    hoje = momento.strftime("%Y-%m-%d")
    nomes = [u for u, _ in unidades]
    registros, res_hoje, ultimas = _registros(con, nomes), _reservas_do_dia(con, hoje), _ultimas_saidas(con, hoje)
    eventos, quem = _ultimos_eventos(con), _quem()
    plano, conflitos = [], []
    for u, versao in unidades:
        estado = _estado(u, registros[u], res_hoje, ultimas, momento, par)
        try:
            resultado, campos = gov.avaliar(acao, estado, quem, momento, par, dados)
        except gov.Recusa as e:
            raise _erro(e)
        if resultado == "ok" and versao != estado["reg"]["versao"]:
            conflitos.append(_conflito(estado, estado["reg"]["versao"], eventos))
        plano.append((estado, resultado, campos))
    if conflitos:
        raise ErroApi("Algumas unidades foram alteradas por outra pessoa. Atualize e tente de novo.", 409, conflitos=conflitos)
    return plano


def _gravar(con, acao, estado, campos, lote, momento):
    """Atualiza a unidade (versão +1) e acrescenta o evento. Texto de observação/motivo NUNCA vai para o evento."""
    u, reg = estado["u"], estado["reg"]
    sets = ", ".join("%s=?" % c for c in campos)
    con.execute("UPDATE governanca_unidade SET %s, versao=versao+1 WHERE unidade=?" % sets, list(campos.values()) + [u])
    ator = ator_atual()
    de = reg["situacao"] if "situacao" in campos else None
    para = campos.get("situacao")
    con.execute("INSERT INTO governanca_evento (em, unidade, usuario_id, usuario_login, acao, de, para, lote, ip) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (momento.strftime(gov.FORMATO), u, ator["id"], ator["login"], acao, de, para, lote, ator["ip"]))
    if acao in ("manutencao_abrir", "manutencao_fechar"):
        registrar(con, acao, "governanca", None, None, {"unidade": u, "situacao": "manutencao"}, ator)
    elif g.usuario["papel"] == "admin" and acao == "suja" and reg["situacao"] == "pronta" and reg["situacao_por"] != ator["id"]:
        registrar(con, "governanca_correcao", "governanca", None, {"unidade": u, "situacao": "pronta"},
                  {"unidade": u, "situacao": "suja"}, ator)       # o administrador desfez o "pronto" de outra pessoa


@bp.route("/api/governanca/acao", methods=["POST"])
@exige("governanca.atualizar", "governanca.manutencao")
def acao():
    """Uma ou N unidades, tudo ou nada: qualquer erro desfaz a transação inteira e não grava evento."""
    acao_, unidades, dados = _validar_pedido(request.get_json(silent=True))
    if acao_ in ("manutencao_abrir", "manutencao_fechar"):
        exigir("governanca.manutencao")
    else:
        exigir("governanca.atualizar")
    momento, con, par = agora(), obter_con(), gov.parametros(current_app.config)
    lote = uuid.uuid4().hex
    resultados = []
    with transacao(con):
        plano = _planejar(con, acao_, unidades, dados, momento, par)
        for estado, resultado, campos in plano:
            versao = estado["reg"]["versao"]
            if resultado == "ok":
                _gravar(con, acao_, estado, campos, lote, momento)
                versao += 1
            resultados.append({"u": estado["u"], "resultado": resultado, "versao": versao})
    return jsonify({"ok": True, "lote": lote, "resultados": resultados})


# ---------------------------------------------------------------- GET /api/governanca/<unidade>/eventos

@bp.route("/api/governanca/<unidade>/eventos", methods=["GET"])
@exige("governanca.ver")
def eventos(unidade):
    """Últimos 50 eventos da unidade (a camareira vê só os de hoje). Sem IP e sem texto livre."""
    if unidade not in UNIDADES:
        raise ErroApi("Unidade não encontrada", 404)
    sql = "SELECT em, usuario_login, acao, de, para FROM governanca_evento WHERE unidade = ?"
    args = [unidade]
    if g.usuario["papel"] == "camareira":
        sql += " AND em >= ?"
        args.append(agora().strftime("%Y-%m-%d") + " 00:00:00")
    linhas = obter_con().execute(sql + " ORDER BY id DESC LIMIT ?", args + [MAX_EVENTOS]).fetchall()
    return jsonify([{"em": r["em"], "por": r["usuario_login"], "acao": r["acao"], "de": r["de"], "para": r["para"]} for r in linhas])
