"""Relatório de ocupação de um período: grade unidade x dia, totais por dia e resumo.

Regras (as mesmas do mapa): reserva = unidade + [entrada, saída). A coluna de um dia representa a NOITE desse dia:
ocupada se entrada <= dia < saída. Saída e entrada no mesmo dia na mesma unidade é permitido (não conta dupla).
Contagem por UNIDADE (não por reserva); a unidade interditada (regras.OCUPADAS) fica fora da conta (24 reserváveis).
Reservas canceladas não entram. Nunca há valor de diária aqui.
"""
from datetime import timedelta

from .regras import ANO_MAX, ANO_MIN, OCUPADAS, UNIDADES, data_valida

MAX_DIAS = 92
RESERVAVEIS = [u for u in UNIDADES if u not in OCUPADAS]


def validar_periodo(inicio, fim):
    """Devolve (date_inicio, date_fim, None) ou (None, None, mensagem). Aceita só AAAA-MM-DD reais."""
    d0, d1 = data_valida(inicio), data_valida(fim)
    if not d0 or not d1:
        return None, None, "Informe datas válidas (AAAA-MM-DD)"
    if not (ANO_MIN <= d0.year <= ANO_MAX and ANO_MIN <= d1.year <= ANO_MAX):
        return None, None, "O ano das datas deve estar entre %d e %d" % (ANO_MIN, ANO_MAX)
    if d1 < d0:
        return None, None, "A data final deve ser igual ou depois da inicial"
    if (d1 - d0).days + 1 > MAX_DIAS:
        return None, None, "Período grande demais (máximo %d dias)" % MAX_DIAS
    return d0, d1, None


def _pct(ocupadas):
    return round(100.0 * ocupadas / len(RESERVAVEIS), 1)


def montar(con, d0, d1, com_nomes=False):
    """Dados do relatório de d0 a d1 (inclusive). com_nomes=False omite nome e grupo (camareira)."""
    dias = [(d0 + timedelta(days=k)).isoformat() for k in range((d1 - d0).days + 1)]
    iso0, iso1 = dias[0], dias[-1]
    fim_excl = (d1 + timedelta(days=1)).isoformat()
    # noites do período: i <= d1 e f > d0; saídas no próprio primeiro dia (f = d0) contam só como check-out
    linhas = con.execute("SELECT a, nome, grupo, n, i, f FROM reservas WHERE status = 'ativa' AND i < ? AND f >= ? "
                         "ORDER BY i, a", (fim_excl, iso0)).fetchall()
    por_unidade = {u: [] for u in UNIDADES}
    noite = {d: {} for d in dias}                  # dia -> {unidade: pessoas}: a unidade conta uma vez só
    entradas, saidas = dict.fromkeys(dias, 0), dict.fromkeys(dias, 0)
    for r in linhas:
        if r["a"] not in por_unidade:
            continue
        if r["f"] > iso0 and r["i"] <= iso1:
            item = {"i": r["i"], "f": r["f"], "n": r["n"]}
            if com_nomes:
                item["nome"], item["grupo"] = r["nome"], r["grupo"] or ""
            por_unidade[r["a"]].append(item)
        if r["a"] in OCUPADAS:
            continue
        if r["i"] in entradas:
            entradas[r["i"]] += 1
        if r["f"] in saidas:
            saidas[r["f"]] += 1
        k = max(r["i"], iso0)
        while k < r["f"] and k <= iso1:             # no máximo 92 passos por reserva
            noite[k][r["a"]] = noite[k].get(r["a"], 0) + r["n"]
            k = (data_valida(k) + timedelta(days=1)).isoformat()
    totais = []
    for d in dias:
        oc = len(noite[d])
        totais.append({"data": d, "ocupadas": oc, "livres": len(RESERVAVEIS) - oc, "pct": _pct(oc),
                       "entradas": entradas[d], "saidas": saidas[d], "pessoas": sum(noite[d].values())})
    soma = sum(t["ocupadas"] for t in totais)
    pico = max(totais, key=lambda t: (t["ocupadas"], -dias.index(t["data"])))     # empate: o primeiro dia
    resumo = {"dias": len(dias), "reservaveis": len(RESERVAVEIS), "noites_ocupadas": soma,
              "noites_disponiveis": len(RESERVAVEIS) * len(dias),
              "ocupacao_media": round(100.0 * soma / (len(RESERVAVEIS) * len(dias)), 1),
              "pico": {"data": pico["data"], "ocupadas": pico["ocupadas"], "pct": pico["pct"]},
              "entradas": sum(entradas.values()), "saidas": sum(saidas.values()),
              "pessoas_noites": sum(t["pessoas"] for t in totais)}
    unidades = [{"a": u, "interditada": u in OCUPADAS, "reservas": [] if u in OCUPADAS else por_unidade[u]}
                for u in UNIDADES]
    return {"inicio": iso0, "fim": iso1, "dias": dias, "com_nomes": bool(com_nomes), "unidades": unidades,
            "totais": totais, "resumo": resumo}


DIAS_POR_BLOCO = {"paisagem": 14, "retrato": 7}        # colunas legíveis por página
ORIENTACOES = tuple(DIAS_POR_BLOCO)


def _celulas(reservas, dias):
    """Reservas da unidade recortadas às colunas (dias) de um bloco: [{col, span, antes, depois, n, nome?, grupo?}]."""
    primeiro, ultimo = dias[0], dias[-1]
    celulas, proxima = [], 0
    for r in sorted(reservas, key=lambda x: x["i"]):
        a = max(r["i"], primeiro)
        z = min(r["f"], (data_valida(ultimo) + timedelta(days=1)).isoformat())     # exclusivo
        if z <= a:
            continue
        col = (data_valida(a) - data_valida(primeiro)).days
        span = (data_valida(z) - data_valida(a)).days
        if col < proxima:                                # sobreposição (conflito antigo): a segunda não é desenhada
            continue
        proxima = col + span
        c = {"col": col, "span": span, "n": r["n"], "antes": r["i"] < primeiro, "depois": r["f"] > ultimo}
        if "nome" in r:
            c["nome"], c["grupo"] = r["nome"], r["grupo"]
        celulas.append(c)
    return celulas


def dividir(dados, orientacao="paisagem"):
    """Quebra a grade em blocos de colunas (um por página), com o recorte das reservas e os totais de cada bloco."""
    passo = DIAS_POR_BLOCO[orientacao]
    blocos = []
    for k in range(0, len(dados["dias"]), passo):
        dias = dados["dias"][k:k + passo]
        blocos.append({"dias": dias, "totais": dados["totais"][k:k + passo],
                       "linhas": [{"a": u["a"], "interditada": u["interditada"], "celulas": _celulas(u["reservas"], dias)}
                                  for u in dados["unidades"]]})
    return {"inicio": dados["inicio"], "fim": dados["fim"], "com_nomes": dados["com_nomes"], "orientacao": orientacao,
            "blocos": blocos, "resumo": dados["resumo"]}
