"""Catálogo de itens: permissões por perfil, cadastro/edição/desativação, bloqueio otimista e log imutável."""
import sqlite3

import pytest

from pousada.db import conectar
from tests.apoio_catalogo import NOVO, PAPEIS, adm, app, cli, criar, itens_do_catalogo  # noqa: F401

LEEM = {"admin", "atendente", "recepcao"}            # quem lança lê o catálogo ativo (com preços)


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_do_catalogo(app, papel):
    c = cli(app, papel, "u_" + papel)
    ok = papel == "admin"
    assert (c.get("/api/catalogo").status_code == 200) == (papel in LEEM)
    assert (c.get("/api/catalogo?todos=1").status_code == 200) == ok
    assert (c.post("/api/catalogo", json=NOVO).status_code == 201) == ok
    assert (c.put("/api/catalogo/1", json=dict(NOVO, descricao="Água com gás 500", versao=1)).status_code == 200) == ok
    assert (c.post("/api/catalogo/1/ativo", json={"ativo": False, "versao": 2}).status_code == 200) == ok
    assert (c.get("/api/catalogo/1/log").status_code == 200) == ok
    assert (c.get("/api/relatorio/consumo?inicio=2026-10-01&fim=2026-10-31").status_code == 200) == ok
    assert c.delete("/api/catalogo/1").status_code in (403, 404, 405)


def test_quem_lanca_ve_preco_e_so_ativos_em_ordem(app):
    dados = cli(app, "recepcao").get("/api/catalogo").get_json()
    assert len(dados["itens"]) == 28 and "ativo" not in dados["itens"][0]
    assert dados["itens"][0]["descricao"] == "Água com gás" and dados["itens"][0]["preco_centavos"] == 500
    assert [c[1] for c in dados["categorias"]] == ["Bebidas", "Lavanderia", "Outros", "Porções"]
    adm(app).post("/api/catalogo/1/ativo", json={"ativo": False, "versao": 1})
    assert len(itens_do_catalogo(app)) == 27
    assert len(adm(app).get("/api/catalogo?todos=1").get_json()["itens"]) == 28


def test_cadastro_edicao_duplicidade_e_validacao(app):
    it = criar(app)
    assert it["versao"] == 1 and it["ativo"] is True
    assert adm(app).post("/api/catalogo", json=dict(NOVO, descricao="PASTEL DE QUEIJO")).status_code == 409
    for ruim in ({"preco_centavos": 0}, {"preco_centavos": 12.5}, {"preco_centavos": True}, {"preco_centavos": 1000001},
                 {"categoria": "pizza"}, {"descricao": "a"}, {"descricao": "x" * 81}, {"descricao": "Cartão 4111 1111 1111 1111"},
                 {"grupo": "x" * 41}, {"descricao": "ab‮cd"}):
        corpo = dict(NOVO, **dict({"descricao": "Outro item"}, **ruim))
        assert adm(app).post("/api/catalogo", json=corpo).status_code in (400, 422), ruim
    assert adm(app).post("/api/catalogo", json=[1]).status_code == 400
    r = adm(app).put("/api/catalogo/%d" % it["id"], json=dict(NOVO, descricao="Pastel de carne", preco_centavos=2000, versao=1))
    assert r.status_code == 200 and r.get_json()["versao"] == 2 and r.get_json()["preco_centavos"] == 2000
    assert adm(app).put("/api/catalogo/%d" % it["id"], json=dict(NOVO, versao=1)).status_code == 409          # versão velha
    assert adm(app).put("/api/catalogo/%d" % it["id"], json=NOVO).status_code == 400                           # sem versão
    assert adm(app).put("/api/catalogo/9999", json=dict(NOVO, versao=1)).status_code == 404


def test_desativar_reativar_e_log_imutavel(app):
    it = criar(app)
    url = "/api/catalogo/%d/ativo" % it["id"]
    r = adm(app).post(url, json={"ativo": False, "versao": 1})
    assert r.status_code == 200 and r.get_json()["ativo"] is False
    assert adm(app).post(url, json={"ativo": False, "versao": 2}).status_code == 409           # já desativado
    assert adm(app).post(url, json={"ativo": True, "versao": 1}).status_code == 409            # versão velha
    assert adm(app).post(url, json={"ativo": "sim", "versao": 2}).status_code == 400
    assert adm(app).post(url, json={"ativo": True, "versao": 2}).status_code == 200
    adm(app).put("/api/catalogo/%d" % it["id"], json=dict(NOVO, preco_centavos=1900, versao=3))
    log = adm(app).get("/api/catalogo/%d/log" % it["id"]).get_json()["itens"]
    assert [l["acao"] for l in log] == ["editado", "reativado", "desativado", "criado"]
    assert log[0]["por"] == "admin" and log[0]["antes"]["preco_centavos"] == 1800 and log[0]["depois"]["preco_centavos"] == 1900
    con = conectar(app.config["CAMINHO_BANCO"])
    for cmd in ("UPDATE catalogo_log SET acao='criado'", "DELETE FROM catalogo_log", "DELETE FROM catalogo_item"):
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(cmd)
    con.close()
