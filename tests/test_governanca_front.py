"""Governança: o que dá para conferir sem navegador (lógica pura em node, menu, CSP, arquivos estáticos protegidos)."""
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import cliente_como, criar_app_teste

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICO = os.path.join(RAIZ, "static")


def ler(nome):
    with open(os.path.join(ESTATICO, nome), encoding="utf-8") as fh:
        return fh.read()


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_logica_pura_da_governanca_no_node():
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", "governanca_logica.js")],
                       capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_menu_governanca_vem_antes_de_camareiras_e_exige_a_capacidade():
    html = ler("index.html")
    botoes = re.findall(r'<button data-aba="(\w+)"[^>]*data-cap="([^"]*)"', html)
    abas = [b[0] for b in botoes]
    assert abas.index("governanca") < abas.index("camareiras")
    assert dict(botoes)["governanca"] == "governanca.ver"
    assert 'data-menu="governanca"' in html and 'id="aba-governanca"' in html


def test_sem_script_nem_estilo_inline_e_scripts_so_do_proprio_site():
    html = ler("index.html")
    assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", html)
    assert not re.search(r"\son\w+\s*=", html) and "style=" not in html
    assert '/static/governanca_logica.js' in html and '/static/governanca.js' in html
    assert "http://" not in html and "https://" not in html


def test_javascript_da_governanca_nao_usa_html_sem_escape():
    """Todo texto do servidor entra por esc() ou textContent; nada de eval, document.write ou estilo inline."""
    for nome in ("governanca.js", "governanca_logica.js"):
        js = ler(nome)
        assert not re.search(r"\beval\(|document\.write|new Function|\.style\.cssText|setAttribute\(\s*[\"']style", js), nome
    js = ler("governanca.js")
    # cada atribuição a innerHTML monta o HTML por funções gvHtml*/gvHtmlImpressao (que usam esc) ou limpa/zera o conteúdo
    for m in re.finditer(r"\.innerHTML\s*=\s*([^;]+);", js):
        assert re.match(r"(gvHtml\w+\(|\"\"|'')", m.group(1).strip()), m.group(0)


def test_obs_e_login_do_servidor_so_com_textcontent_ou_esc():
    js = ler("governanca.js")
    assert "esc(texto)" in js and "esc(n)" in js
    assert "esc(e.por" not in js and "li.textContent = t" in js      # o histórico usa textContent


def test_arquivos_da_governanca_exigem_login(tmp_path):
    app = criar_app_teste(tmp_path)
    cam = cliente_como(app, "camareira")
    for nome in ("governanca.js", "governanca_logica.js"):
        assert app.test_client().get("/static/" + nome).status_code in (302, 401)
        assert cam.get("/static/" + nome).status_code == 200


def test_csp_continua_estrita_na_pagina_principal(tmp_path):
    app = criar_app_teste(tmp_path)
    csp = cliente_como(app, "camareira").get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "style-src 'self'" in csp and "unsafe-inline" not in csp


def test_camareira_desfaz_a_propria_marcacao_de_iniciar(tmp_path):
    from tests.test_governanca import acao, fazer_app, hora, sql, unidade, versao
    app = fazer_app(tmp_path)
    sql(app, "UPDATE governanca_unidade SET situacao='suja' WHERE unidade='203'")
    cam = cliente_como(app, "camareira")
    acao(cam, "iniciar", [("203", versao(cam, "203"))])
    assert "suja" in unidade(cam, "203")["pode"]
    assert acao(cam, "suja", [("203", versao(cam, "203"))]).status_code == 200
    assert unidade(cam, "203")["situacao"] == "suja"
