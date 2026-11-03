"""Relatório de ocupação (API e PDF): permissões dos 6 papéis, nomes só para quem pode, sem valores, entradas hostis, limites."""
import re

import pytest

from pousada.db import conectar
from pousada.regras import agora
from tests.conftest import cliente_como

PAPEIS = ("admin", "atendente", "recepcao", "camareira", "diretoria", "consulta")
COM_NOMES = {"admin", "atendente", "recepcao", "diretoria", "consulta"}        # têm reservas.ver; a camareira só ver_resumo
URL = "/api/ocupacao?inicio=2026-10-10&fim=2026-10-16"
XSS = "<img src=x onerror=alert(1)>&\"'</para><font"


@pytest.fixture
def com_dados(app):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,diaria_centavos) "
                    "VALUES ('201',?,'',2,'2026-10-11','2026-10-14','pendente','OBS-SECRETA','Turma Azul',?,?,1,45000)", (XSS, agora(), agora()))
    finally:
        con.close()
    return app


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_json_e_pdf_para_os_6_papeis(com_dados, papel):
    c = cliente_como(com_dados, papel)
    r = c.get(URL)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    texto = r.get_data(as_text=True)
    assert ("Turma Azul" in texto) == (papel in COM_NOMES)               # camareira não vê nome nem grupo
    assert r.json["com_nomes"] == (papel in COM_NOMES)
    for proibido in ("45000", "diaria", "OBS-SECRETA", "pendente", "extras"):       # nunca valor, observação ou pagamento
        assert proibido not in texto
    p = c.get(URL.replace("/api/ocupacao", "/api/ocupacao.pdf"))
    assert p.status_code == 200 and p.data.startswith(b"%PDF") and p.headers["Cache-Control"] == "no-store"
    assert "attachment" in p.headers["Content-Disposition"] and "ocupacao_2026-10-10_a_2026-10-16.pdf" in p.headers["Content-Disposition"]
    assert b"OBS-SECRETA" not in p.data


@pytest.mark.parametrize("rota", ["/api/ocupacao", "/api/ocupacao.pdf"])
def test_sem_login_da_401(com_dados, rota):
    r = com_dados.test_client().get(rota + "?inicio=2026-10-10&fim=2026-10-11")
    assert r.status_code == 401 and r.is_json


def test_usuario_sem_capacidade_da_403(com_dados, monkeypatch):
    from pousada import permissoes
    monkeypatch.setitem(permissoes.PERMISSOES, "consulta", frozenset({"folha.ver"}))      # sem reservas.ver nem ver_resumo
    c = cliente_como(com_dados, "consulta")
    assert c.get(URL).status_code == 403 and c.get("/api/ocupacao.pdf?inicio=2026-10-10&fim=2026-10-11").status_code == 403


def test_xss_no_nome_vai_cru_no_json_e_escapado_no_pdf(com_dados):
    c = cliente_como(com_dados, "admin")
    linha = next(u for u in c.get(URL).json["blocos"][0]["linhas"] if u["a"] == "201")
    assert linha["celulas"][0]["nome"] == XSS                  # o servidor devolve o texto como está; a tela escapa (esc) e o PDF também
    assert c.get("/api/ocupacao.pdf?inicio=2026-10-10&fim=2026-10-16&orientacao=retrato").status_code == 200


def test_limites_de_periodo(com_dados):
    c = cliente_como(com_dados, "admin")
    assert c.get("/api/ocupacao?inicio=2026-10-01&fim=2026-12-31").status_code == 200          # 92 dias
    r = c.get("/api/ocupacao?inicio=2026-10-01&fim=2027-01-01")                                # 93 dias
    assert r.status_code == 400 and "máximo 92" in r.json["erro"]
    assert c.get("/api/ocupacao.pdf?inicio=2026-10-01&fim=2027-01-01").status_code == 400
    assert c.get("/api/ocupacao?inicio=2026-10-01&fim=2026-10-01").json["resumo"]["dias"] == 1


