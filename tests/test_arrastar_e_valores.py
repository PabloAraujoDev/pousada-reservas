"""Tipo de hóspede, valor da diária (que não vaza) e a rota de mover reserva (arrastar no mapa)."""
import json
import os
import shutil
import sqlite3
import threading

import pytest

from pousada.db import conectar, iniciar_banco
from pousada.regras import validar_reserva
from tests.conftest import cliente_como, criar_app_teste

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESERVA = {"a": "201", "nome": "Hóspede Valioso", "extras": "", "n": 2, "i": "2026-10-10", "f": "2026-10-12",
           "p": "pendente", "o": "", "grupo": ""}
PAPEIS = ["admin", "atendente", "recepcao", "camareira", "diretoria", "consulta"]
VEEM_VALOR = {"admin", "atendente", "recepcao", "diretoria"}
SEGREDO = 98765          # centavos: o número que jamais pode aparecer fora do detalhe


def _historico(app):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return [dict(r) for r in con.execute("SELECT * FROM historico ORDER BY id")]
    finally:
        con.close()


def _criar(cli, **extra):
    r = cli.post("/api/reservas", json=dict(RESERVA, **extra))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


# ---------------------------------------------------------------- migração 009

def test_migracao_009_mantem_reservas_e_aceita_tipo_e_diaria(tmp_path):
    antigas = tmp_path / "ate_008"
    antigas.mkdir()
    for nome in sorted(os.listdir(os.path.join(RAIZ, "migrations"))):
        if nome < "009":
            shutil.copy(os.path.join(RAIZ, "migrations", nome), antigas / nome)
    banco = str(tmp_path / "antigo.db")
    iniciar_banco(banco, str(antigas))
    con = conectar(banco)
    con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,criado,alterado,versao) "
                "VALUES ('201','Antiga','x',2,'2026-10-10','2026-10-12','pago','obs','2026-01-01','2026-01-02',4)")
    con.close()
    iniciar_banco(banco, os.path.join(RAIZ, "migrations"))
    con = conectar(banco)
    try:
        r = dict(con.execute("SELECT * FROM reservas").fetchone())
        assert r["nome"] == "Antiga" and r["versao"] == 4 and r["p"] == "pago"
        assert r["tipo"] is None and r["diaria_centavos"] is None
        con.execute("UPDATE reservas SET tipo='socio', diaria_centavos=12345")
        for coluna, valor in (("tipo", "vip"), ("diaria_centavos", -1), ("diaria_centavos", 100000001)):
            with pytest.raises(sqlite3.IntegrityError):
                con.execute("UPDATE reservas SET %s=?" % coluna, (valor,))
        assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 9
    finally:
        con.close()


# ---------------------------------------------------------------- validação

@pytest.mark.parametrize("campo,valor", [
    ("tipo", "vip"), ("tipo", 1), ("tipo", True), ("tipo", ["socio"]),
    ("diaria_centavos", True), ("diaria_centavos", 10.5), ("diaria_centavos", 10.0), ("diaria_centavos", "100"),
    ("diaria_centavos", -1), ("diaria_centavos", 100000001), ("diaria_centavos", 10 ** 30), ("diaria_centavos", []),
])
def test_validacao_recusa_tipo_e_diaria_invalidos(campo, valor):
    dados, erro = validar_reserva(dict(RESERVA, **{campo: valor}))
    assert dados is None and erro


def test_validacao_aceita_tipo_e_diaria_validos_e_normaliza():
    d, erro = validar_reserva(dict(RESERVA, tipo="", diaria_centavos=0))
    assert erro is None and d["tipo"] is None and d["diaria_centavos"] == 0
    d, _ = validar_reserva(dict(RESERVA, tipo="convidado", diaria_centavos=100000000))
    assert d["tipo"] == "convidado" and d["diaria_centavos"] == 100000000
    d, _ = validar_reserva(RESERVA)                 # ausente fica ausente (a rota decide: criar = NULL, editar = mantém)
    assert "tipo" not in d and "diaria_centavos" not in d


def test_api_recusa_diaria_invalida(cli):
    assert cli.post("/api/reservas", json=dict(RESERVA, diaria_centavos=1.5)).status_code == 400
    assert cli.post("/api/reservas", json=dict(RESERVA, tipo="vip")).status_code == 400


# ---------------------------------------------------------------- tipo e diária: ausente x null no PUT

