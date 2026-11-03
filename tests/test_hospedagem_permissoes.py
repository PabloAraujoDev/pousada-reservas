"""Hospedagem: matriz de permissões dos 6 papéis em cada rota nova, máscara de dados pessoais, placa e ficha FNRH."""
import json

import pytest

from pousada.permissoes import capacidades
from tests.test_hospedagem import acao, app, cli, detalhe, nova, sql  # noqa: F401
from tests.test_hospedes import CPF, put

PAPEIS = ["admin", "atendente", "recepcao", "diretoria", "consulta", "camareira"]
VER = {"admin", "atendente", "recepcao", "diretoria", "consulta"}
RECEPCAO_E_ACIMA = {"admin", "atendente", "recepcao"}
SO_GESTAO = {"admin", "atendente"}
CAPS = {"hospedes.gerir": RECEPCAO_E_ACIMA, "checkin.registrar": RECEPCAO_E_ACIMA, "checkin.reverter": RECEPCAO_E_ACIMA,
        "conta.liberar": RECEPCAO_E_ACIMA, "ficha.imprimir": RECEPCAO_E_ACIMA, "veiculo.editar": RECEPCAO_E_ACIMA}


def test_capacidades_por_papel():
    for cap, quem in CAPS.items():
        for papel in PAPEIS:
            assert (cap in capacidades(papel)) == (papel in quem), (cap, papel)


def _status(app, papel, metodo, caminho, corpo=None):
    c = cli(app, papel, "u_" + papel)
    return getattr(c, metodo)(caminho, json=corpo) if corpo is not None else getattr(c, metodo)(caminho)


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_das_rotas_de_leitura(app, papel):
    rid = nova(app)["id"]
    esperado = 200 if papel in VER else 403
    assert _status(app, papel, "get", "/api/reservas/%d/hospedes" % rid).status_code == esperado
    assert _status(app, papel, "get", "/api/contas-abertas").status_code == esperado


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_das_rotas_de_escrita(app, papel):
    rid = nova(app)["id"]

    def v():
        return detalhe(app, rid)["versao"]

    def ok(caminho, cap, corpo=None, metodo="post"):
        r = _status(app, papel, metodo, "/api/reservas/%d/%s" % (rid, caminho), dict(corpo or {}, versao=v()))
        assert (r.status_code < 300) == (papel in CAPS[cap]), (caminho, papel, r.status_code, r.get_data(as_text=True))
        if papel not in CAPS[cap]:
            assert r.status_code == 403 and "permissão" in r.get_json()["erro"]

    ok("hospedes", "hospedes.gerir", {"titular": {}, "acompanhantes": [{"nome": "A Um"}]}, "put")
    ok("placa", "veiculo.editar", {"placa": "ABC1D23"}, "put")
    ok("checkin", "checkin.registrar")
    M = {"motivo": "Motivo do teste"}
    ok("checkin/reverter", "checkin.reverter", M)
    ok("liberar", "conta.liberar", M)
    ok("liberar/reverter", "conta.liberar", M)
    r = _status(app, papel, "post", "/api/reservas/%d/ficha" % rid, {})
    assert (r.status_code == 200) == (papel in CAPS["ficha.imprimir"])


def test_sem_csrf_e_sem_login_nas_rotas_novas(app):
    rid = nova(app)["id"]
    c = cli(app, "admin")
    for caminho in ("hospedes", "placa", "checkin", "liberar", "ficha"):
        metodo = "put" if caminho in ("hospedes", "placa") else "post"
        r = getattr(c, metodo)("/api/reservas/%d/%s" % (rid, caminho), json={"versao": 1}, sem_csrf=True)
        assert r.status_code == 403, caminho
    anon = app.test_client()
    assert anon.get("/api/contas-abertas").status_code == 401 and anon.get("/api/reservas/%d/hospedes" % rid).status_code == 401


def test_dados_pessoais_mascarados_para_diretoria_e_consulta_e_completos_para_quem_gere(app):
    rid = nova(app)["id"]
    put(app, rid, {"titular": {"documento": CPF, "nascimento": "1980-05-17", "profissao": "Médico"},
                   "acompanhantes": [{"nome": "A Um", "documento": "MG1234567", "destino": "Ouro Preto"}]})
    cli(app, "atendente").put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"], "placa": "abc-1234"})
    for papel in ("diretoria", "consulta"):
        txt = cli(app, papel).get("/api/reservas/%d/hospedes" % rid).get_data(as_text=True)
        for segredo in ("123.456", "MG123", "1980", "Médico", "Ouro Preto"):
            assert segredo not in txt, (papel, segredo)
        d = cli(app, papel).get("/api/reservas/%d/hospedes" % rid).get_json()
        assert d["titular"]["documento"].endswith("09") and d["titular"]["documento"].startswith("*") and d["pode_editar"] is False
        assert detalhe(app, rid, papel)["placa"] == "ABC****"
    for papel in ("recepcao", "atendente", "admin"):
        assert cli(app, papel).get("/api/reservas/%d/hospedes" % rid).get_json()["titular"]["documento"] == CPF
        assert detalhe(app, rid, papel)["placa"] == "ABC-1234"


