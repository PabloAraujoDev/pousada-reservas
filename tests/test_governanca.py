"""Governança: os 15 casos da especificação, permissões por perfil, privacidade da camareira, concorrência e atomicidade."""
import json
import sqlite3
import threading
from datetime import datetime

import pytest

from pousada.db import conectar
from pousada.regras import UNIDADES
from tests import conftest
from tests.conftest import criar_app_teste

HOJE = "2026-10-29"
RES = {"nome": "Maria Silva", "extras": "Joao Acompanhante", "n": 2, "p": "pago", "o": "PIX 31999998888 - berço",
       "grupo": "Familia Silva", "tipo": "socio", "diaria_centavos": 45000}


def cliente_como(app, papel, login=None):
    """Um cliente por (app, login): chamar de novo com o mesmo login reaproveita a sessão."""
    cache = app.__dict__.setdefault("_clientes_gov", {})
    chave = login or papel
    if chave not in cache:
        cache[chave] = conftest.cliente_como(app, papel, login)
    return cache[chave]


def hora(h, m=0, dia=29):
    return datetime(2026, 10, dia, h, m, 0)


def fazer_app(tmp_path, quando=None):
    return criar_app_teste(tmp_path, AGORA=quando or hora(9))


def reserva(app, a, i, f, **extra):
    r = cliente_como(app, "admin", "criador%s" % a.replace(" ", "")).post("/api/reservas", json=dict(RES, a=a, i=i, f=f, **extra))
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def sql(app, comando, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute(comando, args)
    finally:
        con.close()


def consulta(app, comando, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return [tuple(r) for r in con.execute(comando, args)]
    finally:
        con.close()


def pronto_em(app, u, quando):
    sql(app, "UPDATE governanca_unidade SET pronto_em=? WHERE unidade=?", (quando, u))


def unidade(cli, u, dia=None):
    r = cli.get("/api/governanca" + ("?dia=" + dia if dia else ""))
    assert r.status_code == 200, r.get_data(as_text=True)
    return next(x for x in r.get_json()["unidades"] if x["u"] == u)


def acao(cli, a, unidades, **extra):
    """unidades: lista de (u, versao)."""
    corpo = {"acao": a, "unidades": [{"u": u, "versao": v} for u, v in unidades]}
    corpo.update(extra)
    return cli.post("/api/governanca/acao", json=corpo)


def versao(cli, u):
    return unidade(cli, u)["versao"]


# ---------------------------------------------------------------- os 15 casos da especificação

def test_01_saida_ontem_vira_suja_automatica(tmp_path):
    app = fazer_app(tmp_path)
    reserva(app, "201", "2026-10-25", "2026-10-28")
    pronto_em(app, "201", "2026-10-20 10:00:00")
    u = unidade(cliente_como(app, "atendente"), "201")
    assert (u["situacao"], u["suja_origem"], u["dias_sem_arrumacao"]) == ("suja", "automatica", 9)


def test_02_e_03_saida_hoje_aguarda_ate_meio_dia(tmp_path):
    app = fazer_app(tmp_path, hora(10))
    reserva(app, "201", "2026-10-25", HOJE)
    pronto_em(app, "201", "2026-10-28 15:00:00")
    u = unidade(cliente_como(app, "atendente"), "201")
    assert u["situacao"] == "aguardando_saida" and u["saida_hoje"]["hora"] == "12:00"
    app.config["AGORA"] = hora(12)
    assert unidade(cliente_como(app, "atendente"), "201")["situacao"] == "suja"


def test_04_confirmar_saida_evita_suja_automatica_depois_de_pronta(tmp_path):
    app = fazer_app(tmp_path, hora(10))
    reserva(app, "201", "2026-10-25", HOJE)
    pronto_em(app, "201", "2026-10-28 15:00:00")
    rec, cam = cliente_como(app, "recepcao"), cliente_como(app, "camareira")
    v = versao(rec, "201")
    assert acao(rec, "suja", [("201", v)]).status_code == 422                       # falta confirmar a saída
    r = acao(rec, "suja", [("201", v)], confirmou_saida=True)
    assert r.status_code == 200
    app.config["AGORA"] = hora(11)
    assert acao(cam, "pronta", [("201", versao(cam, "201"))]).status_code == 200
    app.config["AGORA"] = hora(12, 30)
    assert unidade(cam, "201")["situacao"] == "pronta"
    assert consulta(app, "SELECT saida_confirmada FROM governanca_unidade WHERE unidade='201'")[0][0] == HOJE


def test_05_troca_atrasada_e_primeira(tmp_path):
    app = fazer_app(tmp_path, hora(13, 5))
    reserva(app, "202", "2026-10-25", HOJE)
    reserva(app, "202", HOJE, "2026-10-31")
    pronto_em(app, "202", "2026-10-28 15:00:00")
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='202'")
    u = unidade(cliente_como(app, "atendente"), "202")
    assert u["troca_hoje"] and u["atrasada"] and u["situacao"] == "suja"
    assert u["saida_hoje"] and u["chegada_hoje"]["pessoas"] == 2


def test_06_reserva_cancelada_nao_suja(tmp_path):
    app = fazer_app(tmp_path)
    r = reserva(app, "201", "2026-10-25", "2026-10-28")
    cliente_como(app, "admin", "outro").delete("/api/reservas/%d" % r["id"], json={"versao": r["versao"], "motivo": "teste"})
    pronto_em(app, "201", "2026-10-20 10:00:00")
    assert unidade(cliente_como(app, "atendente"), "201")["situacao"] == "pronta"


def test_07_duas_pessoas_iniciam_idempotente(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    ana, bia = cliente_como(app, "camareira", "ana"), cliente_como(app, "camareira", "bia")
    v = versao(ana, "203")
    assert acao(ana, "iniciar", [("203", v)]).get_json()["resultados"][0]["resultado"] == "ok"
    r = acao(bia, "iniciar", [("203", v)])
    assert r.status_code == 200 and r.get_json()["resultados"][0]["resultado"] == "ja_estava"
    assert consulta(app, "SELECT COUNT(*) FROM governanca_evento WHERE unidade='203' AND acao='iniciar'")[0][0] == 1


def test_08_pronta_com_versao_velha_da_409_explicativo(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    ana, bia = cliente_como(app, "camareira", "ana"), cliente_como(app, "camareira", "bia")
    v = versao(ana, "203")
    acao(ana, "iniciar", [("203", v)])
    antes = consulta(app, "SELECT COUNT(*) FROM governanca_evento")[0][0]
    r = acao(bia, "pronta", [("203", v)])
    assert r.status_code == 409
    c = r.get_json()["conflitos"][0]
    assert c["u"] == "203" and c["situacao_atual"] == "em_arrumacao" and c["por"] == "ana" and c["em"] == "09:00"
    assert set(c) == {"u", "situacao_atual", "versao", "por", "em"}
    assert consulta(app, "SELECT COUNT(*) FROM governanca_evento")[0][0] == antes


def test_09_em_massa_com_a_104_da_422_e_nao_grava(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade IN ('202','203')")
    cam = cliente_como(app, "camareira")
    r = acao(cam, "iniciar", [("202", versao(cam, "202")), ("203", versao(cam, "203")), ("104", 1)])
    assert r.status_code == 422 and "interditada" in r.get_json()["erro"]
    assert consulta(app, "SELECT COUNT(*) FROM governanca_evento")[0][0] == 0
    assert consulta(app, "SELECT situacao FROM governanca_unidade WHERE unidade IN ('202','203')") == [("suja",), ("suja",)]


def test_10_camareira_nao_recebe_dados_do_hospede(tmp_path):
    app = fazer_app(tmp_path)
    reserva(app, "205", HOJE, "2026-10-31")
    cam = cliente_como(app, "camareira")
    r = cam.get("/api/governanca")
    texto = r.get_data(as_text=True)
    for proibido in ("Maria", "Silva", "Familia", "nome", "hospede", "reserva_id", "grupo", "pago", "diaria", "tipo",
                     "extras", "Acompanhante", "31999998888", "socio", "PIX", "valor"):
        assert proibido not in texto, proibido
    u = unidade(cam, "205")
    assert u["obs_reserva"] == "berço" and u["chegada_hoje"] == {"hora": "14:00", "pessoas": 2}
    a = unidade(cliente_como(app, "atendente"), "205")
    assert a["chegada_hoje"]["nome"] == "Maria Silva" and a["chegada_hoje"]["reserva_id"] and a["grupo_reserva"] == "Familia Silva"
    assert "31999998888" not in json.dumps(a) and "pago" not in a and "diaria" not in json.dumps(a)


def test_11_camareira_sem_manutencao_e_sem_desfazer_de_colega(tmp_path):
    app = fazer_app(tmp_path)
    cam, outra = cliente_como(app, "camareira", "cam1"), cliente_como(app, "camareira", "cam2")
    r = acao(cam, "manutencao_abrir", [("202", versao(cam, "202"))], motivo="torneira")
    assert r.status_code == 403
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    assert acao(outra, "pronta", [("203", versao(outra, "203"))]).status_code == 200
    r = acao(cam, "suja", [("203", versao(cam, "203"))])
    assert r.status_code == 403


def test_12_dias_sem_arrumacao_e_enxoval(tmp_path):
    app = fazer_app(tmp_path)
    reserva(app, "301", "2026-10-24", "2026-11-02")
    pronto_em(app, "301", "2026-10-25 09:00:00")
    cli = cliente_como(app, "atendente")
    u = unidade(cli, "301")
    assert u["situacao"] == "hospedada" and u["dias_sem_arrumacao"] == 4 and u["alerta_enxoval"] is False   # N padrão = 7
    app.config["GOV_DIAS_TROCA_ENXOVAL"] = 3
    assert unidade(cli, "301")["alerta_enxoval"] is True


def test_13_vaga_pronta_ha_muito_tempo_nao_suja(tmp_path):
    app = fazer_app(tmp_path)
    pronto_em(app, "302", "2026-10-19 09:00:00")
    cli = cliente_como(app, "atendente")
    app.config["GOV_DIAS_VAGA"] = 7
    u = unidade(cli, "302")
    assert u["situacao"] == "pronta" and u["pronta_ha_dias"] == 10 and u["alerta_enxoval"] is False


def test_14_migracao_com_reservas_antigas_nao_suja_ninguem(tmp_path):
    from pousada.db import iniciar_banco
    from tests.test_migracoes import PASTA_REAL
    import shutil
    import os
    pasta = tmp_path / "mig_ate_10"
    pasta.mkdir()
    for f in os.listdir(PASTA_REAL):
        if f < "011":
            shutil.copy(os.path.join(PASTA_REAL, f), pasta / f)
    banco = str(tmp_path / "velho.db")
    iniciar_banco(banco, str(pasta))
    con = conectar(banco)
    con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao) VALUES "
                "('201','Antiga','',1,'2026-01-01','2026-01-05','pago','','','x','x',1)")
    con.close()
    iniciar_banco(banco, PASTA_REAL, pasta_backup=str(tmp_path / "bk"))
    linhas = consulta_banco(banco, "SELECT unidade, situacao, pronto_em, versao FROM governanca_unidade")
    assert len(linhas) == 25 and {l[1] for l in linhas} == {"pronta"} and all(l[2] and l[3] == 1 for l in linhas)
    assert [l[0] for l in linhas] == UNIDADES
    from pousada import create_app
    app = create_app(banco, config={"SECRET_KEY": "chave-so-de-teste", "PASTA_INSTANCIA": str(tmp_path / "inst"),
                                    "PASTA_BACKUP": str(tmp_path / "bk"), "AGORA": hora(9)})
    app.test_client_class = conftest.ClienteTeste
    sujas = [x for x in cliente_como(app, "admin").get("/api/governanca").get_json()["unidades"] if x["situacao"] == "suja"]
    assert sujas == []


def consulta_banco(banco, comando):
    con = sqlite3.connect(banco)
    try:
        return con.execute(comando).fetchall()
    finally:
        con.close()


def test_15_observacao_141_caracteres_e_xss(tmp_path):
    app = fazer_app(tmp_path)
    cli = cliente_como(app, "camareira")
    v = versao(cli, "202")
    assert acao(cli, "observacao", [("202", v)], obs="x" * 141).status_code == 422
    r = acao(cli, "observacao", [("202", v)], obs='<script>alert(1)</script> faltou toalha')
    assert r.status_code == 200
    assert unidade(cli, "202")["obs"] == '<script>alert(1)</script> faltou toalha'     # texto puro; a tela usa textContent
    assert acao(cli, "observacao", [("203", versao(cli, "203"))], obs="a‮b").status_code == 422
    assert acao(cli, "observacao", [("203", versao(cli, "203"))], obs="linha1\nlinha2").status_code == 200
    assert unidade(cli, "203")["obs"] == "linha1 linha2"


# ---------------------------------------------------------------- leitura: dia, totais, parâmetros

def test_get_dia_amanha_e_limites(tmp_path):
    app = fazer_app(tmp_path)
    reserva(app, "206", "2026-10-30", "2026-11-01")
    cli = cliente_como(app, "atendente")
    assert unidade(cli, "206", "2026-10-30")["chegada_hoje"] and unidade(cli, "206", "2026-10-30")["pode"] == []
    assert unidade(cli, "206")["chegada_hoje"] is None
    for ruim in ("2026-10-28", "2026-11-06", "abc", "2026-02-30"):
        assert cli.get("/api/governanca?dia=" + ruim).status_code == 422


def test_totais_e_104_interditada(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade IN ('104','202')")
    j = cliente_como(app, "diretoria").get("/api/governanca").get_json()
    t = j["totais"]
    assert t["interditada"] == 1 and t["suja"] == 1 and t["pronta"] == 23 and sum(
        t[k] for k in ("suja", "em_arrumacao", "pronta", "hospedada", "aguardando_saida", "manutencao", "interditada")) == 25
    assert j["parametros"]["dias_troca"] == 7 and j["parametros"]["dias_vaga"] == 14 and j["agora"] == "09:00"
    assert next(u for u in j["unidades"] if u["u"] == "104")["pode"] == []


def test_iniciar_hospedada_e_pronta_depois(tmp_path):
    app = fazer_app(tmp_path)
    reserva(app, "304", "2026-10-26", "2026-11-02")
    cam = cliente_como(app, "camareira")
    u = unidade(cam, "304")
    assert u["situacao"] == "hospedada" and "iniciar" in u["pode"]
    assert acao(cam, "iniciar", [("304", u["versao"])]).status_code == 200
    assert unidade(cam, "304")["situacao"] == "em_arrumacao"
    assert acao(cam, "pronta", [("304", versao(cam, "304"))]).status_code == 200
    j = unidade(cam, "304")
    assert j["situacao"] == "hospedada" and j["dias_sem_arrumacao"] is None


def test_camareira_desfaz_proprio_pronto_dentro_da_janela(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    cam = cliente_como(app, "camareira")
    acao(cam, "pronta", [("203", versao(cam, "203"))])
    app.config["AGORA"] = hora(9, 10)
    assert "suja" in unidade(cam, "203")["pode"]
    app.config["AGORA"] = hora(9, 16)
    assert "suja" not in unidade(cam, "203")["pode"]
    assert acao(cam, "suja", [("203", versao(cam, "203"))]).status_code == 403


def test_manutencao_abre_fecha_com_historico_sem_texto(tmp_path):
    app = fazer_app(tmp_path)
    ate = cliente_como(app, "atendente")
    assert acao(ate, "manutencao_abrir", [("202", versao(ate, "202"))]).status_code == 422           # motivo obrigatório
    r = acao(ate, "manutencao_abrir", [("202", versao(ate, "202"))], motivo="vazamento SEGREDO")
    assert r.status_code == 200 and unidade(ate, "202")["situacao"] == "manutencao"
    assert unidade(ate, "202")["manutencao_motivo"] == "vazamento SEGREDO"
    assert acao(ate, "iniciar", [("202", versao(ate, "202"))]).status_code == 422
    assert acao(ate, "manutencao_fechar", [("202", versao(ate, "202"))]).status_code == 200
    hist = consulta(app, "SELECT acao, entidade, entidade_id, antes, depois FROM historico WHERE entidade='governanca'")
    assert [h[0] for h in hist] == ["manutencao_abrir", "manutencao_fechar"] and hist[0][2] is None
    tudo = json.dumps(consulta(app, "SELECT * FROM historico")) + json.dumps(consulta(app, "SELECT * FROM governanca_evento"))
    assert "SEGREDO" not in tudo and "vazamento" not in tudo


def test_admin_desfaz_pronto_de_outro_e_fica_no_historico(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    cam, adm = cliente_como(app, "camareira"), cliente_como(app, "admin", "chefe")
    acao(cam, "pronta", [("203", versao(cam, "203"))])
    assert acao(adm, "suja", [("203", versao(adm, "203"))]).status_code == 200
    assert consulta(app, "SELECT acao, usuario_login FROM historico WHERE entidade='governanca'") == [("governanca_correcao", "chefe")]


def test_eventos_da_unidade(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    cam, ate = cliente_como(app, "camareira"), cliente_como(app, "atendente")
    acao(cam, "iniciar", [("203", versao(cam, "203"))], obs="NUNCA no log")
    r = ate.get("/api/governanca/203/eventos")
    assert r.status_code == 200 and r.get_json()[0]["acao"] == "iniciar" and "ip" not in r.get_json()[0]
    assert ate.get("/api/governanca/Chal%C3%A9%20A/eventos").status_code == 200
    assert ate.get("/api/governanca/999/eventos").status_code == 404
    sql(app, "INSERT INTO governanca_evento (em, unidade, usuario_login, acao) VALUES ('2026-10-01 08:00:00','203','velho','pronta')")
    assert len(ate.get("/api/governanca/203/eventos").get_json()) == 2
    assert len(cam.get("/api/governanca/203/eventos").get_json()) == 1             # a camareira vê só o dia


def test_evento_e_imutavel_por_trigger(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "INSERT INTO governanca_evento (em, unidade, usuario_login, acao) VALUES ('2026-10-01 08:00:00','203','x','pronta')")
    with pytest.raises(sqlite3.DatabaseError):
        sql(app, "UPDATE governanca_evento SET unidade='202'")
    with pytest.raises(sqlite3.DatabaseError):
        sql(app, "DELETE FROM governanca_evento")
    with pytest.raises(sqlite3.DatabaseError):
        sql(app, "UPDATE governanca_unidade SET situacao='x' WHERE unidade='203'")      # CHECK


# ---------------------------------------------------------------- validação e atomicidade

@pytest.mark.parametrize("corpo", [
    [], {}, {"acao": "voar", "unidades": [{"u": "202", "versao": 1}]},
    {"acao": "pronta", "unidades": []}, {"acao": "pronta", "unidades": "202"},
    {"acao": "pronta", "unidades": [{"u": "999", "versao": 1}]},
    {"acao": "pronta", "unidades": [{"u": "202", "versao": True}]},
    {"acao": "pronta", "unidades": [{"u": "202", "versao": "1"}]},
    {"acao": "pronta", "unidades": [{"u": "202", "versao": 1}, {"u": "202", "versao": 1}]},
    {"acao": "pronta", "unidades": [{"u": "202", "versao": 1}], "confirmou_saida": "sim"},
    {"acao": "pronta", "unidades": [{"u": ["202"], "versao": 1}]},
    {"acao": "pronta", "unidades": ["202"]},
    {"acao": "observacao", "unidades": [{"u": "202", "versao": 1}], "obs": 5},
    {"acao": "pronta", "unidades": [{"u": u, "versao": 1} for u in UNIDADES] + [{"u": "202", "versao": 1}]},
])
def test_pedido_invalido_da_422(tmp_path, corpo):
    app = fazer_app(tmp_path)
    r = cliente_como(app, "admin").post("/api/governanca/acao", json=corpo)
    assert r.status_code == 422, r.get_data(as_text=True)


def test_nao_aceita_usuario_ou_papel_do_cliente(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    rec = cliente_como(app, "recepcao")
    r = rec.post("/api/governanca/acao", json={"acao": "iniciar", "papel": "admin", "usuario": "admin",
                                               "unidades": [{"u": "203", "versao": 1}]})
    assert r.status_code == 403


def test_atomicidade_conflito_em_uma_desfaz_todas(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade IN ('202','203')")
    ana, bia = cliente_como(app, "camareira", "ana"), cliente_como(app, "camareira", "bia")
    v202, v203 = versao(ana, "202"), versao(ana, "203")
    acao(ana, "observacao", [("203", v203)], obs="mudou")                      # 203 muda de versão
    r = acao(bia, "iniciar", [("202", v202), ("203", v203)])
    assert r.status_code == 409 and [c["u"] for c in r.get_json()["conflitos"]] == ["203"]
    assert unidade(bia, "202")["situacao"] == "suja"
    assert consulta(app, "SELECT COUNT(*) FROM governanca_evento WHERE acao='iniciar'")[0][0] == 0


def test_em_massa_ok_e_mistura_de_ja_estava(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade IN ('202','203','204')")
    cam = cliente_como(app, "camareira")
    acao(cam, "iniciar", [("204", versao(cam, "204"))])
    r = acao(cam, "iniciar", [(u, versao(cam, u)) for u in ("202", "203", "204")])
    j = r.get_json()
    assert r.status_code == 200 and [x["resultado"] for x in j["resultados"]] == ["ok", "ok", "ja_estava"]
    lotes = consulta(app, "SELECT DISTINCT lote FROM governanca_evento WHERE acao='iniciar' AND unidade IN ('202','203')")
    assert lotes == [(j["lote"],)]


def test_concorrencia_duas_threads_so_uma_grava(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    c1, c2 = cliente_como(app, "camareira", "t1"), cliente_como(app, "camareira", "t2")
    v = versao(c1, "203")
    barreira, saidas = threading.Barrier(2), []

    def usar(c, a):
        barreira.wait()
        saidas.append((a, acao(c, a, [("203", v)])))
    ts = [threading.Thread(target=usar, args=(c1, "iniciar")), threading.Thread(target=usar, args=(c2, "pronta"))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    codigos = sorted(r.status_code for _, r in saidas)
    assert codigos == [200, 409]                                          # a primeira ganha; a outra recebe 409 explicativo
    assert consulta(app, "SELECT COUNT(*) FROM governanca_evento")[0][0] == 1


def test_concorrencia_mesma_acao_e_idempotente(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    c1, c2 = cliente_como(app, "camareira", "t1"), cliente_como(app, "camareira", "t2")
    v = versao(c1, "203")
    barreira, saidas = threading.Barrier(2), []

    def usar(c):
        barreira.wait()
        saidas.append(acao(c, "iniciar", [("203", v)]))
    ts = [threading.Thread(target=usar, args=(c,)) for c in (c1, c2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(r.status_code for r in saidas) == [200, 200]
    assert sorted(r.get_json()["resultados"][0]["resultado"] for r in saidas) == ["ja_estava", "ok"]
    assert consulta(app, "SELECT COUNT(*) FROM governanca_evento")[0][0] == 1


# ---------------------------------------------------------------- permissões por perfil

PAPEIS = ["admin", "atendente", "recepcao", "camareira", "diretoria", "consulta"]


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_de_acoes_por_perfil(tmp_path, papel):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade IN ('202','203','204')")
    c = cliente_como(app, papel)
    assert c.get("/api/governanca").status_code == 200
    assert c.get("/api/governanca/202/eventos").status_code == 200
    esperado = {
        "iniciar": {"admin", "atendente", "camareira"}, "pronta": {"admin", "atendente", "camareira", "recepcao"},
        "observacao": {"admin", "atendente", "camareira", "recepcao"}, "manutencao_abrir": {"admin", "atendente"}}
    for a, quem in esperado.items():
        extra = {"obs": "ok"} if a == "observacao" else {"motivo": "cano"} if a == "manutencao_abrir" else {}
        u = {"iniciar": "202", "pronta": "203", "observacao": "204", "manutencao_abrir": "205"}[a]
        r = acao(c, a, [(u, versao(c, u))], **extra)
        assert (r.status_code == 200) == (papel in quem), (papel, a, r.status_code)
        if papel not in quem:
            assert r.status_code == 403
    # "suja": recepção, atendente e admin; camareira só desfazendo o próprio pronto
    pronta = unidade(c, "203")["situacao"] == "pronta"
    r = acao(c, "suja", [("206", versao(c, "206"))])
    assert (r.status_code == 200) == (papel in {"admin", "atendente", "recepcao"})
    if papel in {"diretoria", "consulta", "camareira"}:
        assert r.status_code == 403
    assert pronta == (papel in esperado["pronta"])


def test_pode_reflete_o_perfil(tmp_path):
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='202'")
    assert unidade(cliente_como(app, "camareira"), "202")["pode"] == ["iniciar", "pronta"]
    assert unidade(cliente_como(app, "recepcao"), "202")["pode"] == ["pronta"]
    assert unidade(cliente_como(app, "consulta"), "202")["pode"] == []
    assert "manutencao_abrir" in unidade(cliente_como(app, "atendente"), "202")["pode"]


def test_sem_login_e_sem_csrf(tmp_path):
    app = fazer_app(tmp_path)
    assert app.test_client().get("/api/governanca").status_code == 401
    cam = cliente_como(app, "camareira")
    corpo = {"acao": "pronta", "unidades": [{"u": "202", "versao": 1}]}
    assert cam.post("/api/governanca/acao", json=corpo, sem_csrf=True).status_code == 403
    assert cam.post("/api/governanca/acao", json=corpo, headers={"Origin": "http://evil.example"}).status_code == 403


def test_quando_nao_ha_reserva_nenhuma_chave_de_hospede_para_diretoria_tambem_vem(tmp_path):
    app = fazer_app(tmp_path)
    reserva(app, "207", HOJE, "2026-10-31")
    assert unidade(cliente_como(app, "diretoria"), "207")["chegada_hoje"]["nome"] == "Maria Silva"
