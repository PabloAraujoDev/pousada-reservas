"""Relatório de ocupação: cálculo (bordas), blocos de página e regras de domínio. Sem rede, banco temporário."""
from datetime import date

import pytest

from pousada import ocupacao as oc
from pousada.db import conectar
from pousada.regras import agora


def _inserir(app, a, i, f, n=2, nome="Hóspede", status="ativa", grupo=""):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status) "
                    "VALUES (?,?,'',?,?,?,'pendente','',?,?,?,1,?)", (a, nome, n, i, f, grupo, agora(), agora(), status))
    finally:
        con.close()


def _rel(app, ini, fim, nomes=True):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return oc.montar(con, date.fromisoformat(ini), date.fromisoformat(fim), nomes)
    finally:
        con.close()


def _t(rel, dia):
    return next(t for t in rel["totais"] if t["data"] == dia)


def test_periodo_de_um_dia_sem_reservas(app):
    r = _rel(app, "2026-10-10", "2026-10-10")
    assert r["dias"] == ["2026-10-10"] and len(r["unidades"]) == 25
    t = r["totais"][0]
    assert (t["ocupadas"], t["livres"], t["pct"], t["entradas"], t["saidas"], t["pessoas"]) == (0, 24, 0.0, 0, 0, 0)
    assert r["resumo"]["ocupacao_media"] == 0.0 and r["resumo"]["noites_disponiveis"] == 24


def test_um_dia_com_reserva_no_dia(app):
    _inserir(app, "201", "2026-10-10", "2026-10-12", n=3)
    r = _rel(app, "2026-10-10", "2026-10-10")
    t = r["totais"][0]
    assert (t["ocupadas"], t["livres"], t["entradas"], t["saidas"], t["pessoas"]) == (1, 23, 1, 0, 3)
    assert t["pct"] == 4.2


def test_saida_e_entrada_no_mesmo_dia_na_mesma_unidade(app):
    _inserir(app, "201", "2026-10-08", "2026-10-10", n=2, nome="Saindo")
    _inserir(app, "201", "2026-10-10", "2026-10-12", n=4, nome="Entrando")
    r = _rel(app, "2026-10-09", "2026-10-11")
    assert [(t["ocupadas"], t["entradas"], t["saidas"], t["pessoas"]) for t in r["totais"]] == [(1, 0, 0, 2), (1, 1, 1, 4), (1, 0, 0, 4)]
    assert r["resumo"]["noites_ocupadas"] == 3                  # a unidade conta uma vez por noite, nunca duas


def test_saida_no_primeiro_dia_conta_so_como_checkout(app):
    _inserir(app, "202", "2026-10-01", "2026-10-10")
    t = _rel(app, "2026-10-10", "2026-10-12")["totais"][0]
    assert (t["ocupadas"], t["saidas"], t["entradas"]) == (0, 1, 0)


def test_entrada_depois_do_periodo_nao_conta(app):
    _inserir(app, "202", "2026-10-13", "2026-10-15")
    r = _rel(app, "2026-10-10", "2026-10-12")
    assert r["resumo"]["noites_ocupadas"] == 0 and r["resumo"]["entradas"] == 0
    assert all(not u["reservas"] for u in r["unidades"])


def test_reserva_atravessando_o_periodo(app):
    _inserir(app, "301", "2026-09-01", "2026-12-01", n=5)
    r = _rel(app, "2026-10-10", "2026-10-12")
    assert [t["ocupadas"] for t in r["totais"]] == [1, 1, 1] and r["resumo"]["entradas"] == 0 and r["resumo"]["saidas"] == 0
    d = oc.dividir(r)["blocos"][0]
    c = next(u for u in d["linhas"] if u["a"] == "301")["celulas"][0]
    assert (c["col"], c["span"], c["antes"], c["depois"]) == (0, 3, True, True)


def test_virada_de_mes_e_de_ano(app):
    _inserir(app, "Chalé A", "2026-12-30", "2027-01-02", n=2)
    r = _rel(app, "2026-12-29", "2027-01-03")
    assert r["dias"][0] == "2026-12-29" and r["dias"][-1] == "2027-01-03" and len(r["dias"]) == 6
    assert [t["ocupadas"] for t in r["totais"]] == [0, 1, 1, 1, 0, 0]
    assert _t(r, "2026-12-30")["entradas"] == 1 and _t(r, "2027-01-02")["saidas"] == 1


def test_ano_bissexto_29_de_fevereiro(app):
    r = _rel(app, "2028-02-28", "2028-03-01")
    assert r["dias"] == ["2028-02-28", "2028-02-29", "2028-03-01"]


