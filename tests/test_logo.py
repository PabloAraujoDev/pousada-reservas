"""Logo do clube: aparece no cabeçalho, no login e no PDF, e o arquivo é público (a tela de login precisa dele)."""
from pousada import folha_pdf


def test_logo_e_publica_para_a_tela_de_login(app):
    r = app.test_client().get("/static/logo.png")
    assert r.status_code == 200
    assert r.mimetype == "image/png"
    assert r.data.startswith(b"\x89PNG")
    assert len(r.data) < 150 * 1024          # leve para carregar na rede da pousada


def test_outros_estaticos_continuam_protegidos(app):
    assert app.test_client().get("/static/app.js").status_code in (401, 302)


def test_login_e_cabecalho_mostram_a_logo_ao_lado_do_nome(cli, app):
    login = app.test_client().get("/login").get_data(as_text=True)
    assert 'src="/static/logo.png"' in login and "Pousada Boa Esperança" in login
    assert login.index("logo.png") < login.index("<h1>")
    pagina = cli.get("/").get_data(as_text=True)
    assert 'class="logo"' in pagina and pagina.index("logo.png") < pagina.index("<h1>")
    assert 'alt="' in pagina                  # texto alternativo para leitores de tela


def test_logo_nao_usa_estilo_inline(cli):
    """A política de segurança não permite style="..." no HTML."""
    assert "style=" not in cli.get("/").get_data(as_text=True)


def test_pdf_leva_a_logo(cli):
    pdf = cli.get("/api/folha.pdf?inicio=2026-10-05").data
    assert b"/Subtype /Image" in pdf or b"/Subtype/Image" in pdf


def test_pdf_sai_sem_a_logo_se_o_arquivo_faltar(cli, monkeypatch):
    monkeypatch.setattr(folha_pdf, "ARQUIVO_LOGO", "/nao/existe/logo.png")
    r = cli.get("/api/folha.pdf?inicio=2026-10-05")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    assert b"/Subtype /Image" not in r.data and b"/Subtype/Image" not in r.data
