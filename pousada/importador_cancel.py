"""Seção CANCELAMENTOS da planilha: leitura tolerante de texto livre (nada aqui grava no banco).

Cada linha vira um item com: linha, unidades[], hospede, entrada, saida, texto (original, curto), ok, motivo.
Linha que não dá para interpretar vira item com ok=False (informativo: nunca cancela nada).
Este módulo importa o importador; o importador só o importa dentro das funções (evita import circular).
"""
import re
from datetime import date, datetime

from .importador import ErroLinha, calcular_periodo, normalizar_apto, sem_acento_maiusc, texto_celula
from .regras import MSG_CARTAO, contem_numero_cartao

MAX_TEXTO = 300
MAX_NOME = 120
POSTOS = ("CEL", "TEN", "CAP", "MAJ", "TC", "SGT", "SD", "CB", "ST", "SO", "BRIG", "GEN", "CORONEL", "TENENTE",
          "CAPITAO", "MAJOR", "SARGENTO", "DR", "DRA")

_PREF = r"(?:(?:APARTAMENTOS?|APTOS?|APTS?|AP)\.?\s*)?"
_UNID = r"(?:CHALE\s*[A-Z]\b|\d{3}\b)"
_RE_LISTA = re.compile(r"^" + _PREF + _UNID + r"(?:\s*(?:/|,|\+|&|-|\bE\b)\s*" + _PREF + _UNID + r")*")
_RE_UNID = re.compile(r"CHALE\s*([A-Z])\b|\b(\d{3})\b")
_RE_SEP_NOME = re.compile(r"\s+[-–]+\s+|\s*\|\s*")


def ler_cancelamentos(linhas, maximo=None):
    """Linhas brutas da seção CANCELAMENTOS de uma aba: [{linha, a, b, c, d, e}] (títulos e totais ficam de fora)."""
    saida, dentro = [], False
    for numero, lin in enumerate(linhas, start=1):
        a, b, c, d, e = (texto_celula(x) for x in lin)
        a_n, b_n = sem_acento_maiusc(a), sem_acento_maiusc(b)
        if a_n.startswith("CANCELAMENTO") or b_n.startswith("CANCELAMENTO"):
            dentro = True
            continue
        if not dentro:
            continue
        if a_n == "APTO" or a_n.startswith("LISTA DE ESPERA") or b_n.startswith("LISTA DE ESPERA") or \
                a_n.startswith(("HOSPEDAGEM", "TOTAL")) or b_n.startswith(("HOSPEDAGEM", "TOTAL")):
            dentro = False
            continue
        if isinstance(lin[0], (date, datetime)):      # data em que a pessoa cancelou: não é texto da reserva
            a = ""
        if any((a, b, c, d, e)):
            saida.append({"linha": numero, "a": a, "b": b, "c": c, "d": d, "e": e})
            if maximo is not None and len(saida) >= maximo:
                break
    return saida


def extrair_unidades(texto_norm):
    """(unidades, resto, inexistentes): lista de unidades no INÍCIO do texto já normalizado.

    Aceita '305', '204 E 304', '303/304', '203,204', 'APTOS 207/208 E CHALE C', 'CHALE E'.
    """
    m = _RE_LISTA.match(texto_norm)
    if not m:
        return [], texto_norm, []
    unidades, inexistentes = [], []
    for letra, num in _RE_UNID.findall(m.group(0)):
        u = normalizar_apto(("CHALE " + letra) if letra else num)
        if not u:
            inexistentes.append(letra or num)
        elif u not in unidades:
            unidades.append(u)
    return unidades, texto_norm[m.end():].strip(), inexistentes


def tirar_posto(nome_norm):
    """Nome sem a patente do início (só para comparar nomes)."""
    partes = nome_norm.replace(".", " ").split()
    while len(partes) > 1 and partes[0] in POSTOS:
        partes.pop(0)
    return " ".join(partes)


def _nome(resto):
    for seg in _RE_SEP_NOME.split(resto):
        seg = re.split(r"\d|\bCANCEL\w*", seg.strip("-–: "))[0].strip(" -–:.")
        if seg:
            return seg[:MAX_NOME]
    return ""


def interpretar_cancelamento(bruto, ano, mes_aba):
    """Uma linha bruta -> item (ver o início do módulo). Nunca levanta erro por texto estranho."""
    partes = [bruto[k] for k in ("a", "b", "c", "d", "e") if bruto[k]]
    item = {"linha": bruto["linha"], "unidades": [], "hospede": "", "entrada": None, "saida": None,
            "texto": " | ".join(partes)[:MAX_TEXTO], "ok": False, "motivo": ""}
    if contem_numero_cartao(" ".join(partes)):
        item.update(texto="", motivo=MSG_CARTAO)
        return item
    a_n, b_n = sem_acento_maiusc(bruto["a"]), sem_acento_maiusc(bruto["b"])
    unidades, resto_a, invalidas = extrair_unidades(a_n)
    if unidades and not re.search(r"[A-Z]{3}", resto_a):
        resto = b_n
    else:
        u_b, resto, inv_b = extrair_unidades(b_n)
        resto = resto.lstrip("-–: ")
        unidades, invalidas = (u_b, inv_b) if (u_b or inv_b or not invalidas) else ([], invalidas)
    item["unidades"] = unidades
    item["hospede"] = _nome(resto)
    tudo = " | ".join([resto] + [sem_acento_maiusc(bruto[k]) for k in ("c", "d", "e")])
    try:
        item["entrada"], item["saida"], _ = calcular_periodo(tudo, ano, mes_aba)
    except ErroLinha:
        pass
    if invalidas:
        item["motivo"] = "Unidade inexistente na linha (%s)" % ", ".join(invalidas)
    elif not unidades:
        item["motivo"] = "Não foi possível identificar o apartamento ou chalé"
    elif not (item["entrada"] or item["hospede"]):
        item["motivo"] = "Sem nome do hóspede nem período"
    else:
        item["ok"] = True
    return item
