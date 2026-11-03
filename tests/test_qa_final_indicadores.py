"""QA final: o ponto "há observações" das listas considera também as NOTAS novas (reserva e apartamento), sem vazar texto."""
from datetime import datetime

import pytest

from tests import conftest
from tests.conftest import criar_app_teste

RES = {"a": "201", "nome": "Maria", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente", "o": "", "grupo": ""}


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=datetime(2026, 10, 29, 9, 0))


def cl(app, papel):
    cache = app.__dict__.setdefault("_cl", {})
    if papel not in cache:
        cache[papel] = conftest.cliente_como(app, papel)
    return cache[papel]


def da_lista(c, rid):
    return next(r for r in c.get("/api/reservas").get_json() if r["id"] == rid)


def da_gov(c, u):
    return next(x for x in c.get("/api/governanca").get_json()["unidades"] if x["u"] == u)


def test_tem_nota_da_reserva_liga_e_desliga_ao_ocultar(app):
    adm = cl(app, "admin")
    rid = adm.post("/api/reservas", json=RES).get_json()["id"]
    assert da_lista(adm, rid)["tem_nota"] is False
    n = adm.post("/api/reservas/%d/notas" % rid, json={"texto": "segredo da nota"}).get_json()
    for papel in ("admin", "atendente", "recepcao", "diretoria", "consulta"):
        item = da_lista(cl(app, papel), rid)
        assert item["tem_nota"] is True and "segredo" not in str(item)
    assert adm.post("/api/notas/%d/ocultar" % n["id"], json={"motivo": "engano", "versao": 1}).status_code == 200
    assert da_lista(adm, rid)["tem_nota"] is False


def test_camareira_nao_recebe_indicador_de_nota(app):
    adm = cl(app, "admin")
    rid = adm.post("/api/reservas", json=RES).get_json()["id"]
    adm.post("/api/reservas/%d/notas" % rid, json={"texto": "nota"})
    adm.post("/api/unidades/201/notas", json={"texto": "nota do apto"})
    lista = cl(app, "camareira").get("/api/reservas").get_json()
    assert all("tem_nota" not in r for r in lista)
    assert "tem_nota_unidade" not in da_gov(cl(app, "camareira"), "201")


def test_tem_nota_unidade_na_governanca(app):
    adm = cl(app, "admin")
    assert da_gov(adm, "202")["tem_nota_unidade"] is False
    n = adm.post("/api/unidades/202/notas", json={"texto": "chuveiro fraco"}).get_json()
    assert da_gov(cl(app, "recepcao"), "202")["tem_nota_unidade"] is True
    assert da_gov(adm, "203")["tem_nota_unidade"] is False                # outra unidade não acende
    adm.post("/api/notas/%d/ocultar" % n["id"], json={"motivo": "resolvido", "versao": 1})
    assert da_gov(adm, "202")["tem_nota_unidade"] is False
