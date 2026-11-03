"""Rotas da API de reservas, exportação e folha das camareiras."""
import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, current_app, g, jsonify, request

from . import despesas as desp
from . import hospedagem as hp
from . import notas as nt
from . import ocupacao as oc
from . import pagamentos as pg
from .ocupacao_pdf import gerar_pdf as pdf_ocupacao
from .camareiras import montar_folha
from .db import obter_con, transacao
from .erros import ErroApi
from .folha_pdf import ORIENTACOES, gerar_pdf, montar_semana
from .historico import diferenca, registrar, resumo_reserva
from .permissoes import exige, exigir, pode
from .regras import (ANO_MAX, ANO_MIN, MSG_CARTAO, agora, contem_numero_cartao, data_valida, existe_conflito,
                     status_do_erro, texto_limpo, validar_destino, validar_reserva)

bp = Blueprint("api", __name__)
CAMPOS = ["id", "a", "nome", "extras", "n", "i", "f", "p", "o", "grupo", "lote_id", "criado", "alterado", "versao", "status", "tipo"]
# O valor da diária (diaria_centavos) NÃO está em CAMPOS de propósito: só sai no detalhe e no CSV completo.
CAMPOS_CANCELAMENTO = ["motivo_cancelamento", "cancelado_por", "cancelado_em"]
MAX_MOTIVO = 300
CAMPOS_RESUMO = ["id", "a", "n", "i", "f"]
SQL_INSERIR = ("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,tipo,diaria_centavos) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)")


def hoje():
    return current_app.config.get("HOJE") or date.today()


def _linha(r, com_cancelamento=False):
    return {c: r[c] for c in CAMPOS + (CAMPOS_CANCELAMENTO if com_cancelamento else [])}


def valores_inserir(d):
    t = agora()
    return (d["a"], d["nome"], d["extras"], d["n"], d["i"], d["f"], d["p"], d["o"], d["grupo"] or "", t, t,
            d.get("tipo"), d.get("diaria_centavos"))


def _versao(corpo):
    """Lê o número da versão enviado pelo navegador (controle de edição simultânea)."""
    v = corpo.get("versao") if isinstance(corpo, dict) else None
    if not isinstance(v, int) or isinstance(v, bool):
        raise ErroApi("Informe a versão da reserva", 400)
    return v


def _buscar(con, rid):
    r = con.execute("SELECT * FROM reservas WHERE id=?", (rid,)).fetchone()
    if not r:
        raise ErroApi("Reserva não encontrada", 404)
    return r


def _sem_valor_se_nao_pode(corpo):
    """Quem não pode editar valores tem o campo da diária ignorado (o resto da reserva segue normal)."""
    if isinstance(corpo, dict) and "diaria_centavos" in corpo and not pode("valores.editar"):
        corpo = {k: v for k, v in corpo.items() if k != "diaria_centavos"}
    return corpo


def _so_pagamento_e_obs(atual, corpo):
    """Para quem só pode mexer em pagamento e observações: o resto vem da reserva já gravada."""
    base = {c: atual[c] for c in ("a", "nome", "extras", "n", "i", "f", "grupo")}
    base["p"] = corpo.get("p", atual["p"])
    base["o"] = corpo.get("o", atual["o"])
    return base


@bp.route("/")
def pagina():
    return current_app.send_static_file("index.html")


@bp.route("/api/reservas", methods=["GET"])
@exige("reservas.ver", "reservas.ver_resumo")
def listar():
    """Reservas ativas (as canceladas só aparecem com ?canceladas=1, para quem pode vê-las)."""
    canceladas = request.args.get("canceladas") == "1"
    if canceladas:
        exigir("reservas.ver_canceladas")
        linhas = obter_con().execute("SELECT * FROM reservas WHERE status='cancelada' ORDER BY cancelado_em DESC, id DESC").fetchall()
        return jsonify([_linha(r, True) for r in linhas])
    linhas = obter_con().execute("SELECT * FROM reservas WHERE status='ativa' ORDER BY i, a").fetchall()
    if not pode("reservas.ver"):           # camareira: só unidade, datas e nº de pessoas
        return jsonify([{c: r[c] for c in CAMPOS_RESUMO} for r in linhas])
    saida = [_linha(r) for r in linhas]
    com_nota = nt.reservas_com_nota(obter_con())           # só sim/não para o ponto "há observações" (nunca o texto)
    estados = {l["id"]: hp.estado(l) for l in linhas}
    for r in saida:
        r["tem_nota"] = r["id"] in com_nota
        r["estado_hospedagem"] = estados[r["id"]]
    if pode("despesas.ver"):               # só um indicador sim/não (nunca o valor) para o ponto do botão Despesas
        com = {rid for rid, _, _ in desp.reservas_com_saldo(obter_con())}
        for r in saida:
            r["tem_despesa"] = r["id"] in com
    return jsonify(saida)


