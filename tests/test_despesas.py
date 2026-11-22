"""Despesas: lançar, listar, estornar, validações, totais, cancelar/excluir com saldo, atomicidade e cartão."""
import sqlite3
from datetime import datetime

import pytest

from pousada.db import conectar
from tests import conftest
from tests.conftest import criar_app_teste

AGORA = datetime(2026, 10, 29, 9, 0, 0)
RES = {"a": "201", "nome": "Maria Silva", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente",
       "o": "", "grupo": "", "diaria_centavos": 35000}
LANC = {"categoria": "bar", "descricao": "Água 500ml", "quantidade": 2, "valor_unit_centavos": 800, "chave": "k1abcdef"}


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


def lancar(c, rid, **extra):
    return c.post("/api/reservas/%d/despesas" % rid, json=dict(LANC, **extra))


def test_lancar_e_listar_soma(app):
    rid = nova_reserva(app)["id"]
    r = lancar(cli(app, "admin"), rid)
    assert r.status_code == 201
    it = r.get_json()
    assert it["total_centavos"] == 1600 and it["por"] == "admin" and it["em"] == "2026-10-29 09:00:00"
    g = cli(app, "admin").get("/api/reservas/%d/despesas" % rid).get_json()
    assert g["totais"]["despesas_centavos"] == 1600 and len(g["itens"]) == 1
    assert g["conta"] == {"situacao": "aberta", "quitacao": "pendente", "versao": 2, "fechada_em": None, "quitada_em": None}


def test_mesma_chave_devolve_o_original(app):
    rid = nova_reserva(app)["id"]
    c = cli(app, "admin")
    a, b = lancar(c, rid), lancar(c, rid)
    assert (a.status_code, b.status_code) == (201, 200) and a.get_json()["id"] == b.get_json()["id"]
    assert len(c.get("/api/reservas/%d/despesas" % rid).get_json()["itens"]) == 1


@pytest.mark.parametrize("campo,valor", [
    ("valor_unit_centavos", 12.5), ("valor_unit_centavos", "1250"), ("valor_unit_centavos", True),
    ("valor_unit_centavos", 1000001), ("valor_unit_centavos", 0), ("quantidade", 0), ("quantidade", 100),
    ("quantidade", 1.5), ("quantidade", False), ("descricao", "a"), ("descricao", "x" * 81), ("descricao", "ab‮cd"),
    ("descricao", "   "), ("descricao", 5), ("categoria", "pizza"), ("categoria", None), ("chave", "curta"),
    ("descricao", "Cartão 4111 1111 1111 1111"),
])
def test_validacoes_422(app, campo, valor):
    rid = nova_reserva(app)["id"]
    r = lancar(cli(app, "admin"), rid, **{campo: valor})
    assert r.status_code == 422, r.get_data(as_text=True)
    assert "4111" not in r.get_data(as_text=True)


def test_limite_de_valor_tem_mensagem_em_reais(app):
    rid = nova_reserva(app)["id"]
    r = lancar(cli(app, "admin"), rid, valor_unit_centavos=1000001)
    assert "R$ 10.000,00" in r.get_json()["erro"]
    assert lancar(cli(app, "admin"), rid, valor_unit_centavos=1000000, quantidade=99, chave=None).status_code == 201


def test_corpo_que_nao_e_objeto_400(app):
    rid = nova_reserva(app)["id"]
    assert cli(app, "admin").post("/api/reservas/%d/despesas" % rid, json=[1]).status_code == 400


def test_xss_na_descricao_e_guardado_como_texto(app):
    rid = nova_reserva(app)["id"]
    d = "<img src=x onerror=alert(1)>"
    assert lancar(cli(app, "admin"), rid, descricao=d).status_code == 201
    assert cli(app, "admin").get("/api/reservas/%d/despesas" % rid).get_json()["itens"][0]["descricao"] == d


def test_estorno_fluxo(app):
    rid = nova_reserva(app)["id"]
    adm = cli(app, "admin")
    lid = lancar(adm, rid).get_json()["id"]
    assert adm.post("/api/despesas/%d/estorno" % lid, json={"motivo": "erro"}).status_code == 422
    r = adm.post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"})
    assert r.status_code == 201 and r.get_json()["total_centavos"] == -1600 and r.get_json()["estorno_de"] == lid
    g = adm.get("/api/reservas/%d/despesas" % rid).get_json()
    assert g["totais"]["despesas_centavos"] == 0 and len(g["itens"]) == 2
    orig = next(i for i in g["itens"] if i["id"] == lid)
    assert orig["estornado"] and orig["estorno_id"] == r.get_json()["id"]      # segue visível, marcado
    assert adm.post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"}).status_code == 409
    assert adm.post("/api/despesas/%d/estorno" % r.get_json()["id"], json={"motivo": "digitado errado"}).status_code == 409
    assert adm.post("/api/despesas/99999/estorno", json={"motivo": "digitado errado"}).status_code == 404


