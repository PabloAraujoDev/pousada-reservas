"""QA do catálogo: entradas hostis, ordem alfabética com acento, estouro de total, conta fechada, transferência e extrato."""
import pytest

from tests.apoio_catalogo import NOVO, adm, app, cli, criar, itens_do_catalogo, lancar_item, nova_reserva  # noqa: F401
from tests.test_transferencia import transferir


def _reserva_b(app):
    r = cli(app, "admin").post("/api/reservas", json={"a": "202", "nome": "João Souza", "extras": "", "n": 2, "i": "2026-10-27",
                                                       "f": "2026-10-30", "p": "pendente", "o": "", "grupo": "", "diaria_centavos": 30000})
    return r.get_json()["id"]


@pytest.mark.parametrize("corpo", [{"item_id": 2 ** 70, "item_versao": 1, "quantidade": 1},
                                   {"item_id": 1, "item_versao": 2 ** 70, "quantidade": 1},
                                   {"item_id": -1, "item_versao": 1, "quantidade": 1},
                                   {"item_id": "1", "item_versao": 1, "quantidade": 1},
                                   {"item_id": None, "item_versao": 1, "quantidade": 1}])
def test_item_id_e_versao_hostis_nunca_dao_500(app, corpo):
    rid = nova_reserva(app)["id"]
    for papel in ("recepcao", "admin"):
        r = cli(app, papel).post("/api/reservas/%d/despesas" % rid, json=corpo)
        assert r.status_code in (400, 404, 409, 422), (papel, r.status_code)


def test_id_gigante_na_url_do_catalogo_nao_da_500(app):
    for r in (adm(app).put("/api/catalogo/%d" % 2 ** 70, json=dict(NOVO, versao=1)),
              adm(app).post("/api/catalogo/%d/ativo" % 2 ** 70, json={"ativo": False, "versao": 1}),
              adm(app).get("/api/catalogo/%d/log" % 2 ** 70)):
        assert r.status_code in (400, 404)


@pytest.mark.parametrize("qtd", [0, -1, 100, 10 ** 30, 1.5, 2.0, "2", True, None, [1]])
def test_quantidade_hostil_por_item(app, qtd):
    rid = nova_reserva(app)["id"]
    r = lancar_item(cli(app, "recepcao"), rid, itens_do_catalogo(app)[0], qtd=qtd)
    assert r.status_code == 422


def test_preco_em_centavos_e_estouro_de_total(app):
    rid = nova_reserva(app)["id"]
    caro = criar(app, descricao="Vinho raro", preco_centavos=1000000)             # R$ 10.000,00, o máximo
    assert adm(app).post("/api/catalogo", json=dict(NOVO, descricao="Caro demais", preco_centavos=1000001)).status_code == 422
    heineken = [i for i in itens_do_catalogo(app) if i["descricao"] == "Heineken 600ml"][0]
    assert heineken["preco_centavos"] == 1500                                       # R$ 15,00
    assert lancar_item(cli(app, "recepcao"), rid, caro, qtd=99).status_code == 201   # R$ 990.000,00
    r = lancar_item(cli(app, "recepcao"), rid, caro, qtd=2)                          # passaria de R$ 1.000.000,00
    assert r.status_code == 422 and "máximo" in r.get_json()["erro"]
    assert cli(app, "recepcao").get("/api/reservas/%d/despesas" % rid).get_json()["totais"]["despesas_centavos"] == 99000000


def test_ordem_alfabetica_ignora_acento_e_maiuscula(app):
    for d in ("Ágata", "abacaxi", "Zebra", "água de coco", "Éclair", "Eclipse"):
        criar(app, categoria="outros", grupo="", descricao=d)
    nomes = [i["descricao"] for i in itens_do_catalogo(app) if i["categoria"] == "outros"]
    assert nomes == ["abacaxi", "Ágata", "água de coco", "Eclipse", "Éclair", "Zebra"] or nomes == [
        "abacaxi", "Ágata", "água de coco", "Éclair", "Eclipse", "Zebra"]
    assert nomes.index("Ágata") < nomes.index("água de coco") < nomes.index("Zebra")
    assert adm(app).post("/api/catalogo", json=dict(NOVO, categoria="outros", grupo="", descricao="AGATA")).status_code == 409
    todos = [i["descricao"] for i in itens_do_catalogo(app)]
    bebidas = [i for i in itens_do_catalogo(app) if i["categoria"] == "bebidas"]
    assert [i["grupo"] for i in bebidas] == sorted([i["grupo"] for i in bebidas], key=lambda g: g.casefold().replace("á", "a"))
    assert len(todos) == 34