@bp.route("/api/reservas", methods=["POST"])
@exige("reservas.criar")
def criar():
    dados, erro = validar_reserva(_sem_valor_se_nao_pode(request.get_json(silent=True)))
    if erro:
        raise ErroApi(erro, status_do_erro(erro))
    con = obter_con()
    with transacao(con):
        if existe_conflito(con, dados["a"], dados["i"], dados["f"]):
            raise ErroApi("Conflito: a unidade já está reservada nesse período", 409)
        novo = con.execute(SQL_INSERIR, valores_inserir(dados)).lastrowid
        registrar(con, "criar", "reserva", novo, None, resumo_reserva(dados))
    return jsonify(_linha(_buscar(con, novo))), 201


def _conferir_dinheiro_da_conta(con, atual, i, f, diaria):
    """Datas e diária mexem no total da conta: com a conta fechada nada muda, e o total nunca fica abaixo do já pago."""
    if (atual["i"], atual["f"], atual["diaria_centavos"]) == (i, f, diaria):
        return
    if desp.conta(con, atual["id"])["situacao"] == "fechada":
        raise ErroApi("A conta já foi fechada: reabra-a antes de mudar datas ou diária.", 409)
    if pg.liquido(con, atual["id"]):
        try:
            pg.conferir_total_cobre_pagamentos(con, atual, pg.total_conta(con, {"id": atual["id"], "i": i, "f": f, "diaria_centavos": diaria}))
        except desp.Recusa as e:
            raise ErroApi(e.mensagem, e.status)


@bp.route("/api/reservas/<int:rid>", methods=["PUT"])
@exige("reservas.editar", "reservas.editar_pagamento")
def alterar(rid):
    corpo = request.get_json(silent=True)
    versao = _versao(corpo)
    con = obter_con()
    with transacao(con):
        atual = _buscar(con, rid)
        if atual["status"] != "ativa":
            raise ErroApi("Esta reserva está cancelada. Reative-a antes de editar.", 409)
        antigos = ()
        if not pode("reservas.editar"):
            corpo = _so_pagamento_e_obs(atual, corpo)     # recepção: só p e o; o resto (inclusive tipo e diária) é mantido
            antigos = ("nome", "extras", "grupo")          # texto que ela não pode mudar não é conferido de novo
        corpo = _sem_valor_se_nao_pode(corpo)
        dados, erro = validar_reserva(corpo, antigos)
        if erro:
            raise ErroApi(erro, status_do_erro(erro))
        if atual["versao"] != versao:
            raise ErroApi("Esta reserva foi alterada por outra pessoa", 409)
        if existe_conflito(con, dados["a"], dados["i"], dados["f"], ignorar_id=rid):
            raise ErroApi("Conflito: a unidade já está reservada nesse período", 409)
        cadastrados = con.execute("SELECT COUNT(*) FROM hospedagem_hospede WHERE reserva_id=? AND titular=0", (rid,)).fetchone()[0]
        if dados["n"] < 1 + cadastrados:
            raise ErroApi("Há %d acompanhante(s) cadastrado(s): remova-os em Hóspedes antes de reduzir o número de pessoas" % cadastrados, 409)
        # tipo e diária: chave ausente = mantém o valor atual (a lista não traz a diária, então o cliente pode não conhecê-la)
        dados.setdefault("tipo", atual["tipo"])
        dados.setdefault("diaria_centavos", atual["diaria_centavos"])
        _conferir_dinheiro_da_conta(con, atual, dados["i"], dados["f"], dados["diaria_centavos"])
        con.execute(
            "UPDATE reservas SET a=?,nome=?,extras=?,n=?,i=?,f=?,p=?,o=?,grupo=COALESCE(?,grupo),"
            "tipo=?,diaria_centavos=?,alterado=?,versao=versao+1 WHERE id=?",
            (dados["a"], dados["nome"], dados["extras"], dados["n"], dados["i"], dados["f"],
             dados["p"], dados["o"], dados["grupo"], dados["tipo"], dados["diaria_centavos"], agora(), rid))
        antes, depois = diferenca(atual, dados)
        registrar(con, "alterar", "reserva", rid, antes, depois)
    return jsonify(_linha(_buscar(con, rid)))


