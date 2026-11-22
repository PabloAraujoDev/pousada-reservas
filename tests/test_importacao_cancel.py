"""Importação que também cancela e atualiza reservas do sistema (prévia, casamento, mesma confirmação)."""
from tests.apoio_importacao_cancel import CAB, NOV, corpo, ids, importar_base, previa, sql
from tests.test_importacao import app  # noqa: F401  (fixture com HOJE fixo)


def nova(cancelamentos, grade=()):
    return {NOV: list(grade) + [None, CAB] + list(cancelamentos)}


def props(j):
    return {(p["apto"], p["nome"]): p for p in j["cancelamentos"]["propostas"]}


def test_alta_media_nao_encontrada_e_nao_identificada(cli):
    importar_base(cli)
    j = previa(cli, nova([("201", "CEL ANA TESTE - 05 A 07/11 - CANCELOU"), ("202", "Beltrano Outro - 10 A 12/11"),
                          ("203", "Fulano Qualquer - 05 A 07/11"), ("CHALE Z", "X - 05 A 07/11"), (None, "texto solto")],
                         grade=[("CHALE A", "Carla Teste", 4, "15/11 A 18/11", "")]), abas=[NOV]).get_json()
    p = props(j)
    assert p[("201", "Ana Teste")]["confianca"] == "alta" and p[("201", "Ana Teste")]["marcada"]
    assert p[("202", "Bruno Teste")]["confianca"] == "media" and not p[("202", "Bruno Teste")]["marcada"]
    assert [n["unidade"] for n in j["cancelamentos"]["nao_encontradas"]] == ["203"]
    assert len(j["cancelamentos"]["nao_identificadas"]) == 2
    c = j["contadores"]
    assert (c["cancelamentos"], c["cancel_alta"], c["cancel_media"], c["cancel_nao_encontradas"], c["cancel_nao_identificadas"]) == (5, 1, 1, 1, 2)
    assert len(cli.get("/api/reservas").get_json()) == 3         # prévia não grava


def test_cancelamento_libera_unidade_para_a_nova_reserva_na_mesma_confirmacao(app, cli):
    importar_base(cli)
    grade = [(201, "Novo Hospede", 2, "05/11 A 07/11", ""), None, (202, "Bruno Teste", 3, "10/11 A 12/11", ""), None,
             ("CHALE A", "Carla Teste", 4, "15/11 A 18/11", "")]
    j = previa(cli, nova([("201", "Ana Teste - 05 A 07/11 - CANCELOU")], grade), abas=[NOV]).get_json()
    nova_l = [l for l in j["linhas"] if l["hospede"] == "Novo Hospede"][0]
    assert nova_l["status"] == "aviso" and nova_l["depende_de"] == [ids(cli)[("201", "Ana Teste")]]
    r = cli.post("/api/importar/confirmar", json=corpo(j))
    assert r.status_code == 201 and (r.get_json()["canceladas"], r.get_json()["criadas"]) == (1, 1)
    ativas = {(x["a"], x["nome"]) for x in cli.get("/api/reservas").get_json()}
    assert ("201", "Novo Hospede") in ativas and ("201", "Ana Teste") not in ativas
    canc = cli.get("/api/reservas?canceladas=1").get_json()[0]
    assert canc["motivo_cancelamento"].startswith("Cancelada conforme planilha importada (aba ") and canc["cancelado_por"] == "admin"
    assert sql(app, "SELECT COUNT(*) FROM historico WHERE acao='cancelar'")[0][0] == 1


def test_sem_marcar_o_cancelamento_a_nova_vira_conflito_no_servidor(cli):
    importar_base(cli)
    j = previa(cli, nova([("201", "Ana Teste - 05 A 07/11")], [(201, "Novo Hospede", 2, "05/11 A 07/11", "")]), abas=[NOV]).get_json()
    c = corpo(j)
    c["cancelamentos"] = []
    r = cli.post("/api/importar/confirmar", json=c)
    assert r.status_code == 409 and len(cli.get("/api/reservas").get_json()) == 3


