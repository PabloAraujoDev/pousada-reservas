"""Ajudantes dos testes do catálogo e da hora dos lançamentos."""
import pytest

from tests.conftest import criar_app_teste
from tests.test_despesas import AGORA, cli, nova_reserva  # noqa: F401  (reexportados)

PAPEIS = ["admin", "atendente", "recepcao", "diretoria", "consulta", "camareira"]
NOVO = {"categoria": "porcoes", "grupo": "", "descricao": "Pastel de queijo", "preco_centavos": 1800}


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def adm(app):
    return cli(app, "admin")


def criar(app, **extra):
    r = adm(app).post("/api/catalogo", json=dict(NOVO, **extra))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def itens_do_catalogo(app, papel="recepcao"):
    return cli(app, papel).get("/api/catalogo").get_json()["itens"]


def lancar_item(c, rid, item, qtd=1, chave=None, **extra):
    corpo = {"item_id": item["id"], "item_versao": item["versao"], "quantidade": qtd}
    if chave:
        corpo["chave"] = chave
    return c.post("/api/reservas/%d/despesas" % rid, json=dict(corpo, **extra))
