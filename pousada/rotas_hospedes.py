"""Rotas da lista de hóspedes da hospedagem (titular + acompanhantes): GET e PUT /api/reservas/<id>/hospedes.

PRIVACIDADE: documento, nascimento, nacionalidade, profissão, procedência e destino são dados pessoais. Só quem tem hospedes.gerir
ou ficha.imprimir recebe tudo; os demais (diretoria, consulta) recebem nome, tipo e o documento MASCARADO. O histórico e o log da
hospedagem guardam só contagens e nomes de campos, nunca valores. CSRF, login e Origin são conferidos em seguranca.py.
"""
from flask import Blueprint, jsonify, request

from . import hospedagem as hp
from .db import obter_con, transacao
from .despesas import Recusa
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import exige, pode
from .regras import agora as agora_texto
from .rotas_governanca import agora

bp = Blueprint("hospedes", __name__)
COLUNAS = ("tipo", "documento", "nascimento", "nacionalidade", "profissao", "procedencia", "destino")


def reserva_ou_erro(con, rid, escrita=False):
    """Reserva existente. Cancelada: some (404) para quem não vê canceladas; para escrita, 409."""
    r = con.execute("SELECT * FROM reservas WHERE id=?", (rid,)).fetchone()
    if not r or (r["status"] != "ativa" and not pode("reservas.ver_canceladas")):
        raise ErroApi("Reserva não encontrada", 404)
    if escrita and r["status"] != "ativa":
        raise ErroApi("Esta reserva está cancelada. Reative-a antes.", 409)
    return r


def versao_igual(r, versao):
    if r["versao"] != versao:
        raise ErroApi("Esta reserva foi alterada por outra pessoa", 409)


def registrar_evento(con, rid, acao, detalhe, momento):
    """Acrescenta ao log imutável da hospedagem (sem dado pessoal em 'detalhe')."""
    a = ator_atual()
    con.execute("INSERT INTO hospedagem_evento (reserva_id, acao, detalhe, em, usuario_id, usuario_login, ip) VALUES (?,?,?,?,?,?,?)",
                (rid, acao, detalhe, momento.strftime("%Y-%m-%d %H:%M:%S"), a["id"], a["login"], a["ip"]))


def ve_dados_pessoais():
    return pode("hospedes.gerir") or pode("ficha.imprimir")


def _pessoa(linha, nome, completo):
    """Hóspede -> JSON. Sem permissão: nome, tipo e documento mascarado (os outros campos pessoais nem saem)."""
    d = {"id": linha["id"], "nome": nome, "tipo": linha["tipo"]}
    if completo:
        d.update({c: linha[c] for c in COLUNAS if c != "tipo"})
    else:
        d["documento"] = hp.mascarar_documento(linha["documento"])
    return d


def montar(con, r, completo):
    linhas = con.execute("SELECT * FROM hospedagem_hospede WHERE reserva_id=? ORDER BY ordem, id", (r["id"],)).fetchall()
    tit = next((l for l in linhas if l["titular"]), None)
    vazio = {c: None for c in COLUNAS}
    vazio.update(id=None, tipo="adulto")
    return {"versao": r["versao"], "n": r["n"], "pode_editar": pode("hospedes.gerir") and r["status"] == "ativa",
            "dados_completos": completo,
            "titular": _pessoa(tit or vazio, r["nome"], completo),
            "acompanhantes": [_pessoa(l, l["nome"], completo) for l in linhas if not l["titular"]]}


@bp.route("/api/reservas/<int:rid>/hospedes", methods=["GET"])
@exige("reservas.ver")
def listar(rid):
    con = obter_con()
    return jsonify(montar(con, reserva_ou_erro(con, rid), ve_dados_pessoais()))


def _valores(p):
    return [p["nome"], p["tipo"], p["documento"], p["nascimento"], p["nacionalidade"], p["profissao"], p["procedencia"], p["destino"]]


def _gravar_titular(con, rid, novo, atuais):
    """Cria ou atualiza a linha do titular; devolve True se algo mudou."""
    tit = next((l for l in atuais if l["titular"]), None)
    if tit is None:
        if all(novo[c] is None for c in hp.CAMPOS_PESSOAIS) and novo["tipo"] == "adulto":
            return False                      # nada informado: não cria linha vazia
        con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, ordem, nome, tipo, documento, nascimento, nacionalidade,"
                    " profissao, procedencia, destino) VALUES (?,1,0,NULL,?,?,?,?,?,?,?)", [rid] + _valores(novo)[1:])
        return True
    if hp.campos_diferentes(dict(tit), novo) == []:
        return False
    con.execute("UPDATE hospedagem_hospede SET tipo=?, documento=?, nascimento=?, nacionalidade=?, profissao=?, procedencia=?,"
                " destino=? WHERE id=?", _valores(novo)[1:] + [tit["id"]])
    return True


def _gravar_acompanhantes(con, rid, novos, atuais):
    """Insere, atualiza e remove (de verdade) os acompanhantes. Devolve (adicionados, alterados, removidos)."""
    por_id = {l["id"]: l for l in atuais if not l["titular"]}
    add = alt = 0
    for ordem, p in enumerate(novos, start=1):
        if p["id"] is None:
            con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, ordem, nome, tipo, documento, nascimento, nacionalidade,"
                        " profissao, procedencia, destino) VALUES (?,0,?,?,?,?,?,?,?,?,?)", [rid, ordem] + _valores(p))
            add += 1
        elif p["id"] not in por_id:
            raise ErroApi("Hóspede não encontrado nesta reserva", 422)
        else:
            antigo = por_id.pop(p["id"])
            if hp.campos_diferentes(dict(antigo), p) or antigo["ordem"] != ordem:
                con.execute("UPDATE hospedagem_hospede SET ordem=?, nome=?, tipo=?, documento=?, nascimento=?, nacionalidade=?,"
                            " profissao=?, procedencia=?, destino=? WHERE id=?", [ordem] + _valores(p) + [p["id"]])
                alt += 1
    for sobra in por_id.values():           # o que ficou de fora da lista foi removido
        con.execute("DELETE FROM hospedagem_hospede WHERE id=?", (sobra["id"],))
    return add, alt, len(por_id)


@bp.route("/api/reservas/<int:rid>/hospedes", methods=["PUT"])
@exige("hospedes.gerir")
def salvar(rid):
    momento = agora()
    con = obter_con()
    corpo = request.get_json(silent=True)
    with transacao(con):
        r = reserva_ou_erro(con, rid, escrita=True)
        try:
            versao, titular, acomp = hp.validar_lista(corpo, r["n"], momento.strftime("%Y-%m-%d"))
        except Recusa as e:
            raise ErroApi(e.mensagem, e.status)
        versao_igual(r, versao)
        atuais = con.execute("SELECT * FROM hospedagem_hospede WHERE reserva_id=?", (rid,)).fetchall()
        mudou_tit = _gravar_titular(con, rid, titular, atuais)
        add, alt, rem = _gravar_acompanhantes(con, rid, acomp, atuais)
        if mudou_tit or add or alt or rem:
            con.execute("UPDATE reservas SET alterado=?, versao=versao+1 WHERE id=?", (agora_texto(), rid))
            registrar_evento(con, rid, "hospedes", "titular=%s adicionados=%d alterados=%d removidos=%d"
                             % ("sim" if mudou_tit else "nao", add, alt, rem), momento)
            registrar(con, "hospedes_alterados", "reserva", rid, None, {"itens": add + alt + rem + int(mudou_tit)})
        corpo_resp = montar(con, reserva_ou_erro(con, rid), True)
    return jsonify(corpo_resp)
