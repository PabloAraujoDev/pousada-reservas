"""Detector de número de cartão de pagamento em textos livres (nome, grupo, extras, observações, motivos).

O sistema não é ambiente certificado (PCI DSS): número de cartão nunca deve ser gravado. A função só diz
SIM ou NÃO; a mensagem de recusa NUNCA repete o texto recebido.
"""
import re
import unicodedata

MSG_CARTAO = ("Isto parece um número de cartão. Por segurança o sistema não guarda números de cartão. "
              "Apague os números e escreva apenas, por exemplo, 'pago no cartão (final 1234)'.")

# Invisíveis que alguém poderia usar para "quebrar" o número e escapar da conferência
_RE_INVISIVEIS = re.compile("[­​-‍⁠﻿]")
# Número corrido de 13 a 19 dígitos (letras coladas antes/depois não atrapalham)
_RE_CORRIDO = re.compile(r"(?<!\d)\d{13,19}(?!\d)", re.ASCII)
# Cadeia de grupos de 4+ dígitos separados por UM espaço, hífen ou ponto (ex.: 4111 1111 1111 1111)
_RE_CADEIA = re.compile(r"(?<!\d)\d{4,}(?:[ \-.]\d{4,})+(?!\d)", re.ASCII)
# Padrão visual 4-4-4-x: recusado mesmo que falhe no Luhn (provável erro de digitação de um cartão)
_RE_VISUAL = re.compile(r"(?<!\d)\d{4}([ \-.])\d{4}\1\d{4}\1\d{1,7}(?!\d)", re.ASCII)


def _nao_ascii(trecho):
    """Só os caracteres fora do ASCII passam por aqui (texto em português quase não tem): sem formatação/marcas, NFKC, dígitos em ASCII."""
    t = "".join(c for c in trecho if unicodedata.category(c) not in ("Cf", "Mn", "Me") and c not in "ᅟᅠㅤﾠ")
    t = unicodedata.normalize("NFKC", t)
    return "".join(str(unicodedata.decimal(c)) if c.isdigit() and unicodedata.decimal(c, None) is not None else c for c in t)


def _normalizar(texto):
    """Texto sem invisíveis/marcas de formatação (LRM, CGJ...), com dígitos de qualquer alfabeto em ASCII e
    separadores "arrumados": quebra de linha, tab e espaços repetidos viram um espaço; " - " vira "-"."""
    t = _RE_INVISIVEIS.sub("", texto)
    if not t.isascii():
        t = re.sub(r"[^\x00-\x7f]+", lambda m: _nao_ascii(m.group()), t)
    return re.sub(r"\s+", " ", re.sub(r"\s*([-.])\s*", r"\1", t))


def _luhn(digitos):
    """Soma de verificação dos cartões (mod 10)."""
    soma = 0
    for k, c in enumerate(reversed(digitos)):
        d = int(c)
        if k % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        soma += d
    return soma % 10 == 0


def _cadeia_suspeita(cadeia):
    """Grupos com o MESMO separador, total de 13 a 19 dígitos e Luhn válido (telefones juntos têm separadores mistos)."""
    separadores = set(re.findall(r"[ \-.]", cadeia))
    digitos = re.sub(r"\D", "", cadeia)
    return len(separadores) == 1 and 13 <= len(digitos) <= 19 and _luhn(digitos)


def contem_numero_cartao(texto):
    """True se o texto parece conter um número de cartão (13 a 19 dígitos com Luhn, ou o desenho 4-4-4-x).

    Não recusa: números mascarados ("**** 1234", "5550 ...."), "final 1234", CPF (11 dígitos), telefones,
    datas e protocolos corridos que não passam no Luhn.
    """
    if not isinstance(texto, str):
        return False
    t = _normalizar(texto)
    if _RE_VISUAL.search(t):
        return True
    if any(_luhn(m) for m in _RE_CORRIDO.findall(t)):
        return True
    return any(_cadeia_suspeita(m) for m in _RE_CADEIA.findall(t))
