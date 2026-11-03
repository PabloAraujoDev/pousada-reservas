"""Transferência de despesas/diária entre hospedagens, zerar a diária, fechar/reabrir a conta e a lista de lançamentos (etapa 3B)."""
from tests.apoio_pagamentos import app, cli, conta, detalhe, lancar, nova, receber, sql, totais  # noqa: F401


def transferir(app, rid, destino, itens, papel="admin", **extra):
    corpo = {"destino_id": destino, "itens": itens, "chave": "tr-%d-%d-%s" % (rid, destino, "".join(itens)),
             "conta_versao": conta(app, rid)["conta"]["versao"]}
    corpo.update(extra)
    return cli(app, papel).post("/api/reservas/%d/transferir" % rid, json=corpo)


def par(app):
    return nova(app), nova(app, a="202", nome="João Souza")


def test_transfere_despesa_estorno_na_origem_e_lancamento_no_destino(app):
    a, b = par(app)
    l1, l2 = lancar(app, a, 800, 2)["id"], lancar(app, a, 500)["id"]
    r = transferir(app, a, b, ["d%d" % l1])
    assert r.status_code == 201 and r.get_json()["total_centavos"] == 1600
    assert totais(app, a)["despesas_centavos"] == 500 and totais(app, b)["despesas_centavos"] == 1600
    origem = [i for i in conta(app, a)["itens"] if i["tipo"] == "estorno"][0]
    assert origem["motivo"] == "Transferido para #%d (apto 202)" % b and origem["estorno_de"] == l1
    destino = conta(app, b)["itens"][0]
    assert destino["descricao"] == "Água 500ml" and destino["total_centavos"] == 1600
    t = sql(app, "SELECT id FROM transferencia")[0][0]
    assert sql(app, "SELECT COUNT(*) FROM despesa_lancamento WHERE transferencia_id=?", (t,)) == [(2,)]
    assert l2


def test_transfere_a_diaria_inteira_zera_a_origem_e_cria_lancamento_no_destino(app):
    a, b = par(app)
    r = transferir(app, a, b, ["diaria"])
    assert r.status_code == 201 and r.get_json()["com_diaria"] and r.get_json()["total_centavos"] == 90000
    assert detalhe(app, a)["diaria_centavos"] == 0 and totais(app, a)["conta_centavos"] == 0
    d = conta(app, b)["itens"][0]
    assert d["categoria"] == "outros" and d["quantidade"] == 3 and d["valor_unit_centavos"] == 30000 and "#%d" % a in d["descricao"]
    assert totais(app, b)["conta_centavos"] == 90000 + 90000
    ev = sql(app, "SELECT acao, motivo, valor_centavos, noites FROM conta_evento")
    assert ev == [("diaria_zerar", "Transferido para #%d (apto 202)" % b, 90000, 3)]
    assert transferir(app, a, b, ["diaria"], chave="outra-chave-1").status_code == 409          # já foi zerada


def test_nao_transfere_para_a_mesma_reserva_nem_para_destino_invalido(app):
    a, b = par(app)
    lid = lancar(app, a)["id"]
    assert transferir(app, a, a, ["d%d" % lid]).status_code == 422
    assert transferir(app, a, 9999, ["d%d" % lid]).status_code == 422
    cli(app, "admin").delete("/api/reservas/%d" % b, json={"versao": detalhe(app, b)["versao"], "motivo": "Cancelada pelo hóspede"})
    assert transferir(app, a, b, ["d%d" % lid]).status_code == 422                               # cancelada
    futura = nova(app, a="203", i="2026-11-05", f="2026-11-07")
    assert transferir(app, a, futura, ["d%d" % lid]).status_code == 422                         # ainda não começou
    encerrada = nova(app, a="204", i="2026-10-20", f="2026-10-25")
    assert transferir(app, a, encerrada, ["d%d" % lid]).status_code == 422


def test_destino_liberado_com_conta_aberta_vale(app):
    a, b = par(app)
    enc = nova(app, a="204", i="2026-10-20", f="2026-10-25")
    cli(app, "admin").post("/api/reservas/%d/liberar" % enc, json={"versao": detalhe(app, enc)["versao"], "motivo": "Saiu sem acertar a conta"})
    lid = lancar(app, a)["id"]
    assert transferir(app, a, enc, ["d%d" % lid]).status_code == 201


def test_item_ja_estornado_ou_de_outra_reserva_e_recusado(app):
    a, b = par(app)
    l1 = lancar(app, a)["id"]
    lb = lancar(app, b)["id"]
    assert transferir(app, a, b, ["d%d" % lb]).status_code == 422
    assert cli(app, "admin").post("/api/despesas/%d/estorno" % l1, json={"motivo": "Lançado errado"}).status_code == 201
    assert transferir(app, a, b, ["d%d" % l1]).status_code == 409
    assert transferir(app, a, b, []).status_code == 422
    assert transferir(app, a, b, ["x1"]).status_code == 400


def test_transferencia_idempotente_pela_chave(app):
    a, b = par(app)
    lid = lancar(app, a)["id"]
    c = {"destino_id": b, "itens": ["d%d" % lid], "chave": "chave-unica-1", "conta_versao": conta(app, a)["conta"]["versao"]}
    r1 = cli(app, "admin").post("/api/reservas/%d/transferir" % a, json=c)
    r2 = cli(app, "admin").post("/api/reservas/%d/transferir" % a, json=c)
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.get_json()["id"] == r2.get_json()["id"]
    assert sql(app, "SELECT COUNT(*) FROM transferencia") == [(1,)]


