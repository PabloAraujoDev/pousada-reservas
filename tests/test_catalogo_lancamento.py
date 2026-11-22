"""Lançamento por item do catálogo: preço congelado, recusas, avulso só do administrador, estorno e regra de ouro."""
from tests.apoio_catalogo import adm, app, cli, itens_do_catalogo, lancar_item, nova_reserva  # noqa: F401


def test_lancar_por_item_congela_descricao_e_preco(app):
    rid = nova_reserva(app)["id"]
    item = itens_do_catalogo(app)[0]                                  # Água com gás, R$ 5,00
    r = lancar_item(cli(app, "recepcao"), rid, item, qtd=3, chave="chave-item-1")
    assert r.status_code == 201
    lin = r.get_json()
    assert (lin["descricao"], lin["quantidade"], lin["valor_unit_centavos"], lin["total_centavos"], lin["categoria"]) == ("Água com gás", 3, 500, 1500, "bar")
    assert lin["item_id"] == item["id"] and len(lin["em"]) == 10      # recepção: só a data
    assert lancar_item(cli(app, "recepcao"), rid, item, qtd=3, chave="chave-item-1").status_code == 200   # duplo clique
    adm(app).put("/api/catalogo/%d" % item["id"], json={"categoria": "bebidas", "grupo": "Águas", "descricao": "Água com gás 500ml",
                                                         "preco_centavos": 700, "versao": item["versao"]})
    antigo = lancar_item(cli(app, "recepcao"), rid, item)             # a tela ainda tinha a versão velha
    assert antigo.status_code == 409 and "alterado" in antigo.get_json()["erro"]
    itens = cli(app, "recepcao").get("/api/reservas/%d/despesas" % rid).get_json()["itens"]
    assert itens[0]["descricao"] == "Água com gás" and itens[0]["valor_unit_centavos"] == 500         # histórico intacto
    novo = itens_do_catalogo(app)[0]
    assert lancar_item(cli(app, "recepcao"), rid, novo).get_json()["valor_unit_centavos"] == 700
    adm(app).post("/api/catalogo/%d/ativo" % item["id"], json={"ativo": False, "versao": novo["versao"]})
    assert lancar_item(cli(app, "recepcao"), rid, novo).status_code == 409                           # desativado


def test_cliente_nao_escolhe_preco_nem_avulso_sem_ser_admin(app):
    rid = nova_reserva(app)["id"]
    item = itens_do_catalogo(app)[0]
    assert lancar_item(cli(app, "recepcao"), rid, item, valor_unit_centavos=1).status_code == 400
    assert lancar_item(cli(app, "recepcao"), rid, item, descricao="Grátis").status_code == 400
    assert lancar_item(cli(app, "recepcao"), rid, dict(item, id=99999)).status_code == 404
    assert lancar_item(cli(app, "recepcao"), rid, item, qtd=0).status_code == 422
    assert lancar_item(cli(app, "recepcao"), rid, item, qtd=100).status_code == 422
    avulso = {"categoria": "bar", "descricao": "Avulso", "quantidade": 1, "valor_unit_centavos": 1}
    for papel in ("recepcao", "atendente"):
        assert cli(app, papel).post("/api/reservas/%d/despesas" % rid, json=avulso).status_code == 403
    r = adm(app).post("/api/reservas/%d/despesas" % rid, json=avulso)
    assert r.status_code == 201 and r.get_json()["item_id"] is None


def test_conta_com_item_estorno_e_total(app):
    rid = nova_reserva(app)["id"]
    item = itens_do_catalogo(app, "atendente")[1]                     # Água sem gás, R$ 4,00
    lid = lancar_item(cli(app, "atendente"), rid, item, qtd=2).get_json()["id"]
    assert cli(app, "atendente").get("/api/reservas/%d/despesas" % rid).get_json()["totais"]["despesas_centavos"] == 800
    e = cli(app, "atendente").post("/api/despesas/%d/estorno" % lid, json={"motivo": "lançado errado"})
    assert e.status_code == 201 and e.get_json()["item_id"] == item["id"]
    assert cli(app, "atendente").get("/api/reservas/%d/despesas" % rid).get_json()["totais"]["despesas_centavos"] == 0
