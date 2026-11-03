"""Notas: migração com dados, triggers, permissões nos 6 papéis, janela do autor, privacidade, atomicidade e concorrência."""
import json
import os
import sqlite3
import threading
from datetime import datetime

import pytest

from pousada.db import conectar, iniciar_banco
from tests.conftest import cliente_como, criar_app_teste
from tests.test_notas import AGORA, anotar, cli, listar, nova_reserva, sql

PAPEIS = ["admin", "atendente", "recepcao", "diretoria", "consulta", "camareira"]
PASTA_REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
MARCADOR = "MarcadorSecretoXyz"


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def test_migracao_013_sobre_banco_da_versao_12_com_dados(tmp_path):
    pasta = tmp_path / "mig"
    pasta.mkdir()
    for f in os.listdir(PASTA_REAL):
        if int(f.split("_")[0]) <= 12:
            (pasta / f).write_bytes(open(os.path.join(PASTA_REAL, f), "rb").read())
    banco = str(tmp_path / "b.db")
    iniciar_banco(banco, str(pasta))
    con = conectar(banco)
    con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao) "
                "VALUES ('201','Ana','',1,'2026-10-27','2026-10-30','pago','Observação antiga','','x','x',1)")
    con.close()
    iniciar_banco(banco, PASTA_REAL, pasta_backup=str(tmp_path / "bk"))
    con = conectar(banco)
    try:
        assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 13
        assert con.execute("SELECT o FROM reservas").fetchone()[0] == "Observação antiga"      # o campo "o" segue intacto
        con.execute("INSERT INTO nota (escopo,reserva_id,tipo,texto,em) VALUES ('reserva',1,'nota','oi','x')")
    finally:
        con.close()


def inserir(app, **c):
    base = dict(escopo="reserva", reserva_id=1, unidade=None, tipo="nota", nota_ref=None, texto="oi", motivo="", em="x")
    base.update(c)
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("INSERT INTO nota (%s) VALUES (%s)" % (",".join(base), ",".join("?" * len(base))), list(base.values()))
    finally:
        con.close()


def test_triggers_log_imutavel_e_regras_do_banco(app):
    nova_reserva(app)
    inserir(app)
    con = conectar(app.config["CAMINHO_BANCO"])
    for comando in ("UPDATE nota SET texto='x' WHERE id=1", "DELETE FROM nota WHERE id=1"):
        with pytest.raises(sqlite3.IntegrityError, match="não pode ser"):
            con.execute(comando)
    con.close()
    ruins = [dict(reserva_id=99), dict(texto=""), dict(texto="x" * 301), dict(escopo="unidade"),
             dict(escopo="unidade", reserva_id=None, unidade="201", tipo="correcao", nota_ref=1),       # escopo diferente da nota
             dict(tipo="correcao", nota_ref=None), dict(tipo="ocultar", nota_ref=1, texto="", motivo=""),
             dict(tipo="ocultar", nota_ref=77, texto="", motivo="abc")]
    for r in ruins:
        with pytest.raises(sqlite3.IntegrityError):
            inserir(app, **r)
    inserir(app, tipo="ocultar", nota_ref=1, texto="", motivo="abc")
    for r in (dict(tipo="ocultar", nota_ref=1, texto="", motivo="abc"), dict(tipo="correcao", nota_ref=1, texto="novo")):
        with pytest.raises(sqlite3.IntegrityError):
            inserir(app, **r)                         # nota oculta não muda mais


def test_reserva_com_nota_nao_pode_ser_excluida(app):
    rid = nova_reserva(app)["id"]
    anotar(cli(app, "atendente"), rid)
    r = cli(app, "admin").post("/api/reservas/%d/excluir-definitivo" % rid, json={"versao": 1})
    assert r.status_code == 409 and "notas" in r.get_json()["erro"]
    con = conectar(app.config["CAMINHO_BANCO"])
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM reservas WHERE id=?", (rid,))
    con.close()


