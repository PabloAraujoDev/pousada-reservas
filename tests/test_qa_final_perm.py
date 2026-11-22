"""QA final: matriz de permissões das rotas novas (notas, despesas, governança) por perfil e vazamento de valores."""
from datetime import datetime

import pytest

from tests import conftest
from tests.conftest import criar_app_teste

AGORA = datetime(2026, 10, 29, 9, 0, 0)
RES = {"a": "201", "nome": "Maria Silva", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente",
       "o": "Alergia a amendoim", "grupo": "", "diaria_centavos": 45000}
PAPEIS = ["admin", "atendente", "recepcao", "camareira", "diretoria", "consulta"]


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def cl(app, papel):
    cache = app.__dict__.setdefault("_cl", {})
    if papel not in cache:
        cache[papel] = conftest.cliente_como(app, papel)
    return cache[papel]


@pytest.fixture
def rid(app):
    r = cl(app, "admin").post("/api/reservas", json=RES)
    assert r.status_code == 201
    rid = r.get_json()["id"]
    assert cl(app, "admin").post("/api/reservas/%d/despesas" % rid, json={
        "categoria": "bar", "descricao": "Cerveja", "quantidade": 2, "valor_unit_centavos": 1234}).status_code == 201
    assert cl(app, "admin").post("/api/reservas/%d/notas" % rid, json={"texto": "VIP segredo"}).status_code == 201
    assert cl(app, "admin").post("/api/unidades/201/notas", json={"texto": "Ar condicionado barulhento"}).status_code == 201
    return rid


ESPERADO = {   # (metodo, caminho) -> papéis que recebem 200/201
    "desp_get": {"admin", "atendente", "recepcao", "diretoria"},
    "notas_get": {"admin", "atendente", "recepcao", "diretoria", "consulta"},
    "un_notas_get": {"admin", "atendente", "recepcao", "diretoria", "consulta", "camareira"},
    "resumo": {"admin", "atendente", "recepcao", "diretoria"},
}


@pytest.mark.parametrize("papel", PAPEIS)
def test_leituras_por_perfil(app, rid, papel):
    c = cl(app, papel)
    ok = lambda r: r.status_code == 200
    assert ok(c.get("/api/reservas/%d/despesas" % rid)) == (papel in ESPERADO["desp_get"])
    assert ok(c.get("/api/reservas/%d/notas" % rid)) == (papel in ESPERADO["notas_get"])
    assert ok(c.get("/api/unidades/201/notas")) == (papel in ESPERADO["un_notas_get"])
    assert ok(c.get("/api/despesas/resumo")) == (papel in ESPERADO["resumo"])
    r = c.get("/api/reservas")
    corpo = r.get_data(as_text=True)
    assert "45000" not in corpo and "diaria" not in corpo          # lista nunca traz valor
    if papel == "camareira":
        assert "Maria" not in corpo and "tem_despesa" not in corpo and "amendoim" not in corpo
    if papel in ("consulta",):
        assert "tem_despesa" not in corpo


@pytest.mark.parametrize("papel", PAPEIS)
def test_escritas_por_perfil(app, rid, papel):
    c = cl(app, papel)
    lancar = c.post("/api/reservas/%d/despesas" % rid, json={"item_id": 1, "item_versao": 1, "quantidade": 1})
    assert (lancar.status_code == 201) == (papel in ("admin", "atendente", "recepcao"))
    nota = c.post("/api/reservas/%d/notas" % rid, json={"texto": "x nota"})
    assert (nota.status_code == 201) == (papel in ("admin", "atendente", "recepcao"))
    nu = c.post("/api/unidades/202/notas", json={"texto": "x nota"})
    assert (nu.status_code == 201) == (papel in ("admin", "atendente"))


def test_camareira_nao_ve_valor_nem_autor_nem_nota_de_reserva(app, rid):
    c = cl(app, "camareira")
    corpo = c.get("/api/unidades/201/notas").get_data(as_text=True)
    assert "admin" not in corpo and "por" not in corpo
    assert "VIP" not in corpo
    g = c.get("/api/governanca").get_data(as_text=True)
    for proibido in ("Maria", "45000", "1234", "VIP", "pendente"):
        assert proibido not in g, proibido


def test_valores_somem_para_quem_nao_tem_valores_ver(app, rid):
    # consulta nao tem despesas.ver nem valores.ver: detalhe sem diaria
    d = cl(app, "consulta").get("/api/reservas/%d" % rid).get_json()
    assert "diaria_centavos" not in d
    d = cl(app, "diretoria").get("/api/reservas/%d" % rid).get_json()
    assert d["diaria_centavos"] == 45000
