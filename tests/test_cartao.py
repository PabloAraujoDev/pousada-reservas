"""Detector de número de cartão: função, todos os pontos de entrada de texto, importação e varredura de dados antigos."""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pousada.db import conectar  # noqa: E402
from pousada.regras import MSG_CARTAO, contem_numero_cartao  # noqa: E402
from pousada.varredura_cartoes import executar, varrer  # noqa: E402
from tests.conftest import cliente_como, criar_app_teste  # noqa: E402
from tests.test_importacao import HOJE, OUT, corpo_confirmar, previa  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM = "4111 1111 1111 1111"

RECUSADOS = ["Cartão 4111 1111 1111 1111 val 04/28", "4111-1111-1111-1111", "4111111111111111", "cartao4111111111111111",
             "4000 1234 5678 9010", "4000 1234 5678 9", "4000.1234.5678.9010", "3782 822463 10005",
             "４１１１ １１１１ １１１１ １１１１",
             "4111​1111​1111​1111", "pago 4111111111111111."]
ACEITOS = ["final 1234", "5550 ....", "**** 1234", "xxxx xxxx xxxx 1234", "123.456.789-09", "12345678909", "(11) 98765-4321",
           "11987654321", "1234567890123", "31/10/2026", "2026-10-31 2026-11-02", "Pago no cartão (final 4242)",
           "11 98765-4321 11 98765-4321", "protocolo 20261031123456789012345", "", "Turma 2026"]


@pytest.mark.parametrize("texto", RECUSADOS)
def test_detector_recusa(texto):
    assert contem_numero_cartao(texto) is True


@pytest.mark.parametrize("texto", ACEITOS)
def test_detector_aceita(texto):
    assert contem_numero_cartao(texto) is False


def test_detector_nao_texto():
    assert contem_numero_cartao(None) is False and contem_numero_cartao(4111111111111111) is False


def test_mensagem_nao_repete_numero():
    assert "4111" not in MSG_CARTAO and "cartão" in MSG_CARTAO


@pytest.fixture
def app(tmp_path):
    a = criar_app_teste(tmp_path)
    a.config["HOJE"] = HOJE          # a prévia da importação depende do "hoje"
    return a


def reserva(**campos):
    base = {"a": "201", "nome": "Fulano", "extras": "", "n": 2, "i": "2026-11-10", "f": "2026-11-12", "p": "pendente",
            "o": "", "grupo": ""}
    base.update(campos)
    return base


@pytest.mark.parametrize("campo", ["nome", "grupo", "extras", "o"])
def test_criar_recusa_em_cada_campo(cli, campo):
    r = cli.post("/api/reservas", json=reserva(**{campo: "pago " + NUM}))
    assert r.status_code == 422
    corpo = r.get_data(as_text=True)
    assert "cartão" in r.get_json()["erro"] and "4111" not in corpo and "1111 1111" not in corpo
    assert cli.get("/api/reservas").get_json() == []


def test_editar_recusa_e_nao_grava(cli):
    rid = cli.post("/api/reservas", json=reserva()).get_json()["id"]
    r = cli.put("/api/reservas/%d" % rid, json=dict(reserva(o="cartão 4111111111111111"), versao=1))
    assert r.status_code == 422 and "4111" not in r.get_data(as_text=True)
    assert cli.get("/api/reservas").get_json()[0]["o"] == "" and cli.get("/api/reservas").get_json()[0]["versao"] == 1
    ok = cli.put("/api/reservas/%d" % rid, json=dict(reserva(o="pago no cartão (final 1234)"), versao=1))
    assert ok.status_code == 200


def test_historico_nao_recebe_o_numero(app, cli):
    cli.post("/api/reservas", json=reserva(o="final 1234"))
    cli.post("/api/reservas", json=reserva(a="202", o=NUM))
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        texto = " ".join(str(tuple(l)) for l in con.execute("SELECT * FROM historico").fetchall())
    finally:
        con.close()
    assert "4111" not in texto


def test_recepcao_edita_pagamento_com_texto_antigo_intacto(app, cli):
    """Texto antigo com cartão (nome/extras/grupo) não trava a recepção, que só mexe em pagamento e observações."""
    rid = cli.post("/api/reservas", json=reserva()).get_json()["id"]
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("UPDATE reservas SET extras=? WHERE id=?", (NUM, rid))
    finally:
        con.close()
    rec = cliente_como(app, "recepcao")
    assert rec.put("/api/reservas/%d" % rid, json={"versao": 1, "p": "pago", "o": "ok"}).status_code == 200
    assert rec.put("/api/reservas/%d" % rid, json={"versao": 2, "p": "pago", "o": NUM}).status_code == 422