def test_nao_transfere_deixando_o_total_abaixo_do_pago(app):
    a, b = par(app)
    assert receber(app, a, 80000).status_code == 201
    assert transferir(app, a, b, ["diaria"]).status_code == 409
    assert cli(app, "admin").post("/api/reservas/%d/diaria/zerar" % a, json={
        "versao": detalhe(app, a)["versao"], "motivo": "Diária cobrada errada", "chave": "zerar-chave-1"}).status_code == 409


def test_zerar_a_diaria_com_motivo_e_historico_sem_valores(app):
    a = nova(app)
    corpo = {"versao": detalhe(app, a)["versao"], "motivo": "Hóspede não dormiu", "chave": "zerar-chave-2"}
    r = cli(app, "admin").post("/api/reservas/%d/diaria/zerar" % a, json=corpo)
    assert r.status_code == 201 and detalhe(app, a)["diaria_centavos"] == 0
    assert cli(app, "admin").post("/api/reservas/%d/diaria/zerar" % a, json=corpo).status_code == 200      # mesma chave
    h = sql(app, "SELECT acao, antes, depois FROM historico WHERE acao='diaria_zerada'")
    assert len(h) == 1 and "30000" not in str(h) and "90000" not in str(h) and "dormiu" not in str(h)
    assert cli(app, "admin").post("/api/reservas/%d/diaria/zerar" % a, json=dict(corpo, chave="zerar-chave-3", versao=detalhe(app, a)["versao"])).status_code == 409


def test_fechar_so_com_saldo_zero_bloqueia_lancamento_e_reabre_com_motivo(app):
    a = nova(app)
    cv = lambda: conta(app, a)["conta"]["versao"]  # noqa: E731
    assert cli(app, "admin").post("/api/reservas/%d/conta/fechar" % a, json={"conta_versao": cv()}).status_code == 409
    receber(app, a, 90000)
    assert cli(app, "admin").post("/api/reservas/%d/conta/fechar" % a, json={"conta_versao": 1}).status_code == 409    # versão velha
    assert cli(app, "recepcao").post("/api/reservas/%d/conta/fechar" % a, json={"conta_versao": cv()}).status_code == 200
    assert conta(app, a)["conta"]["situacao"] == "fechada"
    r = cli(app, "admin").post("/api/reservas/%d/despesas" % a, json={"categoria": "bar", "descricao": "Suco", "quantidade": 1, "valor_unit_centavos": 500})
    assert r.status_code == 409
    assert receber(app, a, 100).status_code == 409
    assert cli(app, "recepcao").post("/api/reservas/%d/conta/reabrir" % a, json={"conta_versao": cv(), "motivo": "Faltou lançar"}).status_code == 403
    assert cli(app, "admin").post("/api/reservas/%d/conta/reabrir" % a, json={"conta_versao": cv(), "motivo": "x"}).status_code == 422
    assert cli(app, "atendente").post("/api/reservas/%d/conta/reabrir" % a, json={"conta_versao": cv(), "motivo": "Faltou lançar"}).status_code == 200
    assert conta(app, a)["conta"]["situacao"] == "aberta" and lancar(app, a)
    assert [e[0] for e in sql(app, "SELECT acao FROM conta_evento ORDER BY id")] == ["fechar", "reabrir"]


def test_lista_de_lancamentos_cronologica_com_todos_os_tipos(app):
    a, b = par(app)
    l1 = lancar(app, a, 800)["id"]
    transferir(app, a, b, ["d%d" % l1])
    receber(app, b, 5000)
    j = cli(app, "admin").get("/api/reservas/%d/lancamentos" % b).get_json()
    assert [i["tipo"] for i in j["itens"]] == ["transferencia_entrada", "pagamento"]
    j = cli(app, "admin").get("/api/reservas/%d/lancamentos" % a).get_json()
    assert [i["tipo"] for i in j["itens"]] == ["lancamento", "transferencia_saida"] and j["itens"][1]["total_centavos"] == -800
    assert j["itens"][1]["por"] == "admin" and "Transferido para" in j["itens"][1]["motivo"]
    sem_pag = cli(app, "diretoria").get("/api/reservas/%d/lancamentos" % b).get_json()
    assert [i["tipo"] for i in sem_pag["itens"]] == ["transferencia_entrada", "pagamento"]


def test_busca_de_destino_por_nome_e_apartamento(app):
    a, b = par(app)
    nova(app, a="203", nome="Zélia Andrade")
    nova(app, a="204", nome="Futuro", i="2026-11-05", f="2026-11-07")
    f = lambda q: cli(app, "admin").get("/api/reservas/%d/destinos" % a, query_string={"q": q}).get_json()["itens"]  # noqa: E731
    assert [x["a"] for x in f("")] == ["202", "203"]
    assert [x["a"] for x in f("zelia")] == ["203"] and [x["a"] for x in f("joao")] == ["202"] and [x["a"] for x in f("203")] == ["203"]
    assert f("xyz") == []
    assert cli(app, "admin").get("/api/reservas/%d/destinos" % a, query_string={"q": "a" * 61}).status_code == 422