@pytest.mark.parametrize("papel,le,escreve_reserva,escreve_unidade", [
    ("admin", True, True, True), ("atendente", True, True, True), ("recepcao", True, True, False),
    ("diretoria", True, False, False), ("consulta", True, False, False), ("camareira", False, False, False)])
def test_permissoes_nos_seis_papeis(app, papel, le, escreve_reserva, escreve_unidade):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "admin"), rid).get_json()["id"]
    c = cli(app, papel)
    assert (listar(c, rid).status_code == 200) is le
    assert (anotar(c, rid, "outra").status_code == 201) is escreve_reserva
    u = c.post("/api/unidades/201/notas", json={"texto": "Ar barulhento"})
    assert (u.status_code == 201) is escreve_unidade
    assert c.get("/api/unidades/201/notas").status_code == 200        # todos leem a nota do apartamento (camareira saneada)
    mexe = c.post("/api/notas/%d/corrigir" % nid, json={"texto": "mudou", "versao": 1}).status_code
    assert (mexe == 200) is (papel in ("admin", "atendente"))        # recepção não é autora e não edita reservas
    if papel not in ("admin", "atendente"):
        assert mexe == 403


def test_autor_corrige_na_janela_de_24h_e_depois_so_quem_edita(app):
    rid = nova_reserva(app)["id"]
    rec = cli(app, "recepcao")
    nid = anotar(rec, rid).get_json()["id"]
    app.config["AGORA"] = datetime(2026, 10, 30, 8, 59, 0)
    assert listar(rec, rid).get_json()["notas"][0]["pode_corrigir"] is True
    app.config["AGORA"] = datetime(2026, 10, 30, 9, 1, 0)
    n = listar(rec, rid).get_json()["notas"][0]
    assert not n["pode_corrigir"] and not n["pode_ocultar"]
    assert rec.post("/api/notas/%d/corrigir" % nid, json={"texto": "x", "versao": 1}).status_code == 403
    assert listar(cli(app, "atendente"), rid).get_json()["notas"][0]["pode_corrigir"] is True
    assert cli(app, "atendente").post("/api/notas/%d/corrigir" % nid, json={"texto": "x", "versao": 1}).status_code == 200


def test_outra_recepcionista_nao_mexe_na_nota_alheia(app):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "recepcao", "rec1"), rid).get_json()["id"]
    assert cli(app, "recepcao", "rec2").post("/api/notas/%d/ocultar" % nid, json={"motivo": "abc", "versao": 1}).status_code == 403


def test_camareira_ve_so_a_nota_do_apartamento_saneada_e_sem_autor(app):
    nova_reserva(app)
    adm = cli(app, "admin")
    assert adm.post("/api/unidades/201/notas", json={"texto": "Ar-condicionado barulhento - telefone 31 99999 8888"}).status_code == 201
    assert adm.post("/api/unidades/201/notas", json={"texto": "Pago via PIX"}).status_code == 201
    g = cli(app, "camareira").get("/api/unidades/201/notas").get_json()
    assert [n["texto"] for n in g["notas"]] == ["Ar-condicionado barulhento"] and g["pode_escrever"] is False
    assert set(g["notas"][0]) == {"id", "texto", "em"}
    assert "99999" not in json.dumps(g) and "PIX" not in json.dumps(g)


def test_privacidade_texto_marcador_so_nas_rotas_de_notas(app):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "atendente"), rid, MARCADOR).get_json()["id"]
    cli(app, "atendente").post("/api/notas/%d/corrigir" % nid, json={"texto": MARCADOR + " 2", "versao": 1})
    cli(app, "atendente").post("/api/unidades/201/notas", json={"texto": MARCADOR + " apto"})
    caminhos = ["/api/reservas", "/api/reservas/%d" % rid, "/api/reservas/%d/historico" % rid, "/api/historico",
                "/api/export.csv", "/api/camareiras?nomes=1", "/api/governanca", "/api/reservas/%d/despesas" % rid,
                "/api/export.csv?inicio=2026-10-27&dias=7"]
    for papel in PAPEIS:
        for url in caminhos:
            corpo = cli(app, papel).get(url).get_data(as_text=True)
            assert MARCADOR not in corpo, (papel, url)
    assert MARCADOR not in "".join(l[0] or "" for l in sql(app, "SELECT COALESCE(antes,'')||COALESCE(depois,'') FROM historico"))
    nomes = [l[0] for l in sql(app, "SELECT acao FROM historico WHERE acao LIKE 'nota_%' ORDER BY id")]
    assert nomes == ["nota_adicionada", "nota_corrigida", "nota_adicionada"]
    assert cli(app, "camareira").get("/api/reservas/%d/notas" % rid).status_code == 403