def test_motivo_do_estorno_recusa_cartao_sem_repetir(app):
    rid = nova_reserva(app)["id"]
    adm = cli(app, "admin")
    lid = lancar(adm, rid).get_json()["id"]
    r = adm.post("/api/despesas/%d/estorno" % lid, json={"motivo": "pagou 4111-1111-1111-1111"})
    assert r.status_code == 422 and "4111" not in r.get_data(as_text=True)


def test_totais_da_estadia(app):
    rid = nova_reserva(app, i="2026-10-26", f="2026-10-29")["id"]          # 3 noites, diária 350,00
    lancar(cli(app, "admin"), rid, quantidade=1, valor_unit_centavos=8750)
    t = cli(app, "admin").get("/api/reservas/%d/despesas" % rid).get_json()["totais"]
    assert t == {"despesas_centavos": 8750, "noites": 3, "diaria_centavos": 35000, "diarias_centavos": 105000,
                 "estadia_centavos": 113750, "conta_centavos": 113750, "pagamentos_centavos": 0, "saldo_centavos": 113750}


def test_sem_diaria_nao_ha_total_da_estadia(app):
    rid = nova_reserva(app, diaria_centavos=None)["id"]
    lancar(cli(app, "admin"), rid)
    t = cli(app, "admin").get("/api/reservas/%d/despesas" % rid).get_json()["totais"]
    assert t["diaria_centavos"] is None and "estadia_centavos" not in t and "diarias_centavos" not in t


def test_diretoria_ve_despesas_e_diaria_consulta_nada(app):
    rid = nova_reserva(app)["id"]
    lancar(cli(app, "admin"), rid)
    assert cli(app, "diretoria").get("/api/reservas/%d/despesas" % rid).status_code == 200
    assert cli(app, "consulta").get("/api/reservas/%d/despesas" % rid).status_code == 403


def test_reserva_futura_e_inexistente(app):
    futura = nova_reserva(app, a="202", i="2026-11-05", f="2026-11-07")["id"]
    r = lancar(cli(app, "admin"), futura)
    assert r.status_code == 422 and "ainda não começou" in r.get_json()["erro"]
    assert lancar(cli(app, "admin"), 9999).status_code == 404
    assert cli(app, "admin").get("/api/reservas/9999/despesas").status_code == 404


def test_cancelar_com_saldo_409_e_depois_do_estorno_200(app):
    r0 = nova_reserva(app)
    rid = r0["id"]
    adm = cli(app, "admin")
    lid = lancar(adm, rid).get_json()["id"]
    cancela = lambda: adm.delete("/api/reservas/%d" % rid, json={"versao": r0["versao"], "motivo": "desistiu"})
    assert cancela().status_code == 409
    adm.post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"})
    assert cancela().status_code == 200
    # cancelada: não lança mais; atendente ainda lê; recepção/consulta recebem 404
    assert lancar(adm, rid, chave="outrachave1").status_code == 409
    assert cli(app, "diretoria").get("/api/reservas/%d/despesas" % rid).status_code == 404


def test_cancelar_sem_despesas_segue_normal(app):
    r0 = nova_reserva(app)
    assert cli(app, "admin").delete("/api/reservas/%d" % r0["id"], json={"versao": 1, "motivo": "teste"}).status_code == 200


def test_excluir_definitivo_com_lancamento_409(app):
    r0 = nova_reserva(app)
    lid = lancar(cli(app, "admin"), r0["id"]).get_json()["id"]
    cli(app, "admin").post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"})    # mesmo estornado, fica
    r = cli(app, "admin").post("/api/reservas/%d/excluir-definitivo" % r0["id"], json={"versao": 1})
    assert r.status_code == 409


def test_reserva_movida_mantem_as_despesas(app):
    r0 = nova_reserva(app)
    lancar(cli(app, "admin"), r0["id"])
    assert cli(app, "admin").post("/api/reservas/%d/mover" % r0["id"], json={"versao": 1, "a": "202"}).status_code == 200
    g = cli(app, "admin").get("/api/reservas/%d/despesas" % r0["id"]).get_json()
    assert g["totais"]["despesas_centavos"] == 1600 and g["reserva"]["a"] == "202"


def test_resumo_de_contas_abertas_sem_valores(app):
    a, b = nova_reserva(app), nova_reserva(app, a="202")
    lancar(cli(app, "admin"), a["id"])
    lancar(cli(app, "admin"), b["id"], chave="chave-b-0001")
    lid = lancar(cli(app, "admin"), b["id"], chave="chave-b-0002").get_json()["id"]
    cli(app, "admin").post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"})
    r = cli(app, "diretoria").get("/api/despesas/resumo").get_json()
    assert r["contas_abertas"] == 2 and sorted(r["ids"]) == sorted([a["id"], b["id"]])
    assert cli(app, "consulta").get("/api/despesas/resumo").status_code == 403