@pytest.mark.parametrize("entrada,esperado", [("abc-1234", "ABC-1234"), (" ABC1234 ", "ABC-1234"), ("abc1d23", "ABC1D23"),
                                              ("ABC-1D23", "ABC1D23"), (None, None), ("", None)])
def test_placa_normalizada(app, entrada, esperado):
    rid = nova(app)["id"]
    r = cli(app, "recepcao").put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"], "placa": entrada})
    assert r.status_code == 200 and r.get_json()["placa"] == esperado


@pytest.mark.parametrize("ruim", ["AB-1234", "ABCD123", "ABC12345", "123-ABCD", "ABC 12 34 5", "ÁBC-1234", "ABC1DD3", 12345, ["ABC1234"], "x" * 40,
                                  "<script>", "4111111111111111"])
def test_placa_hostil_recusada(app, ruim):
    rid = nova(app)["id"]
    r = cli(app, "recepcao").put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"], "placa": ruim})
    assert r.status_code == 422 and detalhe(app, rid, "admin")["placa"] is None
    assert "4111" not in r.get_data(as_text=True)


def test_placa_sem_chave_nao_apaga_e_nao_vai_ao_historico(app):
    rid = nova(app)["id"]
    c = cli(app, "recepcao")
    c.put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"], "placa": "ABC1D23"})
    assert c.put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"]}).status_code == 400
    assert detalhe(app, rid)["placa"] == "ABC1D23"
    tudo = json.dumps(sql(app, "SELECT * FROM historico")) + json.dumps(sql(app, "SELECT * FROM hospedagem_evento"))
    assert "ABC1D23" not in tudo and "ABC" not in tudo
    assert c.put("/api/reservas/%d/placa" % rid, json={"versao": 1, "placa": "DEF1G23"}).status_code == 409


def test_ficha_traz_dados_completos_e_linhas_em_branco_e_registra_a_emissao(app):
    rid = nova(app, n=4)["id"]
    put(app, rid, {"titular": {"documento": CPF}, "acompanhantes": [{"nome": "A Um"}]})
    cli(app, "recepcao").put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"], "placa": "ABC1234"})
    r = cli(app, "recepcao").post("/api/reservas/%d/ficha" % rid, json={})
    d = r.get_json()
    assert d["reserva"]["placa"] == "ABC-1234" and d["reserva"]["a"] == "201" and d["titular"]["documento"] == CPF
    assert d["em_branco"] == 2 and len(d["acompanhantes"]) == 1
    assert sql(app, "SELECT acao, usuario_login FROM hospedagem_evento WHERE acao='ficha'") == [("ficha", "recepcao")]
    assert CPF not in json.dumps(sql(app, "SELECT * FROM hospedagem_evento"))


def _urls_get(app, rid):
    """Todas as rotas GET (menos estáticos, a lista de hóspedes e o detalhe da reserva), com parâmetros preenchidos."""
    import re
    urls = set()
    for regra in app.url_map.iter_rules():
        if "GET" not in regra.methods or regra.rule.startswith("/static") or regra.rule.endswith("/hospedes") or regra.rule == "/api/reservas/<int:rid>":
            continue
        urls.add(re.sub(r"<int:[a-z_]+>", str(rid), re.sub(r"<[a-z_]+>", "201", regra.rule)))
    urls |= {"/api/export.csv", "/api/export.csv?inicio=2026-10-26&dias=7", "/api/folha.pdf?inicio=2026-10-26&orientacao=retrato",
             "/api/camareiras?inicio=2026-10-26&fim=2026-11-02&estadias=1&nomes=1", "/api/reservas?canceladas=1", "/api/historico?limite=500"}
    return sorted(urls)


@pytest.mark.parametrize("papel", PAPEIS)
def test_documento_e_placa_nao_vazam_em_nenhuma_outra_rota_nem_no_historico(app, papel):
    rid = nova(app)["id"]
    put(app, rid, {"titular": {"documento": "DOC99887766", "profissao": "Profissao-Secreta"},
                   "acompanhantes": [{"nome": "Acomp Teste", "documento": "RG55443322", "destino": "Destino-Secreto"}]})
    cli(app, "admin").put("/api/reservas/%d/placa" % rid, json={"versao": detalhe(app, rid)["versao"], "placa": "QWE1R23"})
    c = cli(app, papel, "v_" + papel)
    for url in _urls_get(app, rid):
        corpo = c.get(url).get_data()
        for segredo in ("DOC99887766", "RG55443322", "Profissao-Secreta", "Destino-Secreto", "QWE1R23", "QWE-1R23"):
            assert segredo.encode() not in corpo, (papel, url, segredo)
