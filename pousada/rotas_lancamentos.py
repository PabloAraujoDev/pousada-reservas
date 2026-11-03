"""Info (i): lista SOMENTE LEITURA de tudo o que aconteceu na conta da hospedagem, em ordem cronológica.

Junta lançamentos, estornos, transferências (saída e entrada), pagamentos (só com pagamentos.ver), fechamentos, reaberturas e diária
zerada, cada um com autor, data/hora e motivo. Nunca devolve NSU, referência do Pix nem dado de cartão: isso fica na tela de pagamentos.
"""
from flask import Blueprint, jsonify

from . import despesas as desp
from . import pagamentos as pg
from .db import obter_con
from .permissoes import exige, pode
from .rotas_despesas import _reserva

bp = Blueprint("lancamentos", __name__)
GRUPOS = ("lancamento", "estorno", "transferencia", "pagamento", "conta")
_ORDEM = {"despesa": 0, "pagamento": 1, "conta": 2}


def _transf(con, rid):
    sql = "SELECT * FROM transferencia WHERE origem_id=? OR destino_id=?"
    return {t["id"]: t for t in con.execute(sql, (rid, rid))}


def _despesas(con, rid):
    transf, saida = _transf(con, rid), []
    for l in con.execute("SELECT * FROM despesa_lancamento WHERE reserva_id=? ORDER BY id", (rid,)):
        t = transf.get(l["transferencia_id"])
        if t and l["tipo"] == "estorno":
            tipo, grupo, texto = "transferencia_saida", "transferencia", "Transferido para #%d (apto %s): %s" % (t["destino_id"], t["apto_destino"], l["descricao"])
        elif t:
            tipo, grupo, texto = "transferencia_entrada", "transferencia", "Recebido da reserva #%d (apto %s): %s" % (t["origem_id"], t["apto_origem"], l["descricao"])
        else:
            tipo, grupo, texto = l["tipo"], l["tipo"], ("Estorno: " if l["tipo"] == "estorno" else "") + l["descricao"]
        saida.append({"origem": "despesa", "id": l["id"], "tipo": tipo, "grupo": grupo, "descricao": texto, "total_centavos": l["total_centavos"],
                      "em": l["em"], "por": l["usuario_login"], "motivo": l["motivo"], "transferencia_id": l["transferencia_id"]})
    return saida


def _pagamentos(con, rid):
    saida = []
    for l in con.execute("SELECT * FROM pagamento WHERE reserva_id=? ORDER BY id", (rid,)):
        txt = pg.rotulo_forma(l["forma"]) + (" %s %s" % (l["bandeira"], "crédito" if l["modalidade"] == "credito" else "débito") if l["forma"] == "cartao" else "")
        if l["parcelas"] and l["parcelas"] > 1:
            txt += " em %dx" % l["parcelas"]
        est = l["tipo"] == "estorno"
        saida.append({"origem": "pagamento", "id": l["id"], "tipo": "pagamento_estorno" if est else "pagamento", "grupo": "pagamento",
                      "descricao": ("Estorno de pagamento: " if est else "Pagamento: ") + txt, "total_centavos": l["valor_centavos"],
                      "em": l["em"], "por": l["usuario_login"], "motivo": l["motivo"], "transferencia_id": None})
    return saida


_ROTULO_CONTA = {"fechar": ("conta_fechada", "Conta fechada"), "reabrir": ("conta_reaberta", "Conta reaberta"),
                 "diaria_zerar": ("diaria_zerada", "Diária zerada")}


def _eventos(con, rid):
    saida = []
    for l in con.execute("SELECT * FROM conta_evento WHERE reserva_id=? ORDER BY id", (rid,)):
        tipo, texto = _ROTULO_CONTA[l["acao"]]
        saida.append({"origem": "conta", "id": l["id"], "tipo": tipo, "grupo": "transferencia" if l["transferencia_id"] else "conta", "descricao": texto,
                      "total_centavos": -l["valor_centavos"] if l["valor_centavos"] else None, "em": l["em"], "por": l["usuario_login"],
                      "motivo": l["motivo"], "transferencia_id": l["transferencia_id"]})
    return saida


@bp.route("/api/reservas/<int:rid>/lancamentos", methods=["GET"])
@exige("despesas.ver")
def listar(rid):
    con = obter_con()
    _reserva(con, rid)
    linhas = _despesas(con, rid) + _eventos(con, rid) + (_pagamentos(con, rid) if pode("pagamentos.ver") else [])
    linhas.sort(key=lambda x: (x["em"], _ORDEM[x["origem"]], x["id"]))
    return jsonify({"itens": linhas, "grupos": list(GRUPOS)})