def test_put_ausente_mantem_e_null_apaga(app, cli):
    r = _criar(cli, tipo="socio", diaria_centavos=SEGREDO)
    a = cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, nome="Novo Nome", versao=1))
    assert a.status_code == 200 and a.get_json()["tipo"] == "socio"
    d = cli.get("/api/reservas/%d" % r["id"]).get_json()
    assert d["tipo"] == "socio" and d["diaria_centavos"] == SEGREDO and d["nome"] == "Novo Nome"
    b = cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, diaria_centavos=None, tipo="convidado", versao=2))
    assert b.status_code == 200
    d = cli.get("/api/reservas/%d" % r["id"]).get_json()
    assert d["tipo"] == "convidado" and d["diaria_centavos"] is None
    c = cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, tipo=None, versao=3))
    assert cli.get("/api/reservas/%d" % r["id"]).get_json()["tipo"] is None and c.status_code == 200


def test_recepcao_mantem_tipo_e_diaria(app, cli):
    r = _criar(cli, tipo="socio", diaria_centavos=SEGREDO)
    rec = cliente_como(app, "recepcao")
    x = rec.put("/api/reservas/%d" % r["id"], json={"p": "pago", "versao": 1, "tipo": "convidado", "diaria_centavos": 1})
    assert x.status_code == 200
    d = cli.get("/api/reservas/%d" % r["id"]).get_json()
    assert d["p"] == "pago" and d["tipo"] == "socio" and d["diaria_centavos"] == SEGREDO


def test_quem_nao_pode_editar_valores_tem_o_campo_ignorado(app, cli, monkeypatch):
    from pousada import permissoes
    monkeypatch.setitem(permissoes.PERMISSOES, "atendente", permissoes.PERMISSOES["atendente"] - {"valores.editar"})
    at = cliente_como(app, "atendente")
    novo = at.post("/api/reservas", json=dict(RESERVA, diaria_centavos=500, tipo="socio")).get_json()
    d = cli.get("/api/reservas/%d" % novo["id"]).get_json()
    assert d["diaria_centavos"] is None and d["tipo"] == "socio"
    at.put("/api/reservas/%d" % novo["id"], json=dict(RESERVA, diaria_centavos=777, versao=1))
    assert cli.get("/api/reservas/%d" % novo["id"]).get_json()["diaria_centavos"] is None


# ---------------------------------------------------------------- detalhe por papel

@pytest.mark.parametrize("papel", PAPEIS)
def test_detalhe_por_papel(app, cli, papel):
    r = _criar(cli, tipo="socio", diaria_centavos=SEGREDO)
    c = cli if papel == "admin" else cliente_como(app, papel)
    resp = c.get("/api/reservas/%d" % r["id"])
    if papel == "camareira":
        assert resp.status_code == 403
        return
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["tipo"] == "socio" and j["nome"] == "Hóspede Valioso"
    if papel in VEEM_VALOR:
        assert j["diaria_centavos"] == SEGREDO
    else:
        assert "diaria_centavos" not in j and str(SEGREDO) not in resp.get_data(as_text=True)


def test_detalhe_inexistente_e_cancelada(app, cli):
    assert cli.get("/api/reservas/999").status_code == 404
    r = _criar(cli, diaria_centavos=SEGREDO)
    cli.delete("/api/reservas/%d" % r["id"], json={"versao": 1, "motivo": "teste"})
    assert cli.get("/api/reservas/%d" % r["id"]).status_code == 200                 # admin vê canceladas
    assert cliente_como(app, "atendente").get("/api/reservas/%d" % r["id"]).status_code == 200
    for papel in ("recepcao", "diretoria", "consulta"):                              # sem ver_canceladas: 404
        assert cliente_como(app, papel).get("/api/reservas/%d" % r["id"]).status_code == 404


def test_detalhe_exige_login(app):
    assert app.test_client().get("/api/reservas/1").status_code == 401


# ---------------------------------------------------------------- a diária não vaza

def test_diaria_nunca_aparece_em_listas_busca_folha_camareiras_e_historico(app, cli):
    r = _criar(cli, tipo="convidado", diaria_centavos=SEGREDO)
    _criar(cli, a="202", nome="Outro", diaria_centavos=SEGREDO + 1)
    cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, diaria_centavos=SEGREDO + 5, versao=1))
    extra = _criar(cli, a="203", diaria_centavos=SEGREDO + 2)
    cli.delete("/api/reservas/%d" % extra["id"], json={"versao": 1, "motivo": "teste"})
    urls = ["/api/reservas", "/api/reservas?canceladas=1", "/api/export.csv?inicio=2026-10-08&dias=7",
            "/api/folha.pdf?inicio=2026-10-05", "/api/camareiras?inicio=2026-10-08&fim=2026-10-14&estadias=1&nomes=1",
            "/api/historico", "/api/reservas/%d/historico" % r["id"]]
    for papel in PAPEIS:
        c = cli if papel == "admin" else cliente_como(app, papel)
        for url in urls:
            resp = c.get(url)
            if resp.status_code != 200:
                continue
            corpo = resp.get_data().replace(b'"diaria":"alterado"', b"")     # o histórico só diz que mudou
            assert b"diaria" not in corpo.lower(), (papel, url)
            for n in (SEGREDO, SEGREDO + 1, SEGREDO + 2, SEGREDO + 5):
                assert str(n).encode() not in corpo, (papel, url, n)
            assert b"987,65" not in corpo and b"987.65" not in corpo
    assert any(b"tipo" in cli.get("/api/reservas").get_data() for _ in (0,))


