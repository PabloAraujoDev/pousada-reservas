"""A HORA exata do lançamento é dado de auditoria só do administrador: nenhuma outra resposta pode trazê-la (filtro no servidor)."""
import re

import pytest

from tests.apoio_catalogo import PAPEIS, adm, app, cli, itens_do_catalogo, lancar_item, nova_reserva  # noqa: F401

HORA = re.compile(r"\d{2}:\d{2}")
VER_CONTA = {"admin", "atendente", "recepcao", "diretoria"}


def _montar(app):
    """Reserva com lançamento por item (recepção), estorno (atendente) e histórico: tudo às 09:00:00 (hora fixa do teste)."""
    rid = nova_reserva(app)["id"]
    item = itens_do_catalogo(app)[0]
    lid = lancar_item(cli(app, "recepcao"), rid, item, qtd=2).get_json()["id"]
    cli(app, "atendente").post("/api/despesas/%d/estorno" % lid, json={"motivo": "lançado errado"})
    lancar_item(cli(app, "recepcao"), rid, item)
    return rid


def _urls(rid):
    return ["/api/reservas/%d/despesas" % rid, "/api/reservas/%d/lancamentos" % rid, "/api/reservas/%d/historico" % rid,
            "/api/historico?limite=500", "/api/reservas/%d" % rid, "/api/reservas"]


def _despesas_em(url, r):
    """Data/hora ('em') dos itens de despesa; no histórico só as linhas de ação de despesa (login, criar reserva etc. têm hora normal)."""
    dados = r.get_json()
    linhas = dados["itens"] if isinstance(dados, dict) and "itens" in dados else dados
    if not isinstance(linhas, list):
        return []
    if "historico" in url:
        linhas = [x for x in linhas if x["acao"].startswith("despesa")]
    return [x["em"] for x in linhas if isinstance(x, dict) and "em" in x and x.get("origem", "despesa") == "despesa"]


@pytest.mark.parametrize("papel", PAPEIS)
def test_hora_so_para_o_administrador(app, papel):
    rid = _montar(app)
    c = cli(app, papel, "u_" + papel)
    for url in _urls(rid):
        r = c.get(url)
        if r.status_code != 200:
            continue
        corpo = r.get_data(as_text=True)
        for em in _despesas_em(url, r):
            if papel == "admin":
                continue
            assert not HORA.search(em), (papel, url, em)
        if papel != "admin" and ("/despesas" in url or "/lancamentos" in url):
            assert "09:00" not in corpo and "2026-10-29" in corpo, (papel, url)      # a DATA continua visível, a hora não
    if papel == "admin":
        itens = c.get("/api/reservas/%d/despesas" % rid).get_json()["itens"]
        assert {i["em"] for i in itens} == {"2026-10-29 09:00:00"}
        assert any("09:00" in x["em"] for x in c.get("/api/reservas/%d/lancamentos" % rid).get_json()["itens"])
        assert any(HORA.search(x["em"]) for x in c.get("/api/historico").get_json() if x["acao"] == "despesa_lancada")


@pytest.mark.parametrize("papel", PAPEIS)
def test_resposta_do_lancar_nao_traz_a_hora_para_quem_nao_e_admin(app, papel):
    if papel not in ("atendente", "recepcao"):
        return
    rid = nova_reserva(app)["id"]
    r = lancar_item(cli(app, papel), rid, itens_do_catalogo(app)[0])
    assert r.status_code == 201 and r.get_json()["em"] == "2026-10-29"
    e = cli(app, "admin").post("/api/reservas/%d/despesas" % rid, json={"item_id": 1, "item_versao": 1, "quantidade": 1})
    assert e.get_json()["em"] == "2026-10-29 09:00:00"


def test_hora_vem_do_servidor_nunca_do_cliente(app):
    rid = nova_reserva(app)["id"]
    item = itens_do_catalogo(app)[0]
    assert lancar_item(adm(app), rid, item, em="2000-01-01 01:01:01").status_code == 400            # campo extra recusado
    avulso = {"categoria": "bar", "descricao": "Avulso", "quantidade": 1, "valor_unit_centavos": 100, "em": "2000-01-01 01:01:01"}
    assert adm(app).post("/api/reservas/%d/despesas" % rid, json=avulso).get_json()["em"] == "2026-10-29 09:00:00"


def test_relatorio_de_consumo_do_administrador(app):
    rid = _montar(app)
    r = adm(app).get("/api/relatorio/consumo?inicio=2026-10-29&fim=2026-10-29")
    assert r.status_code == 200
    d = r.get_json()
    assert len(d["itens"]) == 3 and d["total_centavos"] == 500 and not d["cortado"]
    l0 = d["itens"][0]
    assert l0["em"] == "2026-10-29 09:00:00" and l0["apto"] == "201" and l0["hospede"] == "Maria Silva"
    assert (l0["descricao"], l0["quantidade"], l0["usuario_login"], l0["reserva_id"]) == ("Água com gás", 2, "recepcao", rid)
    assert adm(app).get("/api/relatorio/consumo?inicio=2026-10-30&fim=2026-10-30").get_json()["itens"] == []
    for q in ("", "?inicio=2026-10-31&fim=2026-10-01", "?inicio=x&fim=y", "?inicio=2026-01-01&fim=2026-12-31"):
        assert adm(app).get("/api/relatorio/consumo" + q).status_code == 400