def _versao_igual(atual, versao):
    if atual["versao"] != versao:
        raise ErroApi("Esta reserva foi alterada por outra pessoa", 409)


def _hospedagem(r):
    """Estado da hospedagem (check-in, conta aberta) e placa. A placa é dado pessoal: completa só para quem edita o veículo ou
    imprime a ficha; os demais recebem as 3 primeiras letras e asteriscos."""
    d = {c: r[c] for c in ("checkin_em", "checkin_por", "conta_aberta_em", "conta_aberta_por")}
    d["estado_hospedagem"] = hp.estado(r)
    if r["placa"]:
        completa = pode("veiculo.editar") or pode("ficha.imprimir")
        d["placa"] = hp.formatar_placa(r["placa"]) if completa else hp.mascarar_placa(r["placa"])
    else:
        d["placa"] = None
    return d


@bp.route("/api/reservas/<int:rid>", methods=["GET"])
@exige("reservas.ver")
def detalhe(rid):
    """Uma reserva, para quem clicou para vê-la. É o ÚNICO lugar (além do CSV completo) onde a diária sai."""
    r = _buscar(obter_con(), rid)
    cancelada = r["status"] != "ativa"
    if cancelada and not pode("reservas.ver_canceladas"):
        raise ErroApi("Reserva não encontrada", 404)
    corpo = _linha(r, cancelada)
    if pode("valores.ver"):
        corpo["diaria_centavos"] = r["diaria_centavos"]
    corpo.update(_hospedagem(r))
    return jsonify(corpo)


@bp.route("/api/reservas/<int:rid>/mover", methods=["POST"])
@exige("reservas.editar")
def mover(rid):
    """Troca a unidade e/ou as datas (arrastar no mapa). Só os campos enviados mudam; o resto vem da reserva."""
    corpo = request.get_json(silent=True)
    versao = _versao(corpo)
    con = obter_con()
    with transacao(con):
        atual = _buscar(con, rid)
        if atual["status"] != "ativa":
            raise ErroApi("Esta reserva está cancelada. Reative-a antes de mover.", 409)
        novo, erro = validar_destino(*(corpo.get(c, atual[c]) for c in ("a", "i", "f")))
        if erro:
            raise ErroApi(erro, 400)
        _versao_igual(atual, versao)
        if all(novo[c] == atual[c] for c in novo):
            return jsonify(_linha(atual))                     # nada mudou: não grava nem registra
        _conferir_dinheiro_da_conta(con, atual, novo["i"], novo["f"], atual["diaria_centavos"])
        if existe_conflito(con, novo["a"], novo["i"], novo["f"], ignorar_id=rid):
            raise ErroApi("Conflito: a unidade já está reservada nesse período", 409)
        con.execute("UPDATE reservas SET a=?,i=?,f=?,alterado=?,versao=versao+1 WHERE id=?",
                    (novo["a"], novo["i"], novo["f"], agora(), rid))
        antes, depois = diferenca(atual, {**resumo_reserva(atual), **novo, "nome": atual["nome"]})
        registrar(con, "mover", "reserva", rid, antes, depois)
    return jsonify(_linha(_buscar(con, rid)))


