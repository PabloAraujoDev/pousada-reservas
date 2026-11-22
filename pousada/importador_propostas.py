"""Propostas de cancelamento da prévia: seção CANCELAMENTOS casada com o sistema + "sumiu da planilha". Não grava nada."""
from .importador_casar import _dados_prop, casar_cancelamento, motivo_bloqueio, nomes_parecidos, sobrepoe

LIMITE_ITENS = 500           # itens de cancelamento lidos por planilha (o resto é descartado, com aviso)
ORDEM = {"alta": 0, "sumiu": 1, "media": 2}
MASSA_MINIMO = 5             # "sumiu" em massa: pelo menos tantas reservas num mês...
MASSA_PERCENTUAL = 30        # ...e mais que isto por cento das reservas de importação daquele mês


def _na_grade(r, grade, so_nome_parecido):
    """A reserva do sistema aparece na grade da planilha? (conservador: sem data legível, vale o nome parecido)"""
    for g in grade:
        if g["apto"] != r["a"]:
            continue
        if g["entrada"]:
            if sobrepoe(g["entrada"], g["saida"], r["i"], r["f"]) and (not so_nome_parecido or nomes_parecidos(g["hospede"], r["nome"])):
                return True
        elif nomes_parecidos(g["hospede"], r["nome"]):
            return True
    return False


def montar_cancelamentos(con, por_apto, itens, grade, meses, hoje_iso, incluir_passadas, truncado=False):
    """itens: [(aba, item_interpretado)]; grade: reservas lidas da planilha; meses: {(ano, mes)} das abas COM reservas lidas."""
    props, nao_enc, nao_ident = {}, [], []
    truncado = truncado or len(itens) > LIMITE_ITENS
    for aba, it in itens[:LIMITE_ITENS]:
        base = {"aba": aba, "linha": it["linha"], "texto": it["texto"]}
        if not it["ok"]:
            nao_ident.append(dict(base, motivo=it["motivo"]))
            continue
        achadas, faltam = casar_cancelamento(it, aba, por_apto, hoje_iso, incluir_passadas)
        for u in faltam:
            nao_enc.append(dict(base, unidade=u, hospede=it["hospede"], entrada=it["entrada"], saida=it["saida"]))
        for u, r, conf, porque in achadas:
            if _na_grade(r, grade, True):
                conf, porque = "media", "a reserva também aparece na grade da planilha (conferir)"
            p = _dados_prop(r, origem="planilha", confianca=conf, motivo=porque, aba=aba, linha=it["linha"], texto=it["texto"])
            if r["id"] not in props or ORDEM[conf] < ORDEM[props[r["id"]]["confianca"]]:
                props[r["id"]] = p
    for lista in por_apto.values():
        for r in lista:
            if (r["status"] == "ativa" and r["lote_id"] is not None and r["i"] >= hoje_iso and r["id"] not in props
                    and (int(r["i"][:4]), int(r["i"][5:7])) in meses and not _na_grade(r, grade, False)):
                props[r["id"]] = _dados_prop(r, origem="sumiu", confianca="sumiu", aba="", linha=None, texto="",
                                             motivo="veio de importação anterior e não consta mais na planilha")
    por_id = {r["id"]: r for lista in por_apto.values() for r in lista}
    for p in props.values():
        p["bloqueio"] = motivo_bloqueio(con, por_id[p["id"]])
        p["marcada"] = p["confianca"] in ("alta", "sumiu") and not p["bloqueio"]
    massa = _sumiu_em_massa(por_apto, props, meses, hoje_iso)
    ordem = sorted(props.values(), key=lambda p: (p["entrada"], p["apto"], p["id"]))
    return {"propostas": ordem, "nao_encontradas": nao_enc, "nao_identificadas": nao_ident, "truncado": truncado,
            "aviso_massa": massa}


def _sumiu_em_massa(por_apto, props, meses, hoje_iso):
    """Planilha cortada ou errada faria "sumir" quase um mês inteiro: nesse caso as caixas NÃO vêm marcadas e a tela avisa.

    Devolve [{"mes": "AAAA-MM", "sumiram": n, "total": n}] dos meses em que isso aconteceu.
    """
    total, sumiram = {}, {}
    for lista in por_apto.values():
        for r in lista:
            mes = (int(r["i"][:4]), int(r["i"][5:7]))
            if r["status"] == "ativa" and r["lote_id"] is not None and r["i"] >= hoje_iso and mes in meses:
                total[mes] = total.get(mes, 0) + 1
                if r["id"] in props and props[r["id"]]["confianca"] == "sumiu":
                    sumiram[mes] = sumiram.get(mes, 0) + 1
    avisos = []
    for mes, n in sorted(sumiram.items()):
        if n < MASSA_MINIMO or n * 100 <= MASSA_PERCENTUAL * total[mes]:
            continue
        avisos.append({"mes": "%04d-%02d" % mes, "sumiram": n, "total": total[mes]})
        for p in props.values():
            if p["confianca"] == "sumiu" and (int(p["entrada"][:4]), int(p["entrada"][5:7])) == mes:
                p["marcada"] = False
                p["motivo"] += " (muitas reservas deste mês sumiram: confira a planilha antes de marcar)"
    return avisos
