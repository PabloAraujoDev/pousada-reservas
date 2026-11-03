"""QA final: texto feito só de caracteres invisíveis (zero-width, braile em branco...) vale como vazio em todo campo de texto."""
from datetime import datetime

import pytest

from tests import conftest
from tests.conftest import criar_app_teste

INVISIVEIS = ["​", "⠀", "ㅤ", " ​‍ ", "﻿", "­"]
RES = {"a": "201", "nome": "Maria", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente", "o": "", "grupo": ""}


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=datetime(2026, 10, 29, 9, 0, 0))


@pytest.fixture
def adm(app):
    c = conftest.cliente_como(app, "admin")
    c.rid = c.post("/api/reservas", json=RES).get_json()["id"]
    return c


@pytest.mark.parametrize("txt", INVISIVEIS)
def test_nome_nota_despesa_obs_motivo_invisivel_sao_recusados(adm, txt):
    assert adm.post("/api/reservas", json=dict(RES, a="202", nome=txt)).status_code == 400
    assert adm.post("/api/reservas/%d/notas" % adm.rid, json={"texto": txt}).status_code == 422
    assert adm.post("/api/unidades/202/notas", json={"texto": txt}).status_code == 422
    assert adm.post("/api/reservas/%d/despesas" % adm.rid, json={
        "categoria": "bar", "descricao": txt * 3, "quantidade": 1, "valor_unit_centavos": 100}).status_code == 422
    n = adm.post("/api/reservas/%d/notas" % adm.rid, json={"texto": "ok"}).get_json()
    assert adm.post("/api/notas/%d/ocultar" % n["id"], json={"motivo": txt * 4, "versao": 1}).status_code == 422
    assert adm.post("/api/notas/%d/corrigir" % n["id"], json={"texto": txt, "versao": 1}).status_code == 422


def test_texto_com_parte_visivel_continua_valendo(adm):
    assert adm.post("/api/reservas/%d/notas" % adm.rid, json={"texto": "​VIP​"}).status_code == 201
    r = adm.post("/api/governanca/acao", json={"acao": "observacao", "unidades": [{"u": "202", "versao": 1}], "obs": "​"})
    assert r.status_code == 200
    g = next(u for u in adm.get("/api/governanca").get_json()["unidades"] if u["u"] == "202")
    assert g["obs"] == ""


def test_varredura_de_cartoes_olha_notas_e_despesas(adm, app):
    """Os logs imutáveis também entram na varredura (só se alguém burlar a validação, gravando direto no banco)."""
    from pousada.db import conectar
    from pousada.varredura_cartoes import varrer
    con = conectar(app.config["CAMINHO_BANCO"])
    con.execute("INSERT INTO nota (escopo,reserva_id,tipo,texto,em) VALUES ('reserva',?,'nota','4111 1111 1111 1111','2026-10-29 10:00:00')", (adm.rid,))
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em) "
                "VALUES (?,'lancamento','bar','5555 5555 5555 4444',1,100,100,'201','2026-10-29 10:00:00')", (adm.rid,))
    achados = {(a["tabela"], a["campo"]) for a in varrer(con)}
    con.close()
    assert ("nota", "texto") in achados and ("despesa_lancamento", "descricao") in achados
