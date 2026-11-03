"""Folha das camareiras: movimento dia a dia SEM valores, pagamento ou telefone."""
import re
from datetime import timedelta

from .regras import ANO_MAX, ANO_MIN, UNIDADES, data_valida

MAX_DIAS = 62
SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# Trechos de observação que nunca devem aparecer para as camareiras
_PALAVRAS_PROIBIDAS = re.compile(
    r"PAGO|PAGAR|PAGTO|PAGAMENTO|PIX|SINAL|PARCIAL|GRATUID|CORTESIA|GRATIS|VALOR|DEPOSIT|CARTAO|DINHEIRO|"
    r"BOLETO|TRANSFER|COMPROVANTE|QUITA|ACERT|NA POUSADA|DIARIA|TARIFA|DESCONTO|FATURA|NOTA FISCAL|R\$|%")


def _sem_acento(t):
    """Maiúsculo, sem acento, com letras de largura total/estilizadas normalizadas (NFKD) e sem caracteres invisíveis."""
    import unicodedata
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if unicodedata.category(c) not in ("Mn", "Cf")).upper()


# Palavras longas também são procuradas sem espaços/pontos no meio ("P A G O", "p.i.x"), que burlariam a busca simples.
_PROIBIDAS_COLADAS = re.compile(
    r"PAGO|PAGAR|PAGTO|PAGAMENTO|SINAL|PARCIAL|GRATUID|CORTESIA|VALOR|DEPOSIT|CARTAO|DINHEIRO|BOLETO|"
    r"COMPROVANTE|QUITA|DESCONTO|FATURA|TARIFA|DIARIA")
_PIX_ESPACADO = re.compile(r"P\W*I\W*X")


def _suspeito(t):
    """O trecho fala de pagamento/valor/telefone? (testa o texto normal e o texto sem separadores)"""
    t = _sem_acento(t)
    colado = re.sub(r"[\W_]+", "", t)
    return bool(len(re.sub(r"\D", "", t)) >= 8 or _PALAVRAS_PROIBIDAS.search(t)
                or _PROIBIDAS_COLADAS.search(colado) or _PIX_ESPACADO.search(t))


def observacao_segura(texto):
    """Tira de uma observação os trechos com telefone, valores em dinheiro ou pagamento.

    O texto é separado em trechos (por ' - ', ';', '|' ou quebra de linha) e cada trecho
    suspeito é descartado inteiro. É uma proteção em camadas: o que sobrar também é
    limpo de sequências longas de números.
    """
    mantidos = []
    for trecho in re.split(r"\s+-+\s+|\s*[;|\n]\s*", str(texto or "")):
        t = trecho.strip()
        if not t:
            continue
        if _suspeito(t):
            continue
        t = re.sub(r"\d[\d\s().+-]{6,}\d", "", t).strip()   # sobras de números longos
        if t:
            mantidos.append(t)
    return " - ".join(mantidos)


def _item(r, mostrar_nomes):
    """Dados de uma reserva para a camareira (sem valores, pagamento ou telefone)."""
    d = {"n": r["n"], "obs": observacao_segura(r["o"]), "grupo": r["grupo"] or ""}
    # extras de reservas manuais são itens (berço...); nas importadas são nomes de acompanhantes
    if mostrar_nomes or r["lote_id"] is None:
        d["extras"] = [x.strip() for x in str(r["extras"] or "").split("\n") if x.strip()]
    else:
        d["extras"] = []
    if mostrar_nomes:
        d["nome"] = r["nome"]
    return d


def montar_folha(con, inicio, fim, estadias=False, mostrar_nomes=False):
    """Para cada dia de [inicio, fim]: unidades com SAÍDA, ENTRADA e (opcional) ESTADIA."""
    d0, d1 = data_valida(inicio), data_valida(fim)
    if not d0 or not d1:
        return None, "Informe datas válidas"
    if not (ANO_MIN <= d0.year <= ANO_MAX and ANO_MIN <= d1.year <= ANO_MAX):
        return None, "O ano das datas deve estar entre %d e %d" % (ANO_MIN, ANO_MAX)
    if d1 < d0:
        return None, "A data final deve ser igual ou depois da inicial"
    if (d1 - d0).days + 1 > MAX_DIAS:
        return None, "Período grande demais (máximo %d dias)" % MAX_DIAS
    linhas = con.execute("SELECT a, nome, extras, n, i, f, o, grupo, lote_id FROM reservas "
                         "WHERE status = 'ativa' AND i <= ? AND f >= ?", (d1.isoformat(), d0.isoformat())).fetchall()
    ordem = {u: k for k, u in enumerate(UNIDADES)}
    dias, dia = [], d0
    while dia <= d1:
        iso = dia.isoformat()
        por_apto = {}
        for r in linhas:
            if r["f"] == iso:
                tipo = "saida"
            elif r["i"] == iso:
                tipo = "entrada"
            elif r["i"] < iso < r["f"] and estadias:
                tipo = "estadia"
            else:
                continue
            por_apto.setdefault(r["a"], {"a": r["a"], "saida": None, "entrada": None, "estadia": None})[tipo] = _item(r, mostrar_nomes)
        unidades = sorted(por_apto.values(), key=lambda u: (0 if (u["saida"] and u["entrada"]) else 1, ordem.get(u["a"], 99)))
        for u in unidades:
            u["saida_e_entrada"] = bool(u["saida"] and u["entrada"])
        dias.append({"data": iso, "semana": SEMANA[dia.weekday()], "unidades": unidades,
                     "total_saidas": sum(1 for u in unidades if u["saida"]),
                     "total_entradas": sum(1 for u in unidades if u["entrada"])})
        dia += timedelta(days=1)
    return {"inicio": d0.isoformat(), "fim": d1.isoformat(), "estadias": bool(estadias),
            "mostrar_nomes": bool(mostrar_nomes), "dias": dias}, None
