"""Hospedagem (etapa 3A): check-in efetivo e reversão, apartamento liberado com a conta aberta (e Governança), placa, concorrência."""
from datetime import datetime

import pytest

from pousada.db import conectar
from tests import conftest
from tests.conftest import criar_app_teste

AGORA = datetime(2026, 10, 29, 9, 0, 0)
RES = {"a": "201", "nome": "Maria Silva", "extras": "", "n": 3, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente",
       "o": "", "grupo": "", "diaria_centavos": None}
LANC = {"categoria": "bar", "descricao": "Água 500ml", "quantidade": 2, "valor_unit_centavos": 800, "chave": "k1abcdef"}


def cli(app, papel, login=None):
    cache = app.__dict__.setdefault("_cl", {})
    chave = login or papel
    if chave not in cache:
        cache[chave] = conftest.cliente_como(app, papel, login)
    return cache[chave]


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def nova(app, **extra):
    r = cli(app, "admin").post("/api/reservas", json=dict(RES, **extra))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def detalhe(app, rid, papel="admin"):
    return cli(app, papel).get("/api/reservas/%d" % rid).get_json()


def acao(app, rid, caminho, papel="admin", **corpo):
    """POST de estado com a versão atual (a menos que 'versao' venha no corpo)."""
    if "versao" not in corpo:
        corpo["versao"] = detalhe(app, rid)["versao"]
    if caminho in ("checkin/reverter", "liberar", "liberar/reverter") and "motivo" not in corpo:
        corpo["motivo"] = "Motivo de teste"           # motivo obrigatório (ausente = 400; veja test_hospedagem_motivo.py)
    if corpo.get("motivo", 0) is None:
        del corpo["motivo"]
    return cli(app, papel).post("/api/reservas/%d/%s" % (rid, caminho), json=corpo)