@bp.route("/api/reservas/<int:rid>", methods=["DELETE"])
@exige("reservas.cancelar")
def cancelar(rid):
    """DELETE cancela (não apaga): a reserva sai do mapa mas continua guardada, com o motivo."""
    corpo = request.get_json(silent=True)
    versao = _versao(corpo)
    motivo = corpo.get("motivo")
    if not isinstance(motivo, str) or not motivo.strip():
        raise ErroApi("Informe o motivo do cancelamento", 400)
    if len(motivo.strip()) > MAX_MOTIVO:
        raise ErroApi("Motivo grande demais (máximo %d caracteres)" % MAX_MOTIVO, 400)
    if not texto_limpo(motivo):      # mesma regra dos demais textos: sem controles invisíveis nem caracteres que invertem o texto
        raise ErroApi("Motivo contém caracteres não permitidos (controles invisíveis ou de inversão do texto)", 400)
    if contem_numero_cartao(motivo):
        raise ErroApi(MSG_CARTAO, 422)
    con = obter_con()
    with transacao(con):
        atual = _buscar(con, rid)
        _versao_igual(atual, versao)
        if atual["status"] != "ativa":
            raise ErroApi("Esta reserva já está cancelada", 409)
        if desp.saldo(con, rid)[0] > 0:
            raise ErroApi("Há despesas lançadas; estorne ou feche a conta antes de cancelar", 409)
        if pg.liquido(con, rid) > 0:
            raise ErroApi("Há pagamentos recebidos; estorne-os antes de cancelar", 409)
        con.execute("UPDATE reservas SET status='cancelada', motivo_cancelamento=?, cancelado_por=?, cancelado_em=?,"
                    " alterado=?, versao=versao+1 WHERE id=?",
                    (motivo.strip(), g.usuario["login"], agora(), agora(), rid))
        registrar(con, "cancelar", "reserva", rid, {"status": "ativa"}, {"status": "cancelada"})
    return jsonify(_linha(_buscar(con, rid), True))


@bp.route("/api/reservas/<int:rid>/reativar", methods=["POST"])
@exige("reservas.reativar")
def reativar(rid):
    """Volta uma reserva cancelada para o mapa, conferindo de novo se a unidade ainda está livre."""
    versao = _versao(request.get_json(silent=True))
    con = obter_con()
    with transacao(con):
        atual = _buscar(con, rid)
        _versao_igual(atual, versao)
        if atual["status"] != "cancelada":
            raise ErroApi("Esta reserva não está cancelada", 409)
        if existe_conflito(con, atual["a"], atual["i"], atual["f"], ignorar_id=rid):
            raise ErroApi("Conflito: a unidade já foi reservada por outra pessoa nesse período", 409)
        con.execute("UPDATE reservas SET status='ativa', motivo_cancelamento=NULL, cancelado_por=NULL, cancelado_em=NULL,"
                    " alterado=?, versao=versao+1 WHERE id=?", (agora(), rid))
        registrar(con, "reativar", "reserva", rid, {"status": "cancelada"}, {"status": "ativa"})
    return jsonify(_linha(_buscar(con, rid), True))


@bp.route("/api/reservas/<int:rid>/excluir-definitivo", methods=["POST"])
@exige("reservas.excluir_definitivo")
def excluir_definitivo(rid):
    """Apaga de verdade (só administrador). Fica registrado no histórico quais eram os dados."""
    versao = _versao(request.get_json(silent=True))
    con = obter_con()
    with transacao(con):
        atual = _buscar(con, rid)
        _versao_igual(atual, versao)
        if desp.tem_lancamento(con, rid):
            raise ErroApi("Esta reserva tem despesas lançadas e não pode ser excluída; cancele-a", 409)
        if con.execute("SELECT 1 FROM pagamento WHERE reserva_id=? LIMIT 1", (rid,)).fetchone():
            raise ErroApi("Esta reserva tem pagamentos registrados e não pode ser excluída; cancele-a", 409)
        if con.execute("SELECT 1 FROM conta_evento WHERE reserva_id=? LIMIT 1", (rid,)).fetchone():
            raise ErroApi("Esta reserva tem fechamento, reabertura ou diária zerada registrados na conta e não pode ser excluída; cancele-a", 409)
        if con.execute("SELECT 1 FROM nota WHERE reserva_id=? LIMIT 1", (rid,)).fetchone():
            raise ErroApi("Esta reserva tem notas registradas e não pode ser excluída; cancele-a", 409)
        registrar(con, "excluir", "reserva", rid, resumo_reserva(atual), None)
        con.execute("DELETE FROM reservas WHERE id=?", (rid,))
    return jsonify({"ok": True})


