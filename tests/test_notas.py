"""Notas da reserva e do apartamento: criar, listar, corrigir, ocultar, validações, limites, versão e idempotência."""
from datetime import datetime

import pytest

from pousada.db import conectar
from tests import conftest
from tests.conftest import criar_app_teste

AGORA = datetime(2026, 10, 29, 9, 0, 0)
RES = {"a": "201", "nome": "Maria Silva", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente",
       "o": "", "grupo": ""}


def cli(app, papel, login=None):
    cache = app.__dict__.setdefault("_cl", {})
    chave = login or papel
    if chave not in cache:
        cache[chave] = conftest.cliente_como(app, papel, login)
    return cache[chave]


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def nova_reserva(app, **extra):
    r = cli(app, "admin").post("/api/reservas", json=dict(RES, **extra))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def sql(app, comando, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return con.execute(comando, args).fetchall()
    finally:
        con.close()


def anotar(c, rid, texto="Cliente chega tarde", **extra):
    return c.post("/api/reservas/%d/notas" % rid, json=dict({"texto": texto}, **extra))


def listar(c, rid, ocultas=False):
    return c.get("/api/reservas/%d/notas%s" % (rid, "?ocultas=1" if ocultas else ""))


def test_anotar_e_listar_com_autor_e_data(app):
    rid = nova_reserva(app)["id"]
    r = anotar(cli(app, "atendente", "juliano"), rid)
    assert r.status_code == 201
    n = r.get_json()
    assert n["texto"] == "Cliente chega tarde" and n["por"] == "juliano" and n["em"] == "2026-10-29 09:00:00"
    assert n["versao"] == 1 and n["modificado_por"] is None and n["pode_corrigir"] and n["pode_ocultar"]
    g = listar(cli(app, "consulta"), rid).get_json()
    assert g["total"] == 1 and g["notas"][0]["texto"] == "Cliente chega tarde" and g["pode_escrever"] is False
    assert not g["notas"][0]["pode_corrigir"]          # consulta só lê


def test_corrigir_guarda_o_texto_antigo_e_mostra_modificado_por(app):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "atendente", "juliano"), rid).get_json()["id"]
    app.config["AGORA"] = datetime(2026, 10, 29, 9, 30, 0)
    r = cli(app, "admin").post("/api/notas/%d/corrigir" % nid, json={"texto": "Chega às 22h", "versao": 1})
    assert r.status_code == 200
    n = r.get_json()
    assert n["texto"] == "Chega às 22h" and n["versao"] == 2 and n["por"] == "juliano"
    assert n["modificado_por"] == "admin" and n["modificado_em"] == "2026-10-29 09:30:00"
    assert "Cliente chega tarde" in [t[0] for t in sql(app, "SELECT texto FROM nota")]       # o anterior continua no log
    oc = listar(cli(app, "admin"), rid, ocultas=True).get_json()["notas"][0]
    assert [a["texto"] for a in oc["anteriores"]] == ["Cliente chega tarde"]
    assert "anteriores" not in listar(cli(app, "atendente"), rid, ocultas=True).get_json()["notas"][0]


def test_ocultar_some_da_lista_mas_fica_no_log(app):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "recepcao"), rid).get_json()["id"]
    r = cli(app, "recepcao").post("/api/notas/%d/ocultar" % nid, json={"motivo": "lançada sem querer", "versao": 1})
    assert r.status_code == 200
    assert listar(cli(app, "atendente"), rid).get_json()["notas"] == []
    assert listar(cli(app, "atendente"), rid).get_json()["total"] == 0
    adm = listar(cli(app, "admin"), rid, ocultas=True).get_json()["notas"][0]
    assert adm["oculta"] and adm["oculta_por"] == "recepcao" and adm["oculta_motivo"] == "lançada sem querer"
    assert sql(app, "SELECT COUNT(*) FROM nota")[0][0] == 2