def test_csv_completo_tem_a_coluna_so_para_quem_pode_ver_valores(app, cli):
    _criar(cli, diaria_centavos=SEGREDO)
    _criar(cli, a="202", nome="Sem valor")
    texto = cli.get("/api/export.csv").get_data(as_text=True)
    cab, l1, l2 = texto.splitlines()[:3]
    assert cab.split(";")[-1] == "diaria" and l1.split(";")[-1] == "987,65" and l2.split(";")[-1] == ""
    assert "diaria" in cliente_como(app, "diretoria").get("/api/export.csv").get_data(as_text=True)
    for papel in ("atendente", "recepcao", "camareira", "consulta"):
        assert cliente_como(app, papel).get("/api/export.csv").status_code == 403


def test_historico_registra_tipo_e_so_diz_que_a_diaria_mudou(app, cli):
    r = _criar(cli, tipo="socio", diaria_centavos=SEGREDO)
    cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, tipo="convidado", diaria_centavos=SEGREDO + 1, versao=1))
    alterar = _historico(app)[-1]
    assert alterar["acao"] == "alterar"
    assert json.loads(alterar["antes"]) == {"tipo": "socio"}
    assert json.loads(alterar["depois"]) == {"tipo": "convidado", "diaria": "alterado"}
    assert str(SEGREDO) not in json.dumps(_historico(app))
    cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, versao=2))              # nada enviado => nada muda
    assert json.loads(_historico(app)[-1]["depois"]) == {}


# ---------------------------------------------------------------- mover

def _mover(c, rid, corpo):
    return c.post("/api/reservas/%d/mover" % rid, json=corpo)


def test_mover_so_unidade(app, cli):
    r = _criar(cli, diaria_centavos=SEGREDO)
    resp = _mover(cli, r["id"], {"versao": 1, "a": "Chalé A"})
    j = resp.get_json()
    assert resp.status_code == 200 and j["a"] == "Chalé A" and j["i"] == "2026-10-10" and j["versao"] == 2
    assert "diaria_centavos" not in j
    assert cli.get("/api/reservas/%d" % r["id"]).get_json()["diaria_centavos"] == SEGREDO      # diária preservada


def test_mover_so_datas_e_ambos(app, cli):
    r = _criar(cli)
    j = _mover(cli, r["id"], {"versao": 1, "i": "2026-10-11", "f": "2026-10-13"}).get_json()
    assert (j["a"], j["i"], j["f"]) == ("201", "2026-10-11", "2026-10-13")
    j = _mover(cli, r["id"], {"versao": 2, "a": "301", "f": "2026-10-20"}).get_json()
    assert (j["a"], j["i"], j["f"], j["versao"]) == ("301", "2026-10-11", "2026-10-20", 3)


def test_mover_conflito_na_mesma_unidade_e_em_outra(app, cli):
    r = _criar(cli)
    _criar(cli, a="202", nome="Vizinho")
    resp = _mover(cli, r["id"], {"versao": 1, "a": "202"})
    assert resp.status_code == 409 and "Conflito" in resp.get_json()["erro"]
    _criar(cli, nome="Depois", i="2026-10-15", f="2026-10-17")
    assert _mover(cli, r["id"], {"versao": 1, "i": "2026-10-14", "f": "2026-10-16"}).status_code == 409
    j = cli.get("/api/reservas/%d" % r["id"]).get_json()
    assert (j["a"], j["i"], j["f"], j["versao"]) == ("201", "2026-10-10", "2026-10-12", 1)    # nada gravado


def test_mover_saida_e_entrada_no_mesmo_dia_e_permitido(app, cli):
    r = _criar(cli)
    _criar(cli, nome="Seguinte", i="2026-10-12", f="2026-10-14")
    assert _mover(cli, r["id"], {"versao": 1, "i": "2026-10-09", "f": "2026-10-12"}).status_code == 200
    anterior = _criar(cli, a="203", nome="Anterior", i="2026-10-05", f="2026-10-09")
    assert _mover(cli, anterior["id"], {"versao": 1, "a": "201"}).status_code == 200      # sai 9, entra 9


