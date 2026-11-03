"""Privacidade: o navegador de quem usa o sistema não contata terceiros (nem o Google), e arquivos públicos não deixam rastro."""
import os
import re

import pytest

from pousada.seguranca import FONTES_PUBLICAS, POLITICA_CSP, POLITICA_CSP_HTTPS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICOS = os.path.join(RAIZ, "static")
_URL_EXTERNA = re.compile(r"""(?:https?:)?//(?!localhost)[a-z0-9.-]+\.[a-z]{2,}""", re.I)


def _ler(nome):
    with open(os.path.join(ESTATICOS, nome), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.parametrize("arquivo", ["index.html", "login.html", "app.css", "app.js", "login.js"])
def test_front_nao_cita_nenhum_servidor_de_terceiros(arquivo):
    """Nenhuma página, folha de estilo ou script aponta para outro domínio (fontes, CDN, rastreadores)."""
    texto = _ler(arquivo)
    for achado in _URL_EXTERNA.findall(texto):
        pytest.fail("%s cita um endereço externo: %s" % (arquivo, achado))
    assert "googleapis" not in texto and "gstatic" not in texto


def test_politica_de_seguranca_so_aceita_o_proprio_sistema():
    for csp in (POLITICA_CSP, POLITICA_CSP_HTTPS):
        assert "http://" not in csp and "https://" not in csp and "*" not in csp
        for diretiva in ("style-src", "font-src", "img-src", "connect-src"):
            valor = [d for d in csp.split(";") if d.strip().startswith(diretiva)][0]
            assert "'self'" in valor


def test_css_declara_as_fontes_locais_e_os_arquivos_existem():
    css = _ler("app.css")
    caminhos = re.findall(r"url\((/static/fonts/[^)]+)\)", css)
    assert len(caminhos) == 2
    for c in caminhos:
        arquivo = os.path.join(ESTATICOS, c[len("/static/"):])
        assert os.path.isfile(arquivo), c
        with open(arquivo, "rb") as fh:
            assert fh.read(4) == b"wOF2", c                      # é mesmo uma fonte WOFF2
        assert c[len("/static/"):] in FONTES_PUBLICAS


def test_fontes_sao_publicas_para_a_tela_de_login(app):
    c = app.test_client()
    for nome in FONTES_PUBLICAS:
        r = c.get("/static/" + nome)
        assert r.status_code == 200 and r.data[:4] == b"wOF2", nome
        assert "woff2" in r.mimetype
        assert r.headers["Cache-Control"] == "public, max-age=604800"
        assert "Set-Cookie" not in r.headers                    # arquivo público não cria cookie nem rastro
        assert "https://" not in r.headers["Content-Security-Policy"]


def test_outros_arquivos_de_fonts_continuam_protegidos(app):
    c = app.test_client()
    assert c.get("/static/fonts/qualquer-outra.woff2").status_code in (302, 401, 404)
    assert c.get("/static/fonts/").status_code in (302, 401, 404)
    assert c.get("/static/fonts/../app.js").status_code in (302, 401, 404)
    assert c.get("/static/app.js").status_code in (302, 401)


def test_arquivos_publicos_nao_criam_cookie(app):
    c = app.test_client()
    for url in ("/static/logo.png", "/static/app.css", "/static/login.js"):
        r = c.get(url)
        assert r.status_code == 200 and "Set-Cookie" not in r.headers, url


def test_paginas_nao_vazam_a_origem_para_outros_sites(app):
    """Referrer-Policy: se algum dia houver link externo, o endereço do sistema não vai junto."""
    r = app.test_client().get("/login")
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "preconnect" not in r.get_data(as_text=True)         # nenhuma conexão antecipada a terceiros


def test_dados_de_hospedes_nao_vao_na_url(cli):
    """Busca e filtros acontecem na tela: nome, telefone e observação nunca viajam em endereço (ficariam em logs)."""
    js = _ler("app.js")
    urls = re.findall(r'api\("GET",\s*"([^"]+)"', js) + re.findall(r'"(/api/[^"]*\?[^"]*)"', js)
    for u in urls:
        assert not re.search(r"[?&](nome|busca|q|telefone|contato|obs|observa)", u, re.I), u
