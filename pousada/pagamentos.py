"""Pagamentos da conta (dinheiro, Pix e cartão): validação PURA, parcelas, saldo e consultas.

Tudo em centavos inteiros. Sem Flask e sem permissão (as rotas decidem). NUNCA entra número de cartão, CVV ou validade:
só bandeira, modalidade, parcelas e um código curto de autorização/NSU ([A-Za-z0-9], até 12). O log é imutável (migração 015).
"""
import re

from .cartao import MSG_CARTAO, _luhn, contem_numero_cartao
from .despesas import Recusa, noites, reais, saldo as saldo_despesas
from .regras import MAX_DIARIA_CENTAVOS

FORMAS = ("dinheiro", "pix", "cartao")
MODALIDADES = ("credito", "debito")
MAX_PAGAMENTOS = 100
MAX_ITENS = 201
_RE_COD = re.compile(r"^[A-Za-z0-9]+$", re.ASCII)
_RE_ITEM = re.compile(r"^(diaria|d[1-9][0-9]{0,9})$", re.ASCII)
_ROTULO_FORMA = {"dinheiro": "Dinheiro", "pix": "Pix", "cartao": "Cartão"}


def inteiro(v):
    return isinstance(v, int) and not isinstance(v, bool)


def rotulo_forma(f):
    return _ROTULO_FORMA.get(f, f)


def chave_valida(v, obrigatoria=True):
    """Chave anti-duplo clique: 8 a 64 caracteres ASCII (letras, números, hífen, sublinhado)."""
    if v is None and not obrigatoria:
        return None
    if not (isinstance(v, str) and 8 <= len(v) <= 64 and v.isascii() and v.replace("-", "").replace("_", "").isalnum()):
        raise Recusa("Chave de envio inválida")
    sem_sep = v.replace("-", "").replace("_", "")
    if sem_sep.isdigit() and 13 <= len(sem_sep) <= 19 and _luhn(sem_sep):
        raise Recusa("Chave de envio inválida")       # a chave é gravada: nunca pode ser um número de cartão disfarçado
    return v


def versao_valida(v, nome="conta_versao"):
    if not inteiro(v) or v < 1 or v > 2 ** 31:
        raise Recusa("Informe a versão da conta (%s)" % nome, 400)
    return v


def codigo_curto(v, rotulo, maximo):
    """Código de autorização/NSU ou referência do Pix: só letras e números, sem espaço. Vazio = ausente. Nunca repete o texto."""
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise Recusa("%s inválido" % rotulo.capitalize())
    if contem_numero_cartao(v) or re.fullmatch(r"\s*\d{13,}\s*", v):
        raise Recusa(MSG_CARTAO)
    v = v.strip()
    if not _RE_COD.match(v):
        raise Recusa("%s deve ter só letras e números, sem espaços ou símbolos" % rotulo.capitalize())
    if len(v) > maximo:
        raise Recusa("%s deve ter no máximo %d caracteres" % (rotulo.capitalize(), maximo))
    return v


def parcelas_valores(valor, n):
    """Valor de cada parcela em centavos: a soma é SEMPRE o valor; as primeiras parcelas absorvem os centavos que sobram."""
    base, resto = divmod(valor, n)
    return [base + 1] * resto + [base] * (n - resto)


def validar_itens(v):
    """Lista opcional de itens quitados ('diaria', 'd12'...): sem repetição, formato fixo."""
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > MAX_ITENS:
        raise Recusa("Lista de itens inválida", 400)
    if not all(isinstance(i, str) and _RE_ITEM.fullmatch(i) for i in v) or len(set(v)) != len(v):
        raise Recusa("Lista de itens inválida", 400)
    return list(v)


def _so_se(forma, esperada, corpo, campos):
    if forma != esperada and any(corpo.get(c) not in (None, "") for c in campos):
        raise Recusa("Há campo que não se aplica a esta forma de pagamento")


def _cartao(corpo, valor, cfg):
    if corpo.get("bandeira") not in cfg["PAG_BANDEIRAS"]:
        raise Recusa("Escolha a bandeira do cartão")
    if corpo.get("modalidade") not in MODALIDADES:
        raise Recusa("Escolha crédito ou débito")
    p = corpo.get("parcelas")
    if p is None or p == "":
        p = 1
    maximo = cfg["PAG_MAX_PARCELAS"]
    if not inteiro(p) or not 1 <= p <= maximo:
        raise Recusa("Número de parcelas inválido (de 2 a %d; 1 = à vista)" % maximo)
    if corpo["modalidade"] == "debito" and p != 1:
        raise Recusa("Débito não pode ser parcelado")
    if p > 1 and min(parcelas_valores(valor, p)) < cfg["PAG_PARCELA_MIN_CENTAVOS"]:
        raise Recusa("Cada parcela deve ter no mínimo %s" % reais(cfg["PAG_PARCELA_MIN_CENTAVOS"]))
    return {"bandeira": corpo["bandeira"], "modalidade": corpo["modalidade"], "parcelas": p,
            "autorizacao": codigo_curto(corpo.get("autorizacao"), "o código de autorização", 12)}


