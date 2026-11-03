"""QA hospedagem/pagamentos: a conta paga ou fechada não pode ficar incoerente por edição de datas/diária/unidade."""
from tests.apoio_pagamentos import *  # noqa: F401,F403
from tests.apoio_pagamentos import app, cli, conta, detalhe, lancar, nova, receber, sql  # noqa: F401


def _fechar(app, rid):
    v = conta(app, rid)["conta"]["versao"]
    r = cli(app, "admin").post("/api/reservas/%d/conta/fechar" % rid, json={"conta_versao": v})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_mover_nao_encurta_abaixo_do_pago(app):
    rid = nova(app)                                   # 3 noites x 300 = 900
    assert receber(app, rid, 90000).status_code == 201
    d = detalhe(app, rid)
    r = cli(app, "admin").post("/api/reservas/%d/mover" % rid, json={"versao": d["versao"], "f": "2026-10-28"})
    assert r.status_code == 409, r.get_data(as_text=True)


def test_conta_fechada_nao_aceita_mudar_datas_nem_diaria(app):
    rid = nova(app)
    assert receber(app, rid, 90000).status_code == 201
    _fechar(app, rid)
    d = detalhe(app, rid)
    corpo = {k: d[k] for k in ("a", "nome", "extras", "n", "i", "f", "p", "o", "grupo", "versao")}
    r = cli(app, "admin").put("/api/reservas/%d" % rid, json=dict(corpo, diaria_centavos=50000))
    assert r.status_code == 409, r.get_data(as_text=True)
    r = cli(app, "admin").post("/api/reservas/%d/mover" % rid, json={"versao": d["versao"], "f": "2026-11-05"})
    assert r.status_code == 409, r.get_data(as_text=True)


def test_encurtar_e_receber_ao_mesmo_tempo_mantem_pago_menor_ou_igual_ao_total(app):
    from tests.test_pagamentos_concorrencia import em_paralelo
    for k in range(4):
        rid = nova(app, a=["201", "202", "203", "204"][k])
        v, cv = detalhe(app, rid)["versao"], conta(app, rid)["conta"]["versao"]
        c1, c2 = cli(app, "admin", "m%d" % k), cli(app, "admin", "n%d" % k)
        em_paralelo([lambda: c1.post("/api/reservas/%d/mover" % rid, json={"versao": v, "f": "2026-10-28"}),
                     lambda: c2.post("/api/reservas/%d/pagamentos" % rid, json={"valor_centavos": 90000, "forma": "pix",
                                                                              "chave": "chave-mr-%d" % k, "conta_versao": cv})])
        tot = cli(app, "admin").get("/api/reservas/%d/pagamentos" % rid).get_json()["total"]
        assert 0 <= tot["pagamentos_centavos"] <= tot["conta_centavos"]


def test_excluir_definitivo_recusa_reserva_com_fechamento_de_conta(app):
    rid = nova(app, diaria_centavos=None)
    _fechar(app, rid)                                  # conta zerada, mas o fechamento ficou no registro imutável
    v = detalhe(app, rid)["versao"]
    r = cli(app, "admin").post("/api/reservas/%d/excluir-definitivo" % rid, json={"versao": v})
    assert r.status_code == 409 and sql(app, "SELECT COUNT(*) FROM reservas WHERE id=?", (rid,)) == [(1,)]
