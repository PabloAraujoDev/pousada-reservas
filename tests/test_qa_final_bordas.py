"""QA final: datas de borda da Governança (mesmo dia saída/entrada, 11:59:59 / 12:00 / 13:00 / 14:00, virada de dia e de mês)."""
from datetime import datetime

import pytest

from pousada.db import conectar
from tests import conftest
from tests.conftest import criar_app_teste

BASE = {"extras": "", "n": 2, "p": "pendente", "o": "", "grupo": ""}


def montar(tmp_path, agora, reservas):
    app = criar_app_teste(tmp_path, AGORA=agora)
    adm = conftest.cliente_como(app, "admin")
    for a, i, f in reservas:
        assert adm.post("/api/reservas", json=dict(BASE, a=a, nome="Hosp " + a + i, i=i, f=f)).status_code == 201
    con = conectar(app.config["CAMINHO_BANCO"])      # a migração carimba "pronto em" com a hora REAL; os testes usam relógio fixo
    con.execute("UPDATE governanca_unidade SET pronto_em='2026-01-01 00:00:00', situacao_em='2026-01-01 00:00:00'")
    con.close()
    return app, adm


def item(c, u, dia=None):
    r = c.get("/api/governanca" + ("?dia=" + dia if dia else ""))
    assert r.status_code == 200
    return next(x for x in r.get_json()["unidades"] if x["u"] == u)


@pytest.mark.parametrize("hora,situacao,atrasada", [
    ((11, 59, 59), "aguardando_saida", False), ((12, 0, 0), "suja", False), ((12, 59, 59), "suja", False),
    ((13, 0, 0), "suja", True), ((14, 0, 0), "suja", True), ((23, 59, 59), "suja", True)])
def test_troca_no_mesmo_dia_hora_a_hora(tmp_path, hora, situacao, atrasada):
    agora = datetime(2026, 10, 29, *hora)
    app, adm = montar(tmp_path, agora, [("201", "2026-10-27", "2026-10-29"), ("201", "2026-10-29", "2026-10-31")])
    x = item(adm, "201")
    assert (x["situacao"], x["atrasada"], x["troca_hoje"]) == (situacao, atrasada, True)
    assert x["saida_hoje"]["hora"] == "12:00" and x["chegada_hoje"]["hora"] == "14:00"


def test_pronta_depois_das_12_tira_o_atraso_e_o_dia_seguinte_hospedada(tmp_path):
    app, adm = montar(tmp_path, datetime(2026, 10, 29, 12, 30), [("201", "2026-10-27", "2026-10-29"), ("201", "2026-10-29", "2026-10-31")])
    v = item(adm, "201")["versao"]
    r = adm.post("/api/governanca/acao", json={"acao": "pronta", "unidades": [{"u": "201", "versao": v}], "confirmou_saida": True})
    assert r.status_code == 200
    app.config["AGORA"] = datetime(2026, 10, 29, 13, 30)
    x = item(adm, "201")
    assert x["situacao"] == "pronta" and x["atrasada"] is False
    app.config["AGORA"] = datetime(2026, 10, 30, 8, 0)             # virou o dia: hóspede novo dormiu, unidade segue hospedada (não volta a suja)
    assert item(adm, "201")["situacao"] == "hospedada"


def test_virada_de_mes_e_ano_na_consulta_de_dias(tmp_path):
    app, adm = montar(tmp_path, datetime(2026, 12, 31, 13, 0), [("202", "2026-12-29", "2027-01-02"), ("203", "2026-12-31", "2027-01-01")])
    assert item(adm, "202", "2027-01-02")["saida_hoje"]["hora"] == "12:00"
    assert item(adm, "203", "2027-01-01")["saida_hoje"] is not None
    assert adm.get("/api/governanca?dia=2027-01-07").status_code == 200
    assert adm.get("/api/governanca?dia=2027-01-08").status_code == 422
    assert adm.get("/api/governanca?dia=2026-12-30").status_code == 422
    assert adm.get("/api/governanca?dia=2027-02-29").status_code == 422


def test_dia_bissexto(tmp_path):
    app, adm = montar(tmp_path, datetime(2028, 2, 28, 9, 0), [("301", "2028-02-27", "2028-03-01")])
    assert item(adm, "301", "2028-02-29")["ocupacao"] == "hospedada"
    assert item(adm, "301", "2028-03-01")["saida_hoje"] is not None


def test_cartoes_e_governanca_concordam_sobre_quem_sai_hoje(tmp_path):
    app, adm = montar(tmp_path, datetime(2026, 10, 29, 10, 0), [("201", "2026-10-27", "2026-10-29"), ("202", "2026-10-29", "2026-10-30")])
    t = adm.get("/api/governanca").get_json()["totais"]
    lista = [r for r in adm.get("/api/reservas").get_json()]
    assert t["saida_hoje"] == sum(1 for r in lista if r["f"] == "2026-10-29")
    assert t["chegada_hoje"] == sum(1 for r in lista if r["i"] == "2026-10-29")