def test_versao_antiga_409_e_nota_oculta_nao_muda(app):
    rid = nova_reserva(app)["id"]
    a = cli(app, "atendente")
    nid = anotar(a, rid).get_json()["id"]
    assert a.post("/api/notas/%d/corrigir" % nid, json={"texto": "Nova", "versao": 1}).status_code == 200
    assert a.post("/api/notas/%d/corrigir" % nid, json={"texto": "Outra", "versao": 1}).status_code == 409
    assert a.post("/api/notas/%d/ocultar" % nid, json={"motivo": "engano", "versao": 1}).status_code == 409
    assert a.post("/api/notas/%d/ocultar" % nid, json={"motivo": "engano", "versao": 2}).status_code == 200
    assert a.post("/api/notas/%d/ocultar" % nid, json={"motivo": "engano", "versao": 2}).status_code == 409
    assert a.post("/api/notas/%d/corrigir" % nid, json={"texto": "Tarde", "versao": 2}).status_code == 409
    assert a.post("/api/notas/%d/corrigir" % nid, json={"texto": "x"}).status_code == 400      # sem versão


@pytest.mark.parametrize("texto", ["", "   ", "x" * 301, "ab‮cd", 5, None, "Cartão 4111 1111 1111 1111"])
def test_texto_invalido_422(app, texto):
    rid = nova_reserva(app)["id"]
    r = anotar(cli(app, "atendente"), rid, texto)
    assert r.status_code == 422, r.get_data(as_text=True)
    assert "4111" not in r.get_data(as_text=True)
    assert sql(app, "SELECT COUNT(*) FROM nota")[0][0] == 0


def test_texto_300_aceito_e_xss_guardado_como_texto(app):
    rid = nova_reserva(app)["id"]
    assert anotar(cli(app, "atendente"), rid, "x" * 300).status_code == 201
    x = "<img src=x onerror=alert(1)>"
    assert anotar(cli(app, "atendente"), rid, x).status_code == 201
    assert listar(cli(app, "atendente"), rid).get_json()["notas"][1]["texto"] == x


def test_cartao_na_correcao_e_no_motivo(app):
    rid = nova_reserva(app)["id"]
    a = cli(app, "atendente")
    nid = anotar(a, rid).get_json()["id"]
    assert a.post("/api/notas/%d/corrigir" % nid, json={"texto": "4111111111111111", "versao": 1}).status_code == 422
    assert a.post("/api/notas/%d/ocultar" % nid, json={"motivo": "cartao4111111111111111", "versao": 1}).status_code == 422
    assert anotar(a, rid, "pago no cartão (final 1234)").status_code == 201


def test_mesma_chave_devolve_a_original(app):
    rid = nova_reserva(app)["id"]
    a, b = anotar(cli(app, "atendente"), rid, chave="chave-12345"), anotar(cli(app, "atendente"), rid, chave="chave-12345")
    assert (a.status_code, b.status_code) == (201, 200) and a.get_json()["id"] == b.get_json()["id"]
    assert listar(cli(app, "atendente"), rid).get_json()["total"] == 1
    assert anotar(cli(app, "atendente"), rid, chave="curta").status_code == 422


def test_limite_de_100_notas_e_corpo_nao_objeto(app):
    rid = nova_reserva(app)["id"]
    a = cli(app, "atendente")
    for k in range(100):
        assert anotar(a, rid, "nota %d" % k).status_code == 201
    assert anotar(a, rid, "101").status_code == 409
    assert a.post("/api/reservas/%d/notas" % rid, json=[1]).status_code == 400


def test_reserva_inexistente_cancelada_e_unidade_invalida(app):
    rid = nova_reserva(app)["id"]
    assert anotar(cli(app, "atendente"), 999).status_code == 404
    assert cli(app, "atendente").get("/api/unidades/999/notas").status_code == 404
    nid = anotar(cli(app, "atendente"), rid).get_json()["id"]
    assert cli(app, "admin").delete("/api/reservas/%d" % rid, json={"versao": 1, "motivo": "teste"}).status_code == 200
    assert anotar(cli(app, "atendente"), rid).status_code == 409
    assert cli(app, "atendente").post("/api/notas/%d/ocultar" % nid, json={"motivo": "abc", "versao": 1}).status_code == 409
    assert listar(cli(app, "atendente"), rid).status_code == 200       # atendente vê canceladas
    assert listar(cli(app, "recepcao"), rid).status_code == 404        # recepção não