def _celula_csv(v):
    """Neutraliza injeção de fórmula: texto que começa com = + - @ (ou tab/CR) ganha um apóstrofo."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _reais(centavos):
    """Centavos inteiros em 'R$' pt-BR sem símbolo (ex.: 12345 -> '123,45'); vazio se não informado."""
    return "" if centavos is None else "%d,%02d" % divmod(centavos, 100)


@bp.route("/api/export.csv")
def exportar():
    """Backup completo; com ?inicio=AAAA-MM-DD&dias=7 gera a folha do período."""
    inicio = request.args.get("inicio")
    con = obter_con()
    exigir("folha.ver" if inicio else "export.completo")
    if inicio:
        d0 = data_valida(inicio)
        try:
            dias = int(request.args.get("dias", 7))
        except ValueError:      # inclui texto e número gigante demais para o int()
            dias = 0
        if not d0 or dias < 1 or dias > 366 or not (ANO_MIN <= d0.year <= ANO_MAX):
            raise ErroApi("Período inválido", 400)
        fim = (d0 + timedelta(days=dias)).isoformat()
        linhas = con.execute("SELECT * FROM reservas WHERE status='ativa' AND i < ? AND f >= ? ORDER BY i, a",
                             (fim, d0.isoformat())).fetchall()
        nome = "folha_%s.csv" % d0.isoformat()
    else:
        linhas = con.execute("SELECT * FROM reservas ORDER BY id").fetchall()
        nome = "backup_reservas.csv"
    com_diaria = not inicio and pode("valores.ver")      # a diária só vai no CSV completo, para quem pode vê-la
    colunas = CAMPOS + (CAMPOS_CANCELAMENTO if not inicio else [])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(colunas + (["diaria"] if com_diaria else []))
    for r in linhas:
        w.writerow([_celula_csv(r[c]) for c in colunas] + ([_reais(r["diaria_centavos"])] if com_diaria else []))
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=" + nome})


@bp.route("/api/folha.pdf")
@exige("folha.ver")
def folha_pdf():
    """Folha da semana em PDF. ?inicio=AAAA-MM-DD (a semana de 7 dias que começa nesse dia)."""
    inicio = data_valida(request.args.get("inicio") or "")
    if not inicio:
        raise ErroApi("Informe a data de início (AAAA-MM-DD)", 400)
    if not (ANO_MIN <= inicio.year <= ANO_MAX):
        raise ErroApi("O ano da data deve estar entre %d e %d" % (ANO_MIN, ANO_MAX), 400)
    orientacao = request.args.get("orientacao") or "paisagem"
    if orientacao not in ORIENTACOES:
        raise ErroApi("Orientação inválida (use paisagem ou retrato)", 400)
    pdf = gerar_pdf(montar_semana(obter_con(), inicio), inicio, orientacao=orientacao)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=folha_%s.pdf" % inicio.isoformat()})


def _relatorio_ocupacao():
    """Valida ?inicio&fim&orientacao e monta o relatório. Nome e grupo só para quem tem reservas.ver (a camareira não)."""
    d0, d1, erro = oc.validar_periodo(request.args.get("inicio") or "", request.args.get("fim") or "")
    if erro:
        raise ErroApi(erro, 400)
    orientacao = request.args.get("orientacao") or "paisagem"
    if orientacao not in oc.ORIENTACOES:
        raise ErroApi("Orientação inválida (use paisagem ou retrato)", 400)
    dados = oc.montar(obter_con(), d0, d1, com_nomes=pode("reservas.ver"))
    return oc.dividir(dados, orientacao)


@bp.route("/api/ocupacao", methods=["GET"])
@exige("reservas.ver", "reservas.ver_resumo")
def ocupacao():
    """Relatório de ocupação de um período (máximo 92 dias): grade unidade x dia em blocos, totais e resumo. Sem valores."""
    rel = _relatorio_ocupacao()
    rel["emitido_por"] = g.usuario["nome"] or g.usuario["login"]
    return jsonify(rel)


@bp.route("/api/ocupacao.pdf", methods=["GET"])
@exige("reservas.ver", "reservas.ver_resumo")
def ocupacao_pdf():
    rel = _relatorio_ocupacao()
    pdf = pdf_ocupacao(rel, g.usuario["nome"] or g.usuario["login"])
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": "attachment; filename=ocupacao_%s_a_%s.pdf" % (rel["inicio"], rel["fim"])})


@bp.route("/api/camareiras", methods=["GET"])
@exige("camareiras.ver")
def camareiras():
    """Movimento por dia para as camareiras (sem valores, pagamento ou telefone)."""
    dia = hoje()
    inicio = request.args.get("inicio") or dia.isoformat()
    fim = request.args.get("fim") or (dia + timedelta(days=6)).isoformat()
    folha, erro = montar_folha(obter_con(), inicio, fim, request.args.get("estadias") == "1",
                               request.args.get("nomes") == "1" and pode("reservas.ver"))   # camareira nunca vê nomes
    if erro:
        raise ErroApi(erro, 400)
    return jsonify(folha)
