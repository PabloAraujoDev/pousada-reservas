"""Revalidação no servidor, bloqueios, concorrência, permissões, desfazer e privacidade da importação com cancelamentos."""
import json

import pytest

from tests.apoio_importacao_cancel import CAB, NOV, corpo, ids, importar_base, previa, sql
from tests.conftest import cliente_como
from tests.test_importacao import app  # noqa: F401

SO_ANA = {NOV: [(202, "Bruno Teste", 3, "10/11 A 12/11", ""), None, ("CHALE A", "Carla Teste", 4, "15/11 A 18/11", ""),
                None, (201, "Novo Hospede", 2, "05/11 A 07/11", ""), None, CAB, ("201", "Ana Teste - 05 A 07/11")]}


def cancela_um(rid, versao=1, origem="planilha"):
    return {"arquivo": "t.xlsx", "linhas": [], "pedidos": [], "cancelamentos": [{"id": rid, "versao": versao, "origem": origem,
                                                                                  "aba": NOV, "linha": 9}]}


def estado(app):
    return sql(app, "SELECT id, status, versao FROM reservas ORDER BY id")


def test_checkin_feito_bloqueia_na_previa_e_no_servidor_tudo_ou_nada(app, cli):
    importar_base(cli)
    rid = ids(cli)[("201", "Ana Teste")]
    from pousada.db import conectar
    con = conectar(app.config["CAMINHO_BANCO"])
    con.execute("UPDATE reservas SET checkin_em='2026-11-05 14:00' WHERE id=?", (rid,))
    con.close()
    j = previa(cli, SO_ANA, abas=[NOV]).get_json()
    p = [x for x in j["cancelamentos"]["propostas"] if x["id"] == rid][0]
    assert "check-in" in p["bloqueio"] and not p["marcada"] and j["contadores"]["cancel_bloqueadas"] == 1
    antes = estado(app)
    forcado = corpo(j)
    forcado["cancelamentos"] = [{"id": rid, "versao": p["versao"], "origem": "planilha", "aba": NOV, "linha": 9}]
    r = cli.post("/api/importar/confirmar", json=forcado)
    assert r.status_code == 409 and "check-in" in json.dumps(r.get_json(), ensure_ascii=False)
    assert estado(app) == antes


def test_conta_com_despesa_ou_pagamento_bloqueia(app, cli):
    importar_base(cli)
    rid = ids(cli)[("201", "Ana Teste")]
    from pousada.db import conectar
    con = conectar(app.config["CAMINHO_BANCO"])
    con.execute("UPDATE reservas SET conta_aberta_em='2026-11-05 10:00' WHERE id=?", (rid,))
    con.close()
    r = cli.post("/api/importar/confirmar", json=cancela_um(rid, 1))
    assert r.status_code == 409 and estado(app)[0][1] == "ativa"


def test_versao_antiga_reserva_ja_cancelada_inexistente_e_sumiu_manual(app, cli):
    importar_base(cli)
    ana = ids(cli)[("201", "Ana Teste")]
    manual = cli.post("/api/reservas", json={"a": "203", "nome": "Manual Teste", "n": 2, "i": "2026-11-05", "f": "2026-11-07", "p": "pendente"}).get_json()["id"]
    antes = estado(app)
    assert cli.post("/api/importar/confirmar", json=cancela_um(ana, 99)).status_code == 409          # alterada por outra pessoa
    assert cli.post("/api/importar/confirmar", json=cancela_um(9999)).status_code == 409             # não existe
    assert cli.post("/api/importar/confirmar", json=cancela_um(manual, 1, "sumiu")).status_code == 409   # manual: nunca por ausência
    assert estado(app) == antes
    assert cli.post("/api/importar/confirmar", json=cancela_um(ana, 1)).status_code == 201
    r = cli.post("/api/importar/confirmar", json=cancela_um(ana, 2))
    assert r.status_code == 409 and "não está ativa" in json.dumps(r.get_json(), ensure_ascii=False)


def test_editada_depois_da_previa_e_recusada_e_nada_e_gravado(app, cli):
    importar_base(cli)
    j = previa(cli, SO_ANA, abas=[NOV]).get_json()
    ana = ids(cli)[("201", "Ana Teste")]
    assert cli.put("/api/reservas/%d" % ana, json={"a": "201", "nome": "Ana Teste", "n": 3, "i": "2026-11-05", "f": "2026-11-07",
                                                      "p": "pago", "versao": 1}).status_code == 200
    r = cli.post("/api/importar/confirmar", json=corpo(j))
    assert r.status_code == 409 and "por outra pessoa" in json.dumps(r.get_json(), ensure_ascii=False)
    assert len(cli.get("/api/reservas").get_json()) == 3                   # a nova também não entrou


@pytest.mark.parametrize("papel", ["recepcao", "atendente", "consulta", "diretoria"])
def test_so_admin_cancela_pela_importacao(app, cli, papel):
    importar_base(cli)
    outro = cliente_como(app, papel)
    assert outro.post("/api/importar/confirmar", json=cancela_um(ids(cli)[("201", "Ana Teste")])).status_code == 403
    assert estado(app)[0][1] == "ativa"


