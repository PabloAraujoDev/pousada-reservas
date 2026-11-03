"""Entradas hostis na etapa 3B: tipos errados, NaN, negativos, enormes, XSS, número de cartão em NSU/referência/motivo, bordas de parcelas."""
import json

import pytest

from pousada.pagamentos import parcelas_valores
from tests.apoio_pagamentos import app, cli, conta, lancar, nova, receber, sql  # noqa: F401

PAN = "4111111111111111"


@pytest.mark.parametrize("valor", ["100", 1.5, True, None, [1], {"a": 1}, -1, 0, 10 ** 30, float("inf")])
def test_valor_de_tipo_errado_ou_absurdo(app, valor):
    rid = nova(app)
    c = cli(app, "admin")
    corpo = {"valor_centavos": valor, "forma": "pix", "chave": "chave-hostil-1", "conta_versao": 1}
    r = c.post("/api/reservas/%d/pagamentos" % rid, data=json.dumps(corpo, allow_nan=True), content_type="application/json")
    assert r.status_code in (400, 422) and sql(app, "SELECT COUNT(*) FROM pagamento") == [(0,)]


def test_nan_e_json_quebrado(app):
    rid = nova(app)
    c = cli(app, "admin")
    r = c.post("/api/reservas/%d/pagamentos" % rid, data='{"valor_centavos": NaN, "forma": "pix"}', content_type="application/json")
    assert r.status_code in (400, 422)
    assert c.post("/api/reservas/%d/pagamentos" % rid, data="[1,2]", content_type="application/json").status_code == 400
    assert c.post("/api/reservas/%d/pagamentos" % rid, data="x=1", content_type="application/x-www-form-urlencoded").status_code in (400, 415, 403)


@pytest.mark.parametrize("campo,valor", [("conta_versao", "1"), ("conta_versao", -3), ("conta_versao", None), ("chave", "curta"),
                                         ("chave", "chave com espaço!"), ("forma", "boleto"), ("forma", ["pix"]), ("itens", "d1"),
                                         ("itens", ["d1", "d1"]), ("itens", ["../x"]), ("itens", ["d1"] * 500)])
def test_campos_de_controle_invalidos(app, campo, valor):
    rid = nova(app)
    corpo = {"valor_centavos": 100, "forma": "pix", "chave": "chave-hostil-2", "conta_versao": 1}
    corpo[campo] = valor
    assert cli(app, "admin").post("/api/reservas/%d/pagamentos" % rid, json=corpo).status_code in (400, 422)


@pytest.mark.parametrize("texto", [PAN, "4111 1111 1111 1111", "4111-1111-1111-1111", "٤١١١١١١١١١١١١١١١"])
def test_numero_de_cartao_em_nsu_referencia_e_motivo(app, texto):
    rid = nova(app)
    r = receber(app, rid, 1000, "cartao", bandeira="Visa", modalidade="debito", autorizacao=texto)
    assert r.status_code == 422 and texto not in r.get_data(as_text=True)
    assert receber(app, rid, 1000, "pix", referencia=texto).status_code == 422
    pid = receber(app, rid, 1000).get_json()["id"]
    r = cli(app, "admin").post("/api/pagamentos/%d/estorno" % pid, json={"motivo": "erro no cartão " + texto})
    assert r.status_code == 422 and texto not in r.get_data(as_text=True)
    assert sql(app, "SELECT COUNT(*) FROM pagamento WHERE autorizacao IS NOT NULL OR referencia IS NOT NULL") == [(0,)]


@pytest.mark.parametrize("nsu", ["<script>", "abc def", "ab-12", "áéíóú", "A" * 13, "a\nb"])
def test_nsu_so_alfanumerico_ate_12(app, nsu):
    rid = nova(app)
    assert receber(app, rid, 1000, "cartao", bandeira="Visa", modalidade="credito", autorizacao=nsu).status_code == 422
    assert receber(app, rid, 1000, "cartao", bandeira="Visa", modalidade="credito", autorizacao="AbC123xyz999").status_code == 201


def test_motivo_invisivel_ou_com_inversao_de_texto(app):
    rid = nova(app)
    pid = receber(app, rid, 1000).get_json()["id"]
    for m in ("​​​​​​", "     ", "abc‮def gh", "abc\x00def gh", 5, None, "ab"):
        assert cli(app, "admin").post("/api/pagamentos/%d/estorno" % pid, json={"motivo": m}).status_code == 422


def test_xss_fica_como_texto_no_banco_e_na_api(app):
    rid = nova(app)
    xss = "<img src=x onerror=alert(1)>"
    lid = lancar(app, rid, 500, desc=xss)["id"]
    j = cli(app, "admin").get("/api/reservas/%d/lancamentos" % rid).get_json()
    assert xss in j["itens"][0]["descricao"] and j["itens"][0]["tipo"] == "lancamento" and lid
    assert cli(app, "admin").get("/api/reservas/%d/lancamentos" % rid).headers["Content-Type"].startswith("application/json")


def test_id_enorme_e_destino_hostil(app):
    rid = nova(app)
    c = cli(app, "admin")
    corpo = {"destino_id": 10 ** 30, "itens": ["d1"], "chave": "chave-hostil-3", "conta_versao": 1}
    assert c.post("/api/reservas/%d/transferir" % rid, json=corpo).status_code in (400, 422)
    corpo.update(destino_id="2", itens=["d99999999999"])
    assert c.post("/api/reservas/%d/transferir" % rid, json=corpo).status_code in (400, 422)
    assert c.post("/api/pagamentos/99999999999999999999/estorno", json={"motivo": "Motivo valido"}).status_code in (400, 404)


@pytest.mark.parametrize("valor,n", [(1, 1), (100, 3), (101, 3), (99999, 12), (500 * 12, 12), (7, 12), (10 ** 8, 12)])
def test_parcelas_somam_sempre_o_valor(valor, n):
    p = parcelas_valores(valor, n)
    assert len(p) == n and sum(p) == valor and max(p) - min(p) <= 1 and p == sorted(p, reverse=True)


def test_receber_com_conta_cancelada_ou_futura(app):
    rid = nova(app, a="203", i="2026-11-05", f="2026-11-07")
    assert receber(app, rid, 100).status_code == 422
    r2 = nova(app, a="204", diaria_centavos=None)
    cli(app, "admin").delete("/api/reservas/%d" % r2, json={"versao": 1, "motivo": "Cancelada pelo hóspede"})
    assert receber(app, r2, 100).status_code in (404, 409)


def test_cancelar_e_alterar_diaria_respeitam_pagamentos(app):
    rid = nova(app)
    receber(app, rid, 50000)
    d = cli(app, "admin").get("/api/reservas/%d" % rid).get_json()
    assert cli(app, "admin").delete("/api/reservas/%d" % rid, json={"versao": d["versao"], "motivo": "Cancelada pelo hóspede"}).status_code == 409
    corpo = dict(d, diaria_centavos=10000)
    assert cli(app, "admin").put("/api/reservas/%d" % rid, json=corpo).status_code == 409           # 3 x 100,00 < 500,00 pagos
    assert cli(app, "admin").put("/api/reservas/%d" % rid, json=dict(d, diaria_centavos=20000)).status_code == 200
    assert conta(app, rid)["totais"]["saldo_centavos"] == 10000
