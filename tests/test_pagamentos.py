"""Pagamentos (etapa 3B): recebimento em dinheiro, Pix e cartão, parcial, saldo, estorno, log imutável e idempotência."""
import sqlite3

import pytest

from pousada.db import conectar
from tests.apoio_pagamentos import app, cli, corpo_pag, lancar, nova, receber, sql, totais  # noqa: F401


def test_total_credito_e_saldo_comecam_zerados(app):
    rid = nova(app)
    lancar(app, rid, 800, 2)
    t = totais(app, rid)
    assert (t["conta_centavos"], t["pagamentos_centavos"], t["saldo_centavos"]) == (91600, 0, 91600)


def test_dinheiro_parcial_com_troco_informativo(app):
    rid = nova(app)
    r = receber(app, rid, 50000, recebido_centavos=60000)
    assert r.status_code == 201
    j = r.get_json()
    assert j["valor_centavos"] == 50000 and j["troco_centavos"] == 10000 and j["por"] == "admin"
    assert totais(app, rid)["saldo_centavos"] == 40000


def test_dinheiro_recebido_menor_que_valor_recusado(app):
    rid = nova(app)
    assert receber(app, rid, 50000, recebido_centavos=49999).status_code == 422


def test_pix_com_referencia_e_cartao_credito_parcelado(app):
    rid = nova(app)
    assert receber(app, rid, 10000, "pix", referencia="E123abc").status_code == 201
    r = receber(app, rid, 10001, "cartao", bandeira="Visa", modalidade="credito", parcelas=3, autorizacao="A1B2C3")
    assert r.status_code == 201
    j = r.get_json()
    assert j["parcelas"] == 3 and j["parcelas_valores"] == [3334, 3334, 3333] and sum(j["parcelas_valores"]) == 10001


def test_cartao_regras_de_modalidade_e_parcelas(app):
    rid = nova(app)
    base = dict(bandeira="Elo", modalidade="credito")
    assert receber(app, rid, 20000, "cartao", **base).get_json()["parcelas"] == 1                 # à vista
    assert receber(app, rid, 20000, "cartao", bandeira="Elo", modalidade="debito", parcelas=2).status_code == 422
    assert receber(app, rid, 20000, "cartao", parcelas=13, **base).status_code == 422             # acima do limite
    assert receber(app, rid, 20000, "cartao", parcelas=0, **base).status_code == 422
    assert receber(app, rid, 20000, "cartao", bandeira="Xpto", modalidade="credito").status_code == 422
    assert receber(app, rid, 20000, "cartao", parcelas=12, **base).status_code == 201


def test_limite_de_parcelas_vem_da_configuracao(app):
    rid = nova(app)
    app.config["PAG_MAX_PARCELAS"] = 3
    assert receber(app, rid, 20000, "cartao", bandeira="Elo", modalidade="credito", parcelas=4).status_code == 422
    assert receber(app, rid, 20000, "cartao", bandeira="Elo", modalidade="credito", parcelas=3).status_code == 201


def test_parcela_minima(app):
    rid = nova(app)
    assert receber(app, rid, 1999, "cartao", bandeira="Elo", modalidade="credito", parcelas=4).status_code == 422   # 499 < R$ 5,00
    assert receber(app, rid, 2000, "cartao", bandeira="Elo", modalidade="credito", parcelas=4).status_code == 201


def test_nao_recebe_acima_do_saldo_nem_zero_nem_negativo(app):
    rid = nova(app)
    assert receber(app, rid, 90001).status_code == 422
    assert receber(app, rid, 0).status_code == 422 and receber(app, rid, -5).status_code == 422
    assert receber(app, rid, 90000).status_code == 201
    assert receber(app, rid, 1).status_code == 422 and totais(app, rid)["saldo_centavos"] == 0


def test_campo_de_outra_forma_e_recusado(app):
    rid = nova(app)
    assert receber(app, rid, 1000, "pix", bandeira="Visa").status_code == 422
    assert receber(app, rid, 1000, "dinheiro", referencia="abc").status_code == 422
    assert receber(app, rid, 1000, "cartao", bandeira="Visa", modalidade="credito", recebido_centavos=1000).status_code == 422


def test_duplo_clique_mesma_chave_devolve_o_mesmo_pagamento(app):
    rid = nova(app)
    c = corpo_pag(app, rid, 10000)
    a = cli(app, "admin").post("/api/reservas/%d/pagamentos" % rid, json=c)
    b = cli(app, "admin").post("/api/reservas/%d/pagamentos" % rid, json=c)
    assert (a.status_code, b.status_code) == (201, 200) and a.get_json()["id"] == b.get_json()["id"]
    assert sql(app, "SELECT COUNT(*) FROM pagamento") == [(1,)]


def test_conta_versao_velha_da_409(app):
    rid = nova(app)
    c = corpo_pag(app, rid, 10000)
    lancar(app, rid)                          # a conta mudou
    assert cli(app, "admin").post("/api/reservas/%d/pagamentos" % rid, json=c).status_code == 409


def test_estorno_de_pagamento_linha_negativa_com_motivo(app):
    rid = nova(app)
    pid = receber(app, rid, 40000).get_json()["id"]
    url = "/api/pagamentos/%d/estorno" % pid
    assert cli(app, "admin").post(url, json={"motivo": "ab"}).status_code == 422
    r = cli(app, "admin").post(url, json={"motivo": "Valor digitado errado"})
    assert r.status_code == 201 and r.get_json()["valor_centavos"] == -40000
    assert cli(app, "admin").post(url, json={"motivo": "Outra vez de novo"}).status_code == 409
    assert totais(app, rid)["saldo_centavos"] == 90000 and totais(app, rid)["pagamentos_centavos"] == 0
    itens = cli(app, "admin").get("/api/reservas/%d/pagamentos" % rid).get_json()["itens"]
    assert [i["estornado"] for i in itens] == [False, True] and itens[0]["tipo"] == "estorno"


def test_nao_estorna_estorno_nem_inexistente(app):
    rid = nova(app)
    pid = receber(app, rid, 1000).get_json()["id"]
    eid = cli(app, "admin").post("/api/pagamentos/%d/estorno" % pid, json={"motivo": "Motivo valido"}).get_json()["id"]
    assert cli(app, "admin").post("/api/pagamentos/%d/estorno" % eid, json={"motivo": "Motivo valido"}).status_code == 409
    assert cli(app, "admin").post("/api/pagamentos/9999/estorno", json={"motivo": "Motivo valido"}).status_code == 404


def test_log_imutavel(app):
    rid = nova(app)
    receber(app, rid, 1000)
    con = conectar(app.config["CAMINHO_BANCO"])
    for cmd in ("UPDATE pagamento SET valor_centavos=1", "DELETE FROM pagamento",
                "INSERT OR REPLACE INTO pagamento (id,reserva_id,tipo,forma,valor_centavos,apto,em) VALUES (1,%d,'recebimento','pix',5,'1','x')" % rid):
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(cmd)
    con.close()