def test_historico_da_reserva_nao_ganha_texto_da_nota(app):
    rid = nova_reserva(app)["id"]
    anotar(cli(app, "atendente"), rid, MARCADOR)
    h = cli(app, "admin").get("/api/reservas/%d/historico" % rid).get_data(as_text=True)
    assert "nota_adicionada" in h and MARCADOR not in h


def test_atomicidade_se_o_historico_falha_nao_fica_nota(app, monkeypatch):
    rid = nova_reserva(app)["id"]
    from pousada import rotas_notas

    def quebra(*a, **k):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(rotas_notas, "registrar", quebra)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    assert anotar(cli(app, "atendente"), rid).status_code == 500
    assert sql(app, "SELECT COUNT(*) FROM nota")[0][0] == 0


def test_concorrencia_duas_correcoes_com_a_mesma_versao_so_uma_passa(app):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "atendente"), rid).get_json()["id"]
    resultados, trava = [], threading.Barrier(2)

    def corrige(texto):
        c = cliente_como(app, "atendente", "u" + texto)
        trava.wait()
        resultados.append(c.post("/api/notas/%d/corrigir" % nid, json={"texto": texto, "versao": 1}).status_code)
    ts = [threading.Thread(target=corrige, args=(t,)) for t in ("aaa", "bbb")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(resultados) == [200, 409]
    assert sql(app, "SELECT COUNT(*) FROM nota WHERE tipo='correcao'")[0][0] == 1


def test_concorrencia_ocultar_duas_vezes_e_limite(app):
    rid = nova_reserva(app)["id"]
    nid = anotar(cli(app, "atendente"), rid).get_json()["id"]
    r1 = cli(app, "atendente").post("/api/notas/%d/ocultar" % nid, json={"motivo": "abc", "versao": 1})
    r2 = cli(app, "admin").post("/api/notas/%d/ocultar" % nid, json={"motivo": "abc", "versao": 1})
    assert (r1.status_code, r2.status_code) == (200, 409)


def test_desfazer_importacao_com_nota_409_e_a_reserva_continua(app):
    rid = nova_reserva(app)["id"]
    con = conectar(app.config["CAMINHO_BANCO"])
    lote = con.execute("INSERT INTO importacoes (arquivo, criado) VALUES ('t.xlsx', 'x')").lastrowid
    con.execute("UPDATE reservas SET lote_id=? WHERE id=?", (lote, rid))
    con.close()
    anotar(cli(app, "atendente"), rid)
    r = cli(app, "admin").post("/api/importar/desfazer/%d" % lote)
    assert r.status_code == 409 and "notas" in r.get_json()["erro"]
    assert cli(app, "admin").get("/api/reservas/%d" % rid).status_code == 200


def test_rotas_de_notas_exigem_login_e_csrf(app):
    rid = nova_reserva(app)["id"]
    anonimo = app.test_client()
    assert anonimo.get("/api/reservas/%d/notas" % rid).status_code in (401, 302)
    c = cli(app, "atendente")
    assert c.post("/api/reservas/%d/notas" % rid, json={"texto": "x"}, sem_csrf=True).status_code == 403
    assert c.post("/api/reservas/%d/notas" % rid, json={"texto": "x"}, headers={"Origin": "https://mal.example"}).status_code == 403
    assert sql(app, "SELECT COUNT(*) FROM nota")[0][0] == 0