def test_cancelamento_recusa_cartao_no_motivo(cli):
    rid = cli.post("/api/reservas", json=reserva()).get_json()["id"]
    r = cli.delete("/api/reservas/%d" % rid, json={"versao": 1, "motivo": "reembolso " + NUM})
    assert r.status_code == 422 and "4111" not in r.get_data(as_text=True)
    assert cli.delete("/api/reservas/%d" % rid, json={"versao": 1, "motivo": "desistiu"}).status_code == 200


@pytest.mark.parametrize("acao,campo", [("observacao", "obs"), ("manutencao_abrir", "motivo")])
def test_governanca_recusa_cartao(app, cli, acao, campo):
    r = cli.get("/api/governanca").get_json()
    u = r["unidades"][0]
    corpo = {"acao": acao, "unidades": [{"u": u["u"], "versao": u["versao"]}], campo: "cartão " + NUM}
    resp = cli.post("/api/governanca/acao", json=corpo)
    assert resp.status_code == 422 and "4111" not in resp.get_data(as_text=True)


def test_importacao_planilha_recusa_a_linha_com_aviso(cli):
    plan = {OUT: [(201, "Ana Teste", 2, "10/10 A 12/10", "PAGO " + NUM), None,
                  (202, "Bruno Teste", 3, "11/10 a 14/10", "PAGO - final 1234")]}
    j = previa(cli, plan, abas=[OUT]).get_json()
    por_apto = {l["apto"]: l for l in j["linhas"]}
    assert por_apto["201"]["status"] == "erro" and por_apto["201"]["categoria"] == "cartao"
    assert por_apto["202"]["status"] == "ok", por_apto["202"]["motivo"]
    assert "4111" not in str(j)                       # a prévia não devolve o número
    c = cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    assert c.status_code == 201 and c.get_json()["criadas"] == 1
    assert [r["a"] for r in cli.get("/api/reservas").get_json()] == ["202"]


def test_confirmar_importacao_revalida_e_recusa(cli):
    linha = {"aba": OUT, "linha": 4, "a": "201", "nome": "Ana", "extras": "", "n": 2, "i": "2026-10-10", "f": "2026-10-12",
             "p": "pago", "o": "cartão " + NUM, "grupo": ""}
    c = cli.post("/api/importar/confirmar", json={"arquivo": "t.xlsx", "linhas": [linha], "pedidos": []})
    assert c.status_code in (400, 409, 422) and "4111" not in c.get_data(as_text=True)
    assert cli.get("/api/reservas").get_json() == []


def test_varredura_somente_leitura_sem_numero(app, cli, capsys):
    rid = cli.post("/api/reservas", json=reserva(o="limpo")).get_json()["id"]
    caminho = app.config["CAMINHO_BANCO"]
    con = conectar(caminho)
    try:
        con.execute("UPDATE reservas SET o=?, extras=? WHERE id=?", ("cartao " + NUM, "ok", rid))
        antes = con.execute("SELECT o, versao FROM reservas WHERE id=?", (rid,)).fetchone()
    finally:
        con.close()
    from pousada.varredura_cartoes import abrir_somente_leitura
    ro = abrir_somente_leitura(caminho)
    try:
        assert varrer(ro) == [{"tabela": "reservas", "id": rid, "campo": "o"}]
        with pytest.raises(Exception):
            ro.execute("UPDATE reservas SET o='x'")          # a conexão não grava
    finally:
        ro.close()
    texto = executar(caminho)
    assert "reservas nº %d" % rid in texto and "'o'" in texto and "4111" not in texto
    con = conectar(caminho)
    try:
        assert tuple(con.execute("SELECT o, versao FROM reservas WHERE id=?", (rid,)).fetchone()) == tuple(antes)
    finally:
        con.close()


def test_varredura_banco_limpo(app):
    assert executar(app.config["CAMINHO_BANCO"]) == "Nenhum número de cartão encontrado."


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_aviso_do_navegador_no_node():
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", "cartao_logica.js")], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