def test_pdf_de_92_dias_tem_varias_paginas_por_orientacao(com_dados):
    c = cliente_como(com_dados, "admin")
    paginas = {}
    for o in ("paisagem", "retrato"):
        pdf = c.get("/api/ocupacao.pdf?inicio=2026-10-01&fim=2026-12-31&orientacao=" + o).data
        paginas[o] = len(re.findall(rb"/Type /Page\b(?!s)", pdf))
    assert paginas == {"paisagem": 7, "retrato": 14}


HOSTIS = ["", "inicio=2026-10-10", "fim=2026-10-10", "inicio=&fim=", "inicio=abc&fim=def", "inicio=2026-13-01&fim=2026-13-02",
          "inicio=2026-10-10&fim=2026-10-09", "inicio=2026-10-10' OR '1'='1&fim=2026-10-11", "inicio=2026-10-10;DROP TABLE reservas&fim=2026-10-11",
          "inicio=../../etc/passwd&fim=2026-10-11", "inicio=2026-10-10%00&fim=2026-10-11", "inicio=2026-10-10%0a&fim=2026-10-11",
          "inicio[]=2026-10-10&fim[]=2026-10-11", "inicio=99999999999999999999&fim=2026-10-11", "inicio=0000-01-01&fim=9999-12-31",
          "inicio=2026-10-10&fim=2026-10-11&orientacao=diagonal", "inicio=2026-10-10&fim=2026-10-11&orientacao=paisagem%00",
          "inicio=%EF%BC%92026-10-10&fim=2026-10-11", "inicio=2026-10-10&fim=2026-10-11&orientacao=" + "x" * 5000,
          "inicio=" + "9" * 5000 + "&fim=2026-10-11"]


@pytest.mark.parametrize("consulta", HOSTIS)
@pytest.mark.parametrize("rota", ["/api/ocupacao", "/api/ocupacao.pdf"])
def test_entradas_hostis_sempre_400_sem_500(com_dados, rota, consulta):
    c = cliente_como(com_dados, "admin")
    r = c.get(rota + "?" + consulta)
    assert r.status_code == 400 and r.is_json and "erro" in r.json
    assert "Traceback" not in r.get_data(as_text=True) and "sqlite" not in r.get_data(as_text=True).lower()
    n = conectar(com_dados.config["CAMINHO_BANCO"]).execute("SELECT COUNT(*) FROM reservas").fetchone()[0]
    assert n == 1                                                                              # nada foi alterado


def test_parametros_repetidos_usam_o_primeiro_sem_estourar(com_dados):
    c = cliente_como(com_dados, "admin")
    r = c.get("/api/ocupacao?inicio=2026-10-10&inicio=2020-01-01&fim=2026-10-11&fim=2030-01-01")
    assert r.status_code == 200 and r.json["inicio"] == "2026-10-10" and r.json["fim"] == "2026-10-11"


@pytest.mark.parametrize("metodo", ["post", "put", "delete", "patch"])
def test_somente_leitura(com_dados, metodo):
    c = cliente_como(com_dados, "admin")
    assert getattr(c, metodo)("/api/ocupacao").status_code in (404, 405)
    assert getattr(c, metodo)("/api/ocupacao.pdf").status_code in (404, 405)


def test_cabecalhos_de_seguranca_e_emitido_por(com_dados):
    r = cliente_como(com_dados, "recepcao").get(URL)
    assert "script-src 'self'" in r.headers["Content-Security-Policy"] and "'unsafe-inline'" not in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.json["emitido_por"] == "Recepcao"


def test_nao_ha_idor_nem_parametro_de_id(com_dados):
    """O relatório não recebe ids; parâmetros extras (id, usuario, valores) são ignorados e nada sai a mais."""
    c = cliente_como(com_dados, "camareira")
    r = c.get(URL + "&id=1&nomes=1&valores=1&com_nomes=1&usuario=admin")
    assert r.status_code == 200 and r.json["com_nomes"] is False and "Turma Azul" not in r.get_data(as_text=True)