def validar_recebimento(corpo, cfg):
    """Corpo do POST -> dict limpo. Levanta Recusa. A conferência contra o saldo é feita pela rota, dentro da transação."""
    if not isinstance(corpo, dict):
        raise Recusa("Envie os dados em um objeto JSON", 400)
    forma, valor = corpo.get("forma"), corpo.get("valor_centavos")
    if forma not in FORMAS:
        raise Recusa("Forma de pagamento inválida (dinheiro, Pix ou cartão)")
    if not inteiro(valor) or valor < 1:
        raise Recusa("Informe um valor maior que zero")
    if valor > MAX_DIARIA_CENTAVOS:
        raise Recusa("Valor acima do máximo permitido (%s)" % reais(MAX_DIARIA_CENTAVOS))
    _so_se(forma, "cartao", corpo, ("bandeira", "modalidade", "parcelas", "autorizacao"))
    _so_se(forma, "pix", corpo, ("referencia",))
    _so_se(forma, "dinheiro", corpo, ("recebido_centavos",))
    out = {"forma": forma, "valor_centavos": valor, "chave": chave_valida(corpo.get("chave")),
           "conta_versao": versao_valida(corpo.get("conta_versao")), "itens": validar_itens(corpo.get("itens")),
           "recebido_centavos": None, "troco_centavos": None, "bandeira": None, "modalidade": None, "parcelas": None,
           "autorizacao": None, "referencia": None}
    if forma == "cartao":
        out.update(_cartao(corpo, valor, cfg))
    elif forma == "pix":
        out["referencia"] = codigo_curto(corpo.get("referencia"), "a referência do Pix", 32)
    else:
        rec = corpo.get("recebido_centavos")
        if rec not in (None, ""):
            if not inteiro(rec) or rec < valor or rec > MAX_DIARIA_CENTAVOS:
                raise Recusa("O valor entregue em dinheiro não pode ser menor que o valor recebido")
            out["recebido_centavos"], out["troco_centavos"] = rec, rec - valor
    return out


# ---------------------------------------------------------------- consultas ao banco

def total_conta(con, r):
    """Total a pagar da hospedagem: diárias (0 se não informada) + despesas líquidas. r: linha com id, i, f, diaria_centavos."""
    soma, _ = saldo_despesas(con, r["id"])
    return (r["diaria_centavos"] or 0) * noites(r["i"], r["f"]) + soma


def liquido(con, rid):
    """Pagamentos recebidos menos estornados (centavos). Estorno é linha negativa."""
    return con.execute("SELECT COALESCE(SUM(valor_centavos),0) FROM pagamento WHERE reserva_id=?", (rid,)).fetchone()[0]


def saldo(con, r):
    return total_conta(con, r) - liquido(con, r["id"])


def conferir_total_cobre_pagamentos(con, r, novo_total):
    """Regra: o total da conta nunca fica abaixo do que já foi pago. Antes, estorne o pagamento."""
    if novo_total < liquido(con, r["id"]):
        raise Recusa("A conta já tem pagamentos acima do novo total. Estorne antes o pagamento correspondente.", 409)


def linhas(con, rid):
    return con.execute("SELECT * FROM pagamento WHERE reserva_id=? ORDER BY id", (rid,)).fetchall()


def item(l, estornos):
    """Linha do banco -> item da API."""
    p = l["parcelas"]
    return {"id": l["id"], "tipo": l["tipo"], "forma": l["forma"], "valor_centavos": l["valor_centavos"],
            "recebido_centavos": l["recebido_centavos"], "troco_centavos": l["troco_centavos"], "bandeira": l["bandeira"],
            "modalidade": l["modalidade"], "parcelas": p, "autorizacao": l["autorizacao"], "referencia": l["referencia"],
            "parcelas_valores": parcelas_valores(abs(l["valor_centavos"]), p) if p and p > 1 else None,
            "itens": [i for i in l["itens"].split(",") if i], "em": l["em"], "por": l["usuario_login"],
            "estorno_de": l["estorno_de"], "estornado": l["id"] in estornos, "estorno_id": estornos.get(l["id"]),
            "motivo": l["motivo"]}


def itens(ls):
    estornos = {l["estorno_de"]: l["id"] for l in ls if l["estorno_de"]}
    return [item(l, estornos) for l in sorted(ls, key=lambda x: -x["id"])]