@pytest.mark.parametrize("corpo", [
    {"a": "104"}, {"a": "999"}, {"a": ""}, {"a": None}, {"a": 201}, {"i": "2026-02-30"}, {"i": "20261010"},
    {"i": "２０２６-10-10"}, {"f": "2026-10-10"}, {"f": "2026-10-09"}, {"i": "2019-12-30", "f": "2020-01-02"},
    {"f": "2101-01-01"}, {"f": "2028-10-12"}, {"i": 5}, {"f": ["2026-10-13"]},
])
def test_mover_dados_invalidos_400(app, cli, corpo):
    r = _criar(cli)
    resp = _mover(cli, r["id"], dict(corpo, versao=1))
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert cli.get("/api/reservas/%d" % r["id"]).get_json()["versao"] == 1


def test_mover_versao_velha_e_sem_versao(app, cli):
    r = _criar(cli)
    assert _mover(cli, r["id"], {"versao": 1, "a": "202"}).status_code == 200
    assert _mover(cli, r["id"], {"versao": 1, "a": "203"}).status_code == 409
    assert _mover(cli, r["id"], {"a": "203"}).status_code == 400
    assert _mover(cli, r["id"], {"versao": True, "a": "203"}).status_code == 400
    assert _mover(cli, 9999, {"versao": 1, "a": "203"}).status_code == 404


def test_mover_cancelada_409(app, cli):
    r = _criar(cli)
    cli.delete("/api/reservas/%d" % r["id"], json={"versao": 1, "motivo": "teste"})
    assert _mover(cli, r["id"], {"versao": 2, "a": "202"}).status_code == 409


def test_mover_sem_mudanca_nao_grava_nem_registra(app, cli):
    r = _criar(cli)
    antes = len(_historico(app))
    resp = _mover(cli, r["id"], {"versao": 1, "a": "201", "i": "2026-10-10", "f": "2026-10-12"})
    assert resp.status_code == 200 and resp.get_json()["versao"] == 1
    assert _mover(cli, r["id"], {"versao": 1}).get_json()["versao"] == 1
    assert len(_historico(app)) == antes


def test_mover_registra_historico_sem_valores(app, cli):
    r = _criar(cli, tipo="socio", diaria_centavos=SEGREDO, extras="SEGREDO-EXTRA", o="SEGREDO-OBS")
    _mover(cli, r["id"], {"versao": 1, "a": "202", "f": "2026-10-13"})
    h = _historico(app)[-1]
    assert h["acao"] == "mover" and h["entidade_id"] == r["id"] and h["usuario_login"] == "admin"
    assert json.loads(h["antes"]) == {"a": "201", "f": "2026-10-12"}
    assert json.loads(h["depois"]) == {"a": "202", "f": "2026-10-13"}
    bruto = json.dumps(_historico(app))
    assert str(SEGREDO) not in bruto and "SEGREDO" not in bruto and "Valioso" not in bruto


@pytest.mark.parametrize("papel", PAPEIS)
def test_mover_permissoes_por_papel(app, cli, papel):
    r = _criar(cli)
    c = cli if papel == "admin" else cliente_como(app, papel)
    resp = _mover(c, r["id"], {"versao": 1, "a": "202"})
    if papel in ("admin", "atendente"):
        assert resp.status_code == 200
    else:
        assert resp.status_code == 403
        assert cli.get("/api/reservas/%d" % r["id"]).get_json()["a"] == "201"


def test_mover_exige_csrf_e_login(app, cli):
    r = _criar(cli)
    assert cli.post("/api/reservas/%d/mover" % r["id"], json={"versao": 1, "a": "202"}, sem_csrf=True).status_code in (400, 403)
    assert app.test_client().post("/api/reservas/%d/mover" % r["id"], json={"versao": 1}).status_code in (401, 403)


def test_corrida_de_dois_movimentos_para_o_mesmo_destino(tmp_path):
    app = criar_app_teste(tmp_path)
    admin = cliente_como(app, "admin")
    r1 = _criar(admin, a="201")
    r2 = _criar(admin, a="202")
    barreira = threading.Barrier(2)
    codigos = []

    def mover(rid):
        c = cliente_como(app, "atendente", "at%d" % rid)
        barreira.wait()
        codigos.append(_mover(c, rid, {"versao": 1, "a": "203"}).status_code)

    ts = [threading.Thread(target=mover, args=(x["id"],)) for x in (r1, r2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(codigos) == [200, 409]
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert con.execute("SELECT COUNT(*) FROM reservas WHERE a='203'").fetchone()[0] == 1
    finally:
        con.close()


def test_importadas_ficam_com_tipo_e_diaria_nulos(app, cli):
    assert cli.post("/api/importar").status_code == 201
    lista = cli.get("/api/reservas").get_json()
    assert lista and all(x["tipo"] is None for x in lista)
    assert cli.get("/api/reservas/%d" % lista[0]["id"]).get_json()["diaria_centavos"] is None
