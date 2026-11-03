"""Concorrência real (threads) e invariantes da etapa 3B: pagamento duplicado, estorno duplo, transferência duplicada, receber acima do saldo."""
import threading

from tests.apoio_pagamentos import app, cli, conta, lancar, nova, receber, sql, totais  # noqa: F401
from tests.test_transferencia import transferir  # noqa: F401


def em_paralelo(funcoes):
    saidas, barreira = [None] * len(funcoes), threading.Barrier(len(funcoes))

    def roda(k, f):
        barreira.wait()
        saidas[k] = f()
    ts = [threading.Thread(target=roda, args=(k, f)) for k, f in enumerate(funcoes)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return saidas


def test_pagamento_duplicado_mesma_chave_grava_uma_vez(app):
    rid = nova(app)
    corpo = {"valor_centavos": 30000, "forma": "pix", "chave": "chave-dupla-1", "conta_versao": conta(app, rid)["conta"]["versao"]}
    clientes = [cli(app, "admin", "a%d" % k) for k in range(6)]
    rs = em_paralelo([lambda c=c: c.post("/api/reservas/%d/pagamentos" % rid, json=corpo) for c in clientes])
    assert sorted(r.status_code for r in rs).count(201) == 1 and all(r.status_code in (200, 201, 409) for r in rs)
    assert sql(app, "SELECT COUNT(*) FROM pagamento") == [(1,)]


def test_receber_acima_do_saldo_em_paralelo_so_um_passa(app):
    rid = nova(app)
    v = conta(app, rid)["conta"]["versao"]
    clientes = [cli(app, "atendente", "t%d" % k) for k in range(5)]
    rs = em_paralelo([lambda c=c, k=k: c.post("/api/reservas/%d/pagamentos" % rid, json={
        "valor_centavos": 90000, "forma": "dinheiro", "chave": "chave-par-%d" % k, "conta_versao": v}) for k, c in enumerate(clientes)])
    assert [r.status_code for r in rs].count(201) == 1
    assert totais(app, rid)["saldo_centavos"] == 0 and sql(app, "SELECT SUM(valor_centavos) FROM pagamento") == [(90000,)]


def test_estorno_duplo_de_pagamento_e_de_despesa(app):
    rid = nova(app)
    pid = receber(app, rid, 5000).get_json()["id"]
    lid = lancar(app, rid)["id"]
    cs = [cli(app, "admin", "e%d" % k) for k in range(4)]
    rs = em_paralelo([lambda c=c: c.post("/api/pagamentos/%d/estorno" % pid, json={"motivo": "Valor errado"}) for c in cs])
    assert sorted(r.status_code for r in rs) == [201, 409, 409, 409]
    rs = em_paralelo([lambda c=c: c.post("/api/despesas/%d/estorno" % lid, json={"motivo": "Lançado errado"}) for c in cs])
    assert sorted(r.status_code for r in rs) == [201, 409, 409, 409]
    assert sql(app, "SELECT COUNT(*) FROM pagamento WHERE tipo='estorno'") == [(1,)]


def test_transferencia_duplicada_move_uma_vez(app):
    a, b = nova(app), nova(app, a="202", nome="João")
    lid = lancar(app, a, 700)["id"]
    v = conta(app, a)["conta"]["versao"]
    cs = [cli(app, "admin", "x%d" % k) for k in range(5)]
    rs = em_paralelo([lambda c=c, k=k: c.post("/api/reservas/%d/transferir" % a, json={
        "destino_id": b, "itens": ["d%d" % lid], "chave": "chave-tr-%d" % k, "conta_versao": v}) for k, c in enumerate(cs)])
    assert [r.status_code for r in rs].count(201) == 1
    assert totais(app, a)["despesas_centavos"] == 0 and totais(app, b)["despesas_centavos"] == 700
    assert sql(app, "SELECT COUNT(*) FROM transferencia") == [(1,)]


def test_invariante_pagamentos_mais_saldo_igual_ao_total_sempre(app):
    a, b = nova(app), nova(app, a="202", nome="João")
    ids = [lancar(app, a, 150 + k, 1 + k)["id"] for k in range(4)]
    receber(app, a, 33333)
    receber(app, a, 20001, "cartao", bandeira="Visa", modalidade="credito", parcelas=7)
    transferir(app, a, b, ["d%d" % ids[0], "d%d" % ids[1]])
    pid = sql(app, "SELECT id FROM pagamento ORDER BY id")[0][0]
    cli(app, "admin").post("/api/pagamentos/%d/estorno" % pid, json={"motivo": "Valor errado"})
    cli(app, "admin").post("/api/despesas/%d/estorno" % ids[2], json={"motivo": "Lançado errado"})
    for rid in (a, b):
        t = totais(app, rid)
        assert t["pagamentos_centavos"] + t["saldo_centavos"] == t["conta_centavos"] and t["saldo_centavos"] >= 0
        assert t["conta_centavos"] == t["diarias_centavos"] + t["despesas_centavos"]
