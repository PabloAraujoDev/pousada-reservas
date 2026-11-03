"""Cabeçalhos de segurança, CSP sem JavaScript inline e configuração de HOST."""
import importlib
import os
import re

import pytest

from pousada import config
from tests.conftest import cliente_como

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URLS = ["/login", "/api/sessao", "/api/reservas", "/static/login.js", "/api/nao-existe"]


@pytest.fixture
def logado(app):
    return cliente_como(app, "admin")


@pytest.mark.parametrize("url", URLS)
def test_cabecalhos_em_todas_as_respostas(logado, url):
    h = logado.get(url).headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    csp = h["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp


def test_cabecalhos_tambem_na_pagina_inicial_e_em_respostas_anonimas(app, logado):
    assert logado.get("/").headers["X-Frame-Options"] == "DENY"
    anonimo = app.test_client().get("/api/reservas")                  # 401
    assert anonimo.status_code == 401 and anonimo.headers["X-Content-Type-Options"] == "nosniff"


def test_csp_nao_permite_script_inline(logado):
    csp = logado.get("/login").headers["Content-Security-Policy"]
    script = [d for d in csp.split(";") if d.strip().startswith("script-src")][0]
    assert script.strip() == "script-src 'self'"                       # sem 'unsafe-inline' nem 'unsafe-eval'
    assert "unsafe" not in csp
    assert "http://" not in csp and "https://" not in csp               # nenhum terceiro: tudo vem do próprio sistema


@pytest.mark.parametrize("pagina", ["index.html", "login.html"])
def test_paginas_nao_tem_script_nem_estilo_nem_evento_inline(pagina):
    with open(os.path.join(RAIZ, "static", pagina), encoding="utf-8") as fh:
        html = fh.read()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "script inline"
    assert "<style" not in html and not re.search(r"\sstyle=", html)
    assert not re.search(r"\son[a-z]+=", html), "manipulador de evento inline (onclick...)"


def test_js_nao_gera_estilo_inline():
    for arq in ("app.js", "login.js"):
        with open(os.path.join(RAIZ, "static", arq), encoding="utf-8") as fh:
            js = fh.read()
        assert not re.search(r"style=[\"'\\]", js), arq


def test_cache_no_store_na_api(logado):
    for url in ("/api/reservas", "/api/sessao", "/api/nao-existe", "/api/export.csv"):
        assert logado.get(url).headers["Cache-Control"] == "no-store", url
    assert logado.post("/api/reservas", json={}).headers["Cache-Control"] == "no-store"


def test_host_padrao_so_este_computador(monkeypatch):
    monkeypatch.delenv("POUSADA_HOST", raising=False)
    monkeypatch.delenv("TRUSTED_HOSTS", raising=False)
    try:
        novo = importlib.reload(config)
        assert novo.HOST == "127.0.0.1" and novo.TRUSTED_HOSTS == []
        monkeypatch.setenv("POUSADA_HOST", "0.0.0.0")
        monkeypatch.setenv("TRUSTED_HOSTS", "pousada.local, 192.168.0.10")
        novo = importlib.reload(config)
        assert novo.HOST == "0.0.0.0" and novo.TRUSTED_HOSTS == ["pousada.local", "192.168.0.10"]
    finally:
        monkeypatch.undo()
        importlib.reload(config)
