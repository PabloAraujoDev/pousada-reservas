"""Ajudantes comuns dos testes de pagamentos/transferência (etapa 3B): app com hora fixa, reservas com diária, clientes por papel."""
from datetime import datetime

import pytest

from pousada.db import conectar
from tests import conftest
from tests.conftest import criar_app_teste

AGORA = datetime(2026, 10, 29, 9, 0, 0)
RES = {"a": "201", "nome": "Maria Silva", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente",
       "o": "", "grupo": "", "diaria_centavos": 30000}          # 3 noites x R$ 300,00 = R$ 900,00


def cli(app, papel, login=None):
    cache = app.__dict__.setdefault("_cl", {})
    chave = login or papel
    if chave not in cache:
        cache[chave] = conftest.cliente_como(app, papel, login)
    return cache[chave]


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def nova(app, **extra):
    r = cli(app, "admin").post("/api/reservas", json=dict(RES, **extra))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()["id"]


def detalhe(app, rid, papel="admin"):
    return cli(app, papel).get("/api/reservas/%d" % rid).get_json()


def conta(app, rid, papel="admin"):
    return cli(app, papel).get("/api/reservas/%d/despesas" % rid).get_json()


def lancar(app, rid, valor=800, qtd=1, papel="admin", desc="Água 500ml", chave=None):
    r = cli(app, papel).post("/api/reservas/%d/despesas" % rid, json={"categoria": "bar", "descricao": desc, "quantidade": qtd,
                                                                     "valor_unit_centavos": valor, "chave": chave})
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


_contador = [0]


def corpo_pag(app, rid, valor, forma="dinheiro", papel="admin", **extra):
    _contador[0] += 1
    base = {"valor_centavos": valor, "forma": forma, "chave": "chave-pag-%d" % _contador[0],
            "conta_versao": conta(app, rid)["conta"]["versao"]}
    base.update(extra)
    return base


def receber(app, rid, valor, forma="dinheiro", papel="admin", **extra):
    return cli(app, papel).post("/api/reservas/%d/pagamentos" % rid, json=corpo_pag(app, rid, valor, forma, papel, **extra))


def sql(app, comando, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return [tuple(r) for r in con.execute(comando, args)]
    finally:
        con.close()


def totais(app, rid, papel="admin"):
    return conta(app, rid, papel)["totais"]