def sql(app, comando, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return [tuple(r) for r in con.execute(comando, args)]
    finally:
        con.close()


def test_checkin_registra_e_aparece_no_detalhe_e_na_lista(app):
    rid = nova(app)["id"]
    assert detalhe(app, rid)["estado_hospedagem"] == "pendente"
    r = acao(app, rid, "checkin", "recepcao")
    assert r.status_code == 201 and r.get_json()["estado"] == "efetuado"
    d = detalhe(app, rid)
    assert d["estado_hospedagem"] == "efetuado" and d["checkin_por"] == "recepcao" and d["checkin_em"] == "2026-10-29 09:00:00"
    assert cli(app, "admin").get("/api/reservas").get_json()[0]["estado_hospedagem"] == "efetuado"
    assert sql(app, "SELECT acao, usuario_login, detalhe FROM hospedagem_evento") == [("checkin", "recepcao", "")]


def test_checkin_nao_muda_a_contagem_por_datas(app):
    """O estado explícito não mexe nos cartões Check-ins/Ocupados: eles seguem as datas da reserva."""
    rid = nova(app, i="2026-10-29", f="2026-10-31")["id"]
    antes = cli(app, "admin").get("/api/ocupacao?inicio=2026-10-29&fim=2026-10-31").get_json()
    acao(app, rid, "checkin")
    assert cli(app, "admin").get("/api/ocupacao?inicio=2026-10-29&fim=2026-10-31").get_json()["resumo"] == antes["resumo"]


def test_checkin_regras_de_data_e_repeticao(app):
    futura = nova(app, a="202", i="2026-11-02", f="2026-11-04")["id"]
    assert acao(app, futura, "checkin").status_code == 422
    passada = nova(app, a="203", i="2026-10-20", f="2026-10-25")["id"]
    assert acao(app, passada, "checkin").status_code == 422
    rid = nova(app)["id"]
    v = detalhe(app, rid)["versao"]
    assert acao(app, rid, "checkin", versao=v).status_code == 201
    assert acao(app, rid, "checkin", versao=v).status_code == 409           # duplo clique: versão velha
    assert acao(app, rid, "checkin").status_code == 409                     # já efetuado, mesmo com versão nova


def test_reverter_sem_lancamentos_funciona_e_registra(app):
    rid = nova(app)["id"]
    acao(app, rid, "checkin")
    r = acao(app, rid, "checkin/reverter")
    assert r.status_code == 200 and r.get_json()["estado"] == "pendente"
    d = detalhe(app, rid)
    assert d["checkin_em"] is None and d["checkin_por"] is None
    assert [x[0] for x in sql(app, "SELECT acao FROM hospedagem_evento ORDER BY id")] == ["checkin", "checkin_reverter"]
    assert acao(app, rid, "checkin/reverter").status_code == 409            # não está mais efetuado


def test_reverter_bloqueado_por_despesa_ativa_e_liberado_apos_estorno(app):
    rid = nova(app)["id"]
    acao(app, rid, "checkin")
    lid = cli(app, "admin").post("/api/reservas/%d/despesas" % rid, json=LANC).get_json()["id"]
    r = acao(app, rid, "checkin/reverter")
    assert r.status_code == 409 and "Estorne" in r.get_json()["erro"]
    cli(app, "admin").post("/api/despesas/%d/estorno" % lid, json={"motivo": "lançado por engano"})
    assert acao(app, rid, "checkin/reverter").status_code == 200            # estornado: nenhum lançamento ativo


def test_reverter_bloqueado_por_diaria_informada(app):
    rid = nova(app, diaria_centavos=35000)["id"]
    acao(app, rid, "checkin")
    r = acao(app, rid, "checkin/reverter")
    assert r.status_code == 409 and "diária" in r.get_json()["erro"] and "35000" not in r.get_data(as_text=True)
    v = detalhe(app, rid)
    corpo = {k: v[k] for k in ("a", "nome", "extras", "n", "i", "f", "p", "o", "grupo", "versao")}
    assert cli(app, "admin").put("/api/reservas/%d" % rid, json=dict(corpo, diaria_centavos=None)).status_code == 200
    assert acao(app, rid, "checkin/reverter").status_code == 200


def test_liberar_deixa_a_conta_aberta_e_a_unidade_suja_na_governanca(app):
    rid = nova(app)["id"]
    antes = {u["u"]: u for u in cli(app, "admin").get("/api/governanca").get_json()["unidades"]}["201"]
    assert antes["situacao"] == "hospedada"
    cli(app, "admin").post("/api/reservas/%d/despesas" % rid, json=LANC)
    r = acao(app, rid, "liberar")
    assert r.status_code == 200 and r.get_json()["estado"] == "conta_aberta"
    depois = {u["u"]: u for u in cli(app, "admin").get("/api/governanca").get_json()["unidades"]}["201"]
    assert depois["situacao"] == "suja" and depois["ocupacao"] == "vaga" and "hospede" not in depois
    ev = sql(app, "SELECT acao, de, para, lote FROM governanca_evento WHERE unidade='201'")
    assert ev == [("suja", "pronta", "suja", "conta_aberta")]
    # a conta (despesas) continua acessível e a reserva aparece em "Contas abertas"
    assert cli(app, "admin").get("/api/reservas/%d/despesas" % rid).status_code == 200
    ca = cli(app, "recepcao").get("/api/contas-abertas").get_json()
    assert ca["contas_abertas"] == 1 and ca["itens"][0]["id"] == rid and "800" not in str(ca) and "1600" not in str(ca)
    assert cli(app, "admin").get("/api/despesas/resumo").get_json()["liberadas"] == 1
    assert acao(app, rid, "liberar").status_code == 409


def test_unidade_liberada_pode_ser_arrumada_e_nao_volta_a_ficar_hospedada(app):
    rid = nova(app)["id"]
    acao(app, rid, "liberar")
    u = {x["u"]: x for x in cli(app, "admin").get("/api/governanca").get_json()["unidades"]}["201"]
    r = cli(app, "admin").post("/api/governanca/acao", json={"acao": "pronta", "unidades": [{"u": "201", "versao": u["versao"]}]})
    assert r.status_code == 200
    again = {x["u"]: x for x in cli(app, "admin").get("/api/governanca").get_json()["unidades"]}["201"]
    assert again["situacao"] == "pronta"


def test_desfazer_liberacao_volta_a_hospedada_e_fecha_a_lista(app):
    rid = nova(app)["id"]
    acao(app, rid, "liberar")
    r = acao(app, rid, "liberar/reverter")
    assert r.status_code == 200 and r.get_json()["estado"] == "pendente"
    assert cli(app, "admin").get("/api/contas-abertas").get_json()["contas_abertas"] == 0
    assert acao(app, rid, "liberar/reverter").status_code == 409
    assert [x[0] for x in sql(app, "SELECT acao FROM hospedagem_evento ORDER BY id")] == ["liberar", "liberar_reverter"]


def test_conta_fechada_sai_da_lista_de_contas_abertas(app):
    rid = nova(app)["id"]
    acao(app, rid, "liberar")
    sql(app, "INSERT INTO despesa_conta (reserva_id, situacao) VALUES (?, 'fechada')", (rid,))
    assert cli(app, "admin").get("/api/contas-abertas").get_json()["contas_abertas"] == 0