def test_limites_e_dados_invalidos(cli):
    importar_base(cli)
    muitos = cancela_um(1)
    muitos["cancelamentos"] = muitos["cancelamentos"] * 501
    assert cli.post("/api/importar/confirmar", json=muitos).status_code == 400
    for ruim in ("x", {"a": 1}, [None], [{"id": "1", "versao": 1}], [{"id": True, "versao": 1}]):
        c = cancela_um(1)
        c["cancelamentos"] = ruim
        assert cli.post("/api/importar/confirmar", json=c).status_code in (400, 409)
    c = cancela_um(1)
    c["atualizacoes"] = [{"id": 1, "versao": 1, "nome": "Outro Nome Total", "n": 2, "i": "2027-01-01", "f": "2027-01-03", "p": "pago"}]
    assert cli.post("/api/importar/confirmar", json=c).status_code == 409        # não corresponde à reserva do sistema


def test_desfazer_reativa_restaura_e_respeita_o_que_foi_mexido_depois(app, cli):
    lote0 = importar_base(cli)
    ana, bruno = ids(cli)[("201", "Ana Teste")], ids(cli)[("202", "Bruno Teste")]
    j = previa(cli, {NOV: [(202, "BRUNO TESTE", 5, "10/11 A 12/11", "PAGO"), None, (201, "Novo Hospede", 2, "05/11 A 07/11", ""),
                           None, CAB, ("201", "Ana Teste - 05 A 07/11"), ("CHALE A", "Carla Teste - 15 A 18/11")]}, abas=[NOV]).get_json()
    r = cli.post("/api/importar/confirmar", json=corpo(j)).get_json()
    assert (r["canceladas"], r["atualizadas"], r["criadas"]) == (2, 1, 1)
    carla = ids_todas(app)["Carla Teste"]
    # alguém mexe na Carla depois da importação: o desfazer não a reativa
    from pousada.db import conectar
    con = conectar(app.config["CAMINHO_BANCO"])
    con.execute("UPDATE reservas SET versao=versao+1 WHERE id=?", (carla,))
    con.close()
    d = cli.post("/api/importar/desfazer/%d" % r["lote_id"]).get_json()
    assert (d["removidas"], d["revertidas"], d["nao_revertidas"]) == (1, 2, 1)
    est = {x[0]: x[1] for x in sql(app, "SELECT id, status FROM reservas")}
    assert est[ana] == "ativa" and est[carla] == "cancelada"
    assert sql(app, "SELECT n FROM reservas WHERE id=?", (bruno,)) == [(3,)]
    assert sql(app, "SELECT COUNT(*) FROM importacao_alteracao")[0][0] == 0
    assert lote0 != r["lote_id"]


def ids_todas(app):
    return {n: i for i, n in sql(app, "SELECT id, nome FROM reservas")}


def test_privacidade_historico_e_motivo_sem_nomes_e_cartao_nao_repetido(app, cli):
    importar_base(cli)
    j = previa(cli, {NOV: [(202, "Bruno Teste", 3, "10/11 A 12/11", ""), None, CAB, ("201", "Ana Teste - 05 A 07/11"),
                           ("305", "Fulano 4111 1111 1111 1111 - 05 A 07/11")]}, abas=[NOV]).get_json()
    assert "4111" not in json.dumps(j) and [x["texto"] for x in j["cancelamentos"]["nao_identificadas"]] == [""]
    assert cli.post("/api/importar/confirmar", json=corpo(j)).status_code == 201
    textos = json.dumps(sql(app, "SELECT antes, depois FROM historico WHERE acao='cancelar'")) + \
        json.dumps(sql(app, "SELECT motivo_cancelamento FROM reservas WHERE status='cancelada'"))
    assert "Ana" not in textos and "Teste" not in textos


def test_xss_na_linha_de_cancelamento_vai_como_texto_json(cli):
    importar_base(cli)
    j = previa(cli, {NOV: [(202, "Bruno Teste", 3, "10/11 A 12/11", ""), None, CAB, ("203", '<img src=x onerror=alert(1)> - 05 A 07/11')]},
               abas=[NOV]).get_json()
    assert j["cancelamentos"]["nao_encontradas"][0]["hospede"].startswith("<IMG")      # o cliente exibe sempre com esc()


def test_despesa_lancada_bloqueia_cancelamento_e_atualizacao(app, cli):
    importar_base(cli)
    ana = ids(cli)[("201", "Ana Teste")]
    r = cli.post("/api/reservas/%d/despesas" % ana, json={"categoria": "bar", "descricao": "Água", "quantidade": 1,
                                                          "valor_unit_centavos": 800, "chave": "k-importacao-1"})
    assert r.status_code in (200, 201), r.get_json()
    j = previa(cli, SO_ANA, abas=[NOV]).get_json()
    assert "despesas" in [x for x in j["cancelamentos"]["propostas"] if x["id"] == ana][0]["bloqueio"]
    j2 = previa(cli, {NOV: [(201, "Ana Teste", 9, "05/11 A 07/11", "PAGO")]}, abas=[NOV]).get_json()
    assert j2["linhas"][0]["status"] == "ignorada" and j2["linhas"][0]["categoria"] == "atualizacao_bloqueada"