def test_conta_fechada_bloqueia_lancamento_por_item_mas_nao_o_duplo_clique(app):
    rid = nova_reserva(app)["id"]
    item = itens_do_catalogo(app)[0]
    lancar_item(cli(app, "recepcao"), rid, item, chave="chave-fecha-1")
    c = cli(app, "admin").get("/api/reservas/%d/despesas" % rid).get_json()
    cli(app, "admin").post("/api/reservas/%d/pagamentos" % rid, json={"valor_centavos": c["totais"]["conta_centavos"], "forma": "dinheiro",
                                                                      "chave": "pag-fecha-001", "conta_versao": c["conta"]["versao"]})
    v = cli(app, "admin").get("/api/reservas/%d/despesas" % rid).get_json()["conta"]["versao"]
    assert cli(app, "admin").post("/api/reservas/%d/conta/fechar" % rid, json={"conta_versao": v}).status_code == 200
    assert lancar_item(cli(app, "recepcao"), rid, item).status_code == 409
    assert lancar_item(cli(app, "recepcao"), rid, item, chave="chave-fecha-1").status_code == 200   # repetição devolve o original


def test_transferencia_mantem_item_e_extrato_sem_hora_para_nao_admin(app):
    a, b = nova_reserva(app)["id"], _reserva_b(app)
    item = itens_do_catalogo(app)[0]
    lid = lancar_item(cli(app, "recepcao"), a, item, qtd=2).get_json()["id"]
    assert transferir(app, a, b, ["d%d" % lid]).status_code == 201
    destino = [i for i in cli(app, "admin").get("/api/reservas/%d/despesas" % b).get_json()["itens"]][0]
    assert destino["item_id"] == item["id"] and destino["total_centavos"] == 1000
    for papel in ("recepcao", "atendente"):
        for rid in (a, b):
            for x in cli(app, papel).get("/api/reservas/%d/lancamentos" % rid).get_json()["itens"]:
                if x["origem"] == "despesa":
                    assert len(x["em"]) == 10, (papel, x)
    assert any(len(x["em"]) == 19 for x in cli(app, "admin").get("/api/reservas/%d/lancamentos" % b).get_json()["itens"])
    est = cli(app, "atendente").post("/api/despesas/%d/estorno" % lid, json={"motivo": "tentando de novo"})
    assert est.status_code == 409                                               # já foi transferido (estornado)


def test_texto_livre_do_catalogo_passa_pelo_detector_de_cartao(app):
    for campo in ("grupo", "descricao"):
        r = adm(app).post("/api/catalogo", json=dict(NOVO, **{campo: "pedido 4111 1111 1111 1111"}))
        assert r.status_code in (400, 422) and "4111" not in r.get_data(as_text=True)
    it = criar(app)
    r = adm(app).put("/api/catalogo/%d" % it["id"], json=dict(NOVO, descricao="4111111111111111", versao=1))
    assert r.status_code in (400, 422)
    avulso = {"categoria": "bar", "descricao": "4111 1111 1111 1111", "quantidade": 1, "valor_unit_centavos": 100}
    assert adm(app).post("/api/reservas/%d/despesas" % nova_reserva(app)["id"], json=avulso).status_code == 422


def test_relatorio_limite_de_93_dias_e_perfis(app):
    assert adm(app).get("/api/relatorio/consumo?inicio=2026-07-01&fim=2026-10-01").status_code == 200      # 92 dias
    assert adm(app).get("/api/relatorio/consumo?inicio=2026-07-01&fim=2026-10-02").status_code == 200      # 93 dias
    assert adm(app).get("/api/relatorio/consumo?inicio=2026-07-01&fim=2026-10-03").status_code == 400      # 94 dias
    for papel in ("recepcao", "atendente", "diretoria", "consulta", "camareira"):
        assert cli(app, papel, "r_" + papel).get("/api/relatorio/consumo?inicio=2026-10-01&fim=2026-10-02").status_code == 403