def test_sumiu_da_planilha_vem_marcada_e_so_para_reservas_importadas(cli):
    importar_base(cli)
    manual = cli.post("/api/reservas", json={"a": "203", "nome": "Manual Teste", "n": 2, "i": "2026-11-05", "f": "2026-11-07", "p": "pendente"})
    assert manual.status_code == 201
    j = previa(cli, {NOV: [(201, "Ana Teste", 2, "05/11 A 07/11", "PAGO")]}, abas=[NOV]).get_json()
    p = props(j)
    assert set(p) == {("202", "Bruno Teste"), ("Chalé A", "Carla Teste")}
    assert all(x["origem"] == "sumiu" and x["marcada"] for x in p.values())
    r = cli.post("/api/importar/confirmar", json=corpo(j))
    assert r.status_code == 201 and r.get_json()["canceladas"] == 2
    assert {x["a"] for x in cli.get("/api/reservas").get_json()} == {"201", "203"}


def test_aba_sem_reservas_lidas_nao_gera_sumiu(cli):
    importar_base(cli)
    j = previa(cli, {NOV: [None, CAB, ("201", "Ana Teste - 05 A 07/11")]}, abas=[NOV]).get_json()
    assert [p["origem"] for p in j["cancelamentos"]["propostas"]] == ["planilha"]
    assert j["contadores"]["cancel_sumiu"] == 0


def test_atualizacao_campo_a_campo_preserva_o_que_a_planilha_nao_tem(app, cli):
    importar_base(cli)
    rid = ids(cli)[("202", "Bruno Teste")]
    from pousada.db import conectar
    con = conectar(app.config["CAMINHO_BANCO"])
    con.execute("UPDATE reservas SET diaria_centavos=12345, placa='ABC1234' WHERE id=?", (rid,))
    con.close()
    j = previa(cli, {NOV: [(201, "Ana Teste", 2, "05/11 A 07/11", "PAGO"), None, (202, "BRUNO TESTE", 5, "10/11 A 13/11", "PAGO"),
                           None, ("CHALE A", "Carla Teste", 4, "15/11 A 18/11", "")]}, abas=[NOV]).get_json()
    up = [l for l in j["linhas"] if l["status"] == "atualizacao"]
    assert len(up) == 1 and j["contadores"]["atualizacoes"] == 1
    assert {d["campo"] for d in up[0]["atualizacao"]["diferencas"]} == {"n", "f", "p", "o"}
    r = cli.post("/api/importar/confirmar", json=corpo(j))
    assert r.status_code == 201 and r.get_json()["atualizadas"] == 1 and r.get_json()["criadas"] == 0
    novo = cli.get("/api/reservas/%d" % rid).get_json()
    assert (novo["n"], novo["f"], novo["versao"]) == (5, "2026-11-13", 2)
    assert sql(app, "SELECT diaria_centavos, placa FROM reservas WHERE id=?", (rid,)) == [(12345, "ABC1234")]
    h = sql(app, "SELECT acao, antes, depois FROM historico WHERE entidade_id=? AND acao='alterar'", (rid,))
    assert len(h) == 1 and '"n": 3' in h[0][1] and '"n": 5' in h[0][2]
    j2 = previa(cli, {NOV: [(202, "BRUNO TESTE", 5, "10/11 A 13/11", "PAGO")]}, abas=[NOV]).get_json()
    assert [l["categoria"] for l in j2["linhas"]] == ["ja_importada"]


def test_atualizacao_de_reserva_manual_vale_mas_nao_vira_importada(app, cli):
    r = cli.post("/api/reservas", json={"a": "203", "nome": "Manual Teste", "n": 2, "i": "2026-11-05", "f": "2026-11-07", "p": "pendente"})
    j = previa(cli, {NOV: [(203, "Manual Teste", 4, "05/11 A 07/11", "")]}, abas=[NOV]).get_json()
    assert j["contadores"]["atualizacoes"] == 1
    assert cli.post("/api/importar/confirmar", json=corpo(j)).status_code == 201
    assert sql(app, "SELECT n, lote_id, chave_import FROM reservas WHERE id=?", (r.get_json()["id"],)) == [(4, None, None)]
