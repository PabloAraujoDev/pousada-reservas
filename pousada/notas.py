"""Notas (anotações com autor e data) da reserva e do apartamento: regras puras e consultas ao banco.

O log (tabela nota, migração 013) é imutável: corrigir = nova linha 'correcao'; apagar = linha 'ocultar'.
Aqui não há Flask nem permissão; quem decide o que cada perfil recebe são as rotas (rotas_notas.py).
O texto da nota nunca vai para o histórico, para logs nem para mensagens de erro.
"""
from datetime import datetime, timedelta

from .despesas import Recusa, texto_validado

MAX_NOTA = 300            # caracteres por nota (o banco também confere)
MAX_NOTAS = 100           # notas por reserva e por unidade (trigger do banco)
MAX_CORRECOES = 20        # correções por nota
JANELA_AUTOR = timedelta(hours=24)       # o autor corrige/oculta a própria nota até 24 h depois; depois, só quem edita reservas
FORMATO = "%Y-%m-%d %H:%M:%S"


def validar_texto(corpo):
    """Texto da nota (1 a 300 caracteres, sem controles invisíveis e sem cara de número de cartão)."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    return texto_validado(corpo.get("texto"), "a nota", 1, MAX_NOTA)


def validar_motivo(corpo):
    """Motivo de ocultar: 3 a 140 caracteres."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    return texto_validado(corpo.get("motivo"), "o motivo", 3, 140)


def validar_chave(corpo):
    """Chave de envio (anti duplo clique): opcional, 8 a 64 letras/números/hífen."""
    c = corpo.get("chave")
    if c is None:
        return None
    if not (isinstance(c, str) and 8 <= len(c) <= 64 and c.isascii() and c.replace("-", "").replace("_", "").isalnum()):
        raise Recusa("Chave de envio inválida")
    return c


def validar_versao(corpo):
    v = corpo.get("versao") if isinstance(corpo, dict) else None
    if not isinstance(v, int) or isinstance(v, bool):
        raise Recusa("Informe a versão da nota", 400)
    return v


# ---------------------------------------------------------------- montagem da cadeia de linhas

def _nova(l):
    return {"id": l["id"], "escopo": l["escopo"], "autor_id": l["usuario_id"], "em_original": l["em"],
            "versoes": [{"texto": l["texto"], "por": l["usuario_login"], "em": l["em"]}],
            "oculta": False, "oculta_por": None, "oculta_em": None, "oculta_motivo": ""}


def montar(linhas):
    """Linhas do log (ordem de id, de UM escopo) -> [nota] em ordem de criação, já dobrando correções e ocultações."""
    notas = {}
    for l in linhas:
        if l["tipo"] == "nota":
            notas[l["id"]] = _nova(l)
        elif l["nota_ref"] in notas:
            n = notas[l["nota_ref"]]
            if l["tipo"] == "correcao":
                n["versoes"].append({"texto": l["texto"], "por": l["usuario_login"], "em": l["em"]})
            else:
                n.update(oculta=True, oculta_por=l["usuario_login"], oculta_em=l["em"], oculta_motivo=l["motivo"])
    return list(notas.values())


def versao(n):
    """Número de versões da nota (1 + correções): é o que o navegador devolve para provar que viu a última."""
    return len(n["versoes"])


def atual(n):
    return n["versoes"][-1]


def dentro_da_janela(n, momento):
    try:
        return momento - datetime.strptime(n["em_original"], FORMATO) <= JANELA_AUTOR
    except ValueError:
        return False


# ---------------------------------------------------------------- consultas

def linhas_do_escopo(con, reserva_id=None, unidade=None):
    if reserva_id is not None:
        return con.execute("SELECT * FROM nota WHERE escopo='reserva' AND reserva_id=? ORDER BY id", (reserva_id,)).fetchall()
    return con.execute("SELECT * FROM nota WHERE escopo='unidade' AND unidade=? ORDER BY id", (unidade,)).fetchall()


def buscar(con, nid):
    """(nota dobrada, linha original) com esse id; (None, None) se não existir ou se o id for de uma correção."""
    ref = con.execute("SELECT * FROM nota WHERE id=? AND tipo='nota'", (nid,)).fetchone()
    if not ref:
        return None, None
    linhas = linhas_do_escopo(con, ref["reserva_id"], ref["unidade"])
    return next((n for n in montar(linhas) if n["id"] == nid), None), ref


def contagem(con, reserva_id=None, unidade=None):
    """Quantas notas (de qualquer estado) o escopo já tem: o limite conta todas, pois o log só cresce."""
    return sum(1 for l in linhas_do_escopo(con, reserva_id, unidade) if l["tipo"] == "nota")


def tem_nota_visivel(con, reserva_id):
    return any(not n["oculta"] for n in montar(linhas_do_escopo(con, reserva_id)))


_VISIVEIS = ("FROM nota n WHERE n.tipo='nota' AND n.escopo=? "
             "AND NOT EXISTS (SELECT 1 FROM nota o WHERE o.nota_ref=n.id AND o.tipo='ocultar')")


def reservas_com_nota(con):
    """Ids das reservas que têm ao menos uma nota NÃO oculta (só um sim/não para o ponto "há observações"; nunca o texto)."""
    return {r[0] for r in con.execute("SELECT DISTINCT n.reserva_id " + _VISIVEIS, ("reserva",))}


def unidades_com_nota(con):
    """Apartamentos com ao menos uma nota do apartamento não oculta."""
    return {r[0] for r in con.execute("SELECT DISTINCT n.unidade " + _VISIVEIS, ("unidade",))}
