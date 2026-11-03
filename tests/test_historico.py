"""Histórico de auditoria: o que grava, o que nunca grava, e que não se altera."""
import json
import sqlite3

import pytest

from pousada.db import conectar
from pousada.historico import registrar
from tests.conftest import SENHA, cliente_como, inserir_usuario

RESERVA = {"a": "201", "nome": "Fulano Sigiloso", "extras": "SEGREDO-EXTRA 11 98888-7777", "n": 2,
           "i": "2026-10-10", "f": "2026-10-12", "p": "pendente", "o": "SEGREDO-OBS cartão final 1234"}


def linhas(app, where="1=1"):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return [dict(r) for r in con.execute("SELECT * FROM historico WHERE %s ORDER BY id" % where)]
    finally:
        con.close()


def test_criar_e_alterar_gravam_so_a_diferenca(app, cli):
    r = cli.post("/api/reservas", json=RESERVA).get_json()
    cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, a="202", n=3, nome="Outro Nome",
                                                    o="SEGREDO-OBS novo", versao=1))
    criar, alterar = linhas(app, "entidade='reserva'")
    assert criar["acao"] == "criar" and criar["antes"] is None
    assert json.loads(criar["depois"]) == {"a": "201", "i": "2026-10-10", "f": "2026-10-12", "n": 2, "p": "pendente"}
    assert alterar["acao"] == "alterar" and alterar["usuario_login"] == "admin" and alterar["entidade_id"] == r["id"]
    assert json.loads(alterar["antes"]) == {"a": "201", "n": 2}
    assert json.loads(alterar["depois"]) == {"a": "202", "n": 3, "nome": "alterado"}
    assert alterar["ip"] and alterar["em"]


def test_nunca_grava_extras_obs_nome_senha_ou_token(app, cli):
    r = cli.post("/api/reservas", json=RESERVA).get_json()
    cli.put("/api/reservas/%d" % r["id"], json=dict(RESERVA, o="SEGREDO-OBS 2", nome="Nome Novo Sigiloso", versao=1))
    cli.delete("/api/reservas/%d" % r["id"], json={"versao": 2, "motivo": "SEGREDO-MOTIVO"})
    inserir_usuario(app, "atendente", "maria")
    from tests.test_auth import entrar
    entrar(app, "maria", SENHA)
    entrar(app, "maria", "SEGREDO-SENHA-ERRADA")
    tudo = json.dumps(linhas(app), ensure_ascii=False)
    for proibido in ("SEGREDO", "Fulano", "Sigiloso", "Nome Novo", SENHA, "SENHA-ERRADA", "11 98888", "token", "csrf"):
        assert proibido not in tudo, proibido


def test_registrar_descarta_chaves_nao_permitidas(app):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        with app.test_request_context():
            registrar(con, "teste", "x", 1, {"extras": "e", "o": "obs", "senha": "s", "a": "101"},
                      {"token": "t", "p": "pago", "senha_hash": "h"}, ator={"id": None, "login": "t", "ip": "1"})
        r = con.execute("SELECT antes, depois FROM historico").fetchone()
        assert json.loads(r["antes"]) == {"a": "101"} and json.loads(r["depois"]) == {"p": "pago"}
    finally:
        con.close()


def test_historico_nao_pode_ser_alterado_nem_apagado(app, cli):
    cli.post("/api/reservas", json=RESERVA)
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        with pytest.raises(sqlite3.IntegrityError, match="não pode ser alterado"):
            con.execute("UPDATE historico SET acao='x'")
        with pytest.raises(sqlite3.IntegrityError, match="não pode ser apagado"):
            con.execute("DELETE FROM historico")
        assert con.execute("SELECT COUNT(*) FROM historico").fetchone()[0] >= 1
    finally:
        con.close()


def test_historico_e_a_operacao_ficam_juntos_na_mesma_transacao(app, cli, monkeypatch):
    def quebrar(*a, **k):
        raise RuntimeError("falha ao gravar histórico")
    monkeypatch.setattr("pousada.rotas.registrar", quebrar)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    assert cli.post("/api/reservas", json=RESERVA).status_code == 500
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert con.execute("SELECT COUNT(*) FROM reservas").fetchone()[0] == 0     # a reserva foi desfeita junto
    finally:
        con.close()


def test_operacao_recusada_nao_deixa_historico(app, cli):
    cli.post("/api/reservas", json=RESERVA)
    antes = len(linhas(app))
    assert cli.post("/api/reservas", json=RESERVA).status_code == 409
    assert cli.post("/api/reservas", json=dict(RESERVA, n=0)).status_code == 400
    assert len(linhas(app)) == antes


def test_login_ok_e_falha_entram_no_historico(app):
    from tests.test_auth import entrar
    inserir_usuario(app, "atendente", "maria")
    entrar(app, "maria", "errada-errada-1")
    entrar(app, "fantasma", "errada-errada-1")
    entrar(app, "maria", SENHA)
    acoes = [(l["acao"], l["usuario_login"]) for l in linhas(app)]
    assert acoes == [("login_falha", "maria"), ("login_falha", "fantasma"), ("login_ok", "maria")]


def test_rotas_de_leitura_do_historico(app, cli):
    r = cli.post("/api/reservas", json=RESERVA).get_json()
    cli.post("/api/reservas", json=dict(RESERVA, a="202"))
    admin = cli.get("/api/historico").get_json()
    assert len(admin) == 2 and admin[0]["ip"] and admin[0]["depois"]["a"] == "202"      # mais recente primeiro
    dire = cliente_como(cli.application, "diretoria").get("/api/historico").get_json()
    assert set(dire[0]) == {"id", "em", "usuario_login", "acao", "entidade", "entidade_id"}   # resumido: sem antes/depois/ip
    at = cliente_como(cli.application, "atendente")
    assert at.get("/api/historico").status_code == 403
    da_reserva = at.get("/api/reservas/%d/historico" % r["id"]).get_json()
    assert len(da_reserva) == 1 and da_reserva[0]["acao"] == "criar" and "ip" not in da_reserva[0]
    assert cli.get("/api/historico?acao=criar&limite=1").get_json()[0]["acao"] == "criar"
    assert cli.get("/api/historico?limite=abc").status_code == 400


def test_importar_e_desfazer_ficam_no_historico(app, cli):
    from datetime import date
    from tests.test_importacao import corpo_confirmar, planilha_limpa, previa
    app.config["HOJE"] = date(2026, 10, 1)
    j = previa(cli, planilha_limpa()).get_json()
    lote = cli.post("/api/importar/confirmar", json=corpo_confirmar(j)).get_json()["lote_id"]
    por_reserva = linhas(app, "acao='importar' AND entidade='reserva'")
    assert len(por_reserva) == 3 and json.loads(por_reserva[0]["depois"])["lote"] == lote
    lote_reg = linhas(app, "acao='importar' AND entidade='importacao'")[0]
    assert json.loads(lote_reg["depois"])["criadas"] == 3
    cli.post("/api/importar/desfazer/%d" % lote)
    assert len(linhas(app, "acao='desfazer' AND entidade='reserva'")) == 3
    assert json.loads(linhas(app, "acao='desfazer' AND entidade='importacao'")[0]["depois"])["removidas"] == 3


def test_acoes_de_usuarios_entram_no_historico(app, cli):
    cli.post("/api/usuarios", json={"login": "joana", "nome": "J", "senha": "senha-longa-123", "papel": "recepcao"})
    assert [l["acao"] for l in linhas(app, "entidade='usuario'")] == ["usuario_criado"]
    assert "senha-longa" not in json.dumps(linhas(app))
