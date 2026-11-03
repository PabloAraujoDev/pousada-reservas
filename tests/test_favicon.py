"""Ícone da aba do navegador (favicon): a logo do clube, público para a tela de login e leve."""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONES = {"favicon.ico": ("image/x-icon", b"\x00\x00\x01\x00"), "icon-192.png": ("image/png", b"\x89PNG"),
          "apple-touch-icon.png": ("image/png", b"\x89PNG")}


@pytest.mark.parametrize("nome", sorted(ICONES))
def test_icone_e_publico_e_leve(app, nome):
    tipo, assinatura = ICONES[nome]
    r = app.test_client().get("/static/" + nome)
    assert r.status_code == 200
    assert r.data.startswith(assinatura)
    assert "icon" in r.mimetype or r.mimetype == tipo
    assert len(r.data) < 50 * 1024
    assert "Set-Cookie" not in r.headers


@pytest.mark.parametrize("pagina", ["index.html", "login.html"])
def test_paginas_apontam_para_os_icones(pagina):
    with open(os.path.join(RAIZ, "static", pagina), encoding="utf-8") as fh:
        html = fh.read()
    assert 'rel="icon" href="/static/favicon.ico"' in html
    assert 'rel="apple-touch-icon" href="/static/apple-touch-icon.png"' in html
    for caminho in re.findall(r'href="(/static/(?:favicon\.ico|icon-[^"]+|apple-touch-icon\.png))"', html):
        assert os.path.isfile(os.path.join(RAIZ, caminho.lstrip("/"))), caminho


def test_favicon_ico_tem_os_tres_tamanhos():
    from PIL import Image
    with Image.open(os.path.join(RAIZ, "static", "favicon.ico")) as ico:
        assert {(16, 16), (32, 32), (48, 48)} <= set(ico.info["sizes"])


def test_outros_arquivos_continuam_protegidos(app):
    assert app.test_client().get("/static/app.js").status_code in (302, 401)