def test_unidade_interditada_fora_da_conta(app):
    r = _rel(app, "2026-10-10", "2026-10-10")
    u104 = next(u for u in r["unidades"] if u["a"] == "104")
    assert u104["interditada"] and u104["reservas"] == []
    assert r["resumo"]["reservaveis"] == 24 and _t(r, "2026-10-10")["livres"] == 24


def test_reserva_na_unidade_interditada_nao_entra_na_conta(app):
    _inserir(app, "104", "2026-10-09", "2026-10-12")          # dado legado: nunca pode inflar a ocupação
    r = _rel(app, "2026-10-10", "2026-10-10")
    assert r["totais"][0]["ocupadas"] == 0 and r["resumo"]["entradas"] == 0


def test_canceladas_excluidas(app):
    _inserir(app, "201", "2026-10-10", "2026-10-12", status="cancelada")
    r = _rel(app, "2026-10-10", "2026-10-11")
    assert r["resumo"]["noites_ocupadas"] == 0 and r["resumo"]["entradas"] == 0


def test_contagem_por_unidade_e_pico(app):
    for a in ("201", "202", "203"):
        _inserir(app, a, "2026-10-11", "2026-10-13", n=2)
    _inserir(app, "204", "2026-10-10", "2026-10-11", n=1)
    r = _rel(app, "2026-10-10", "2026-10-13")
    assert [t["ocupadas"] for t in r["totais"]] == [1, 3, 3, 0]
    s = r["resumo"]
    assert s["pico"] == {"data": "2026-10-11", "ocupadas": 3, "pct": 12.5}        # empate: o primeiro dia
    assert s["noites_ocupadas"] == 7 and s["noites_disponiveis"] == 96 and s["ocupacao_media"] == 7.3
    assert s["entradas"] == 4 and s["saidas"] == 4 and s["pessoas_noites"] == 13


def test_sem_nomes_nao_vaza_nome_nem_grupo(app):
    _inserir(app, "201", "2026-10-10", "2026-10-12", nome="Fulano Secreto", grupo="Turma Secreta")
    texto = str(oc.dividir(_rel(app, "2026-10-10", "2026-10-12", nomes=False)))
    assert "Fulano" not in texto and "Secreta" not in texto
    assert "Fulano Secreto" in str(oc.dividir(_rel(app, "2026-10-10", "2026-10-12", nomes=True)))


def test_blocos_por_orientacao_e_recorte(app):
    _inserir(app, "201", "2026-10-12", "2026-10-30")
    r = _rel(app, "2026-10-10", "2026-11-08")                    # 30 dias
    paisagem, retrato = oc.dividir(r, "paisagem"), oc.dividir(r, "retrato")
    assert [len(b["dias"]) for b in paisagem["blocos"]] == [14, 14, 2]
    assert [len(b["dias"]) for b in retrato["blocos"]] == [7, 7, 7, 7, 2]
    c = [next(u for u in b["linhas"] if u["a"] == "201")["celulas"] for b in paisagem["blocos"]]
    assert [(x[0]["col"], x[0]["span"], x[0]["antes"], x[0]["depois"]) for x in c[:2]] == [(2, 12, False, True), (0, 6, True, False)]
    assert c[2] == []
    assert all(len(b["totais"]) == len(b["dias"]) for b in paisagem["blocos"])


def test_sobreposicao_antiga_nao_quebra_a_grade(app):
    _inserir(app, "201", "2026-10-10", "2026-10-14")
    _inserir(app, "201", "2026-10-12", "2026-10-16")             # conflito antigo (importação): a segunda não é desenhada
    d = oc.dividir(_rel(app, "2026-10-10", "2026-10-16"))["blocos"][0]
    cel = next(u for u in d["linhas"] if u["a"] == "201")["celulas"]
    assert len(cel) == 1 and cel[0]["col"] == 0
    assert _t(_rel(app, "2026-10-10", "2026-10-16"), "2026-10-13")["ocupadas"] == 1


@pytest.mark.parametrize("ini,fim,ok", [
    ("2026-10-01", "2026-10-01", True), ("2026-10-01", "2026-12-31", True),      # 92 dias
    ("2026-10-01", "2027-01-01", False),                                          # 93 dias
    ("2026-10-02", "2026-10-01", False), ("2026-02-30", "2026-03-01", False), ("2026-10-1", "2026-10-02", False),
    ("", "", False), ("2019-12-31", "2020-01-02", False), ("2100-12-31", "2101-01-01", False),
    ("２０２６-10-01", "2026-10-02", False), ("2026-10-01\n", "2026-10-02", False)])
def test_validar_periodo(ini, fim, ok):
    d0, d1, erro = oc.validar_periodo(ini, fim)
    assert (erro is None) == ok
    assert (d0 is not None) == ok
