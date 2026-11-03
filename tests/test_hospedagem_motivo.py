"""Reverter check-in, liberar e desfazer a liberação: MOTIVO obrigatório para todos os perfis, recepção autorizada, histórico do administrador mostra o motivo."""
import pytest

from tests.test_hospedagem import acao, app, cli, detalhe, nova, sql  # noqa: F401

ROTAS = ("checkin/reverter", "liberar", "liberar/reverter")
PAPEIS_QUE_PODEM = ("admin", "atendente", "recepcao")


def _preparar(app, rota, papel):
    """Reserva no estado em que a rota é possível."""
    rid = nova(app)["id"]
    if rota == "checkin/reverter":
        acao(app, rid, "checkin")
    if rota == "liberar/reverter":
        acao(app, rid, "liberar")
    return rid


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("papel", PAPEIS_QUE_PODEM)
def test_motivo_ausente_em_branco_ou_de_tipo_errado_da_400(app, rota, papel):
    rid = _preparar(app, rota, papel)
    for m in (None, "", "     ", 123, ["x"]):
        r = acao(app, rid, rota, papel, motivo=m) if m is not None else acao(app, rid, rota, papel, motivo=None)
        assert r.status_code == 400, (rota, papel, m, r.status_code)
    assert sql(app, "SELECT COUNT(*) FROM hospedagem_evento WHERE acao=?", (rota.replace("/", "_"),)) == [(0,)]


@pytest.mark.parametrize("rota", ROTAS)
def test_motivo_invisivel_curto_ou_com_cartao_e_recusado(app, rota):
    rid = _preparar(app, rota, "admin")
    for m in ("​​​​​​", "abc‮def gh", "ab", "x" * 141, "cartão 4111 1111 1111 1111"):
        r = acao(app, rid, rota, "admin", motivo=m)
        assert r.status_code in (400, 422), (rota, m, r.status_code)
        assert "4111" not in r.get_data(as_text=True)


@pytest.mark.parametrize("rota,evento", [("checkin/reverter", "checkin_reverter"), ("liberar", "liberar"), ("liberar/reverter", "liberar_reverter")])
def test_motivo_fica_no_log_da_hospedagem_e_no_historico_do_admin(app, rota, evento):
    rid = _preparar(app, rota, "recepcao")
    r = acao(app, rid, rota, "recepcao", motivo="Hóspede pediu para refazer")
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    assert sql(app, "SELECT detalhe, usuario_login FROM hospedagem_evento WHERE acao=?", (evento,)) == [("Hóspede pediu para refazer", "recepcao")]
    h = cli(app, "admin").get("/api/historico?limite=50").get_json()
    h = h if isinstance(h, list) else h["itens"]
    linha = [x for x in h if x["depois"] and x["depois"].get("motivo") == "Hóspede pediu para refazer"]
    assert len(linha) == 1 and linha[0]["usuario_login"] == "recepcao" and linha[0]["em"]
    da_reserva = cli(app, "admin").get("/api/reservas/%d/historico" % rid).get_json()
    assert any(x["depois"] and x["depois"].get("motivo") == "Hóspede pediu para refazer" for x in da_reserva)


def test_historico_resumo_da_diretoria_nao_mostra_o_motivo(app):
    rid = _preparar(app, "liberar", "admin")
    acao(app, rid, "liberar", "admin", motivo="Motivo reservado da gestão")
    assert "reservado" not in cli(app, "diretoria").get("/api/historico?limite=50").get_data(as_text=True)


def test_motivo_e_rotulo_aparecem_na_tela_de_historico():
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(raiz, "static", "app.js"), encoding="utf-8").read()
    assert 'motivo:"motivo"' in js and "conta_liberada" in js and "checkin_revertido" in js
