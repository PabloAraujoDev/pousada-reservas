"""Login, logout, sessão, negação por padrão e proteção CSRF."""
import io
from datetime import timedelta

import pytest

from pousada.db import conectar
from tests.conftest import SENHA, cliente_como, inserir_usuario


def novo_visitante(app):
    """Cliente sem login, mas com o token CSRF que a tela de login obtém em /api/sessao."""
    c = app.test_client()
    c.csrf = c.get("/api/sessao").get_json()["csrf"]
    return c


def entrar(app, login, senha=SENHA):
    c = novo_visitante(app)
    r = c.post("/api/login", json={"login": login, "senha": senha})
    if r.status_code == 200:
        c.csrf = r.get_json()["csrf"]
    return c, r


# ---------------------------------------------------------------- negar por padrão

def test_anonimo_nao_acessa_nada_da_api(app):
    c = app.test_client()
    for metodo, url in [("get", "/api/reservas"), ("get", "/api/camareiras"), ("get", "/api/pedidos"),
                        ("get", "/api/export.csv"), ("post", "/api/reservas"), ("post", "/api/importar"),
                        ("post", "/api/logout")]:
        r = getattr(c, metodo)(url)
        assert r.status_code == 401, url
        assert r.get_json() == {"erro": "É preciso entrar no sistema"}


def test_paginas_e_estaticos(app):
    c = app.test_client()
    r = c.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert c.get("/login").status_code == 200
    assert c.get("/static/login.js").status_code == 200
    assert c.get("/static/app.css").status_code == 200
    assert c.get("/static/index.html").status_code == 302        # o resto de /static exige login
    assert c.get("/static/app.js").status_code == 302
    logado = cliente_como(app, "admin")
    assert logado.get("/").status_code == 200
    assert logado.get("/login").status_code == 302                # já logado volta para o sistema


def test_sessao_sem_usuario_no_banco_pede_criar_admin(app):
    j = app.test_client().get("/api/sessao").get_json()
    assert j["autenticado"] is False and j["existe_usuario"] is False and j["csrf"]
    page = app.test_client().get("/static/login.js").get_data(as_text=True)
    assert "criar-admin" in page


# ---------------------------------------------------------------- login e sessão

def test_login_ok_e_cookie_seguro(app):
    inserir_usuario(app, "atendente", "maria")
    c, r = entrar(app, "MARIA")                                  # login não diferencia maiúsculas
    assert r.status_code == 200
    j = r.get_json()
    assert j["autenticado"] and j["usuario"]["papel"] == "atendente" and "senha_hash" not in str(j)
    cookie = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("pousada_sessao=")][0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Expires=" in cookie
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=10)
    assert c.get("/api/reservas").status_code == 200
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert con.execute("SELECT ultimo_login FROM usuarios WHERE login='maria'").fetchone()[0]
    finally:
        con.close()


def test_login_errado_mensagem_generica(app):
    inserir_usuario(app, "atendente", "maria")
    _, r1 = entrar(app, "maria", "senha-errada-123")
    _, r2 = entrar(app, "fantasma", SENHA)
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json() == r2.get_json() == {"erro": "Login ou senha inválidos"}


def test_usuario_inativo_nao_entra_e_desativar_vale_na_hora(app):
    inserir_usuario(app, "atendente", "inativo", ativo=0)
    assert entrar(app, "inativo")[1].status_code == 401
    inserir_usuario(app, "atendente", "maria")
    c, r = entrar(app, "maria")
    assert c.get("/api/reservas").status_code == 200
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("UPDATE usuarios SET ativo=0 WHERE login='maria'")
    finally:
        con.close()
    assert c.get("/api/reservas").status_code == 401             # sem esperar o cookie vencer


def test_trocar_senha_invalida_sessoes_antigas(app):
    inserir_usuario(app, "atendente", "maria")
    antigo, _ = entrar(app, "maria")
    novo, _ = entrar(app, "maria")
    r = novo.post("/api/senha", json={"atual": SENHA, "nova": "outra-senha-forte-1"})
    assert r.status_code == 200
    novo.csrf = r.get_json()["csrf"]
    assert novo.get("/api/reservas").status_code == 200
    assert antigo.get("/api/reservas").status_code == 401
    assert entrar(app, "maria", SENHA)[1].status_code == 401
    assert entrar(app, "maria", "outra-senha-forte-1")[1].status_code == 200


def test_senha_nova_curta_recusada(app):
    inserir_usuario(app, "atendente", "maria")
    c, _ = entrar(app, "maria")
    assert c.post("/api/senha", json={"atual": SENHA, "nova": "curta"}).status_code == 400
    assert c.post("/api/senha", json={"atual": "errada-errada", "nova": "outra-senha-forte-1"}).status_code == 400


def test_usuario_com_trocar_senha_so_acessa_troca(app):
    inserir_usuario(app, "atendente", "novato", trocar_senha=1)
    c, r = entrar(app, "novato")
    assert r.get_json()["usuario"]["trocar_senha"] is True
    bloqueado = c.get("/api/reservas")
    assert bloqueado.status_code == 403 and bloqueado.get_json()["trocar_senha"] is True
    assert c.post("/api/senha", json={"atual": SENHA, "nova": "senha-nova-forte-9"}).status_code == 200


def test_logout_encerra_a_sessao(app):
    c = cliente_como(app, "admin")
    assert c.post("/api/logout").status_code == 200
    assert c.get("/api/reservas").status_code == 401


# ---------------------------------------------------------------- CSRF, Content-Type, Origin

def test_csrf_exigido_nos_pedidos_que_alteram(app):
    c = cliente_como(app, "admin")
    corpo = {"a": "201", "nome": "X", "n": 1, "i": "2026-10-10", "f": "2026-10-11"}
    assert c.post("/api/reservas", json=corpo, sem_csrf=True).status_code == 403
    assert c.post("/api/reservas", json=corpo, headers={"X-CSRF-Token": "errado"}).status_code == 403
    assert c.post("/api/reservas", json=corpo, headers={"X-CSRF-Token": ""}).status_code == 403
    assert c.post("/api/reservas", json=corpo).status_code == 201
    # leitura não precisa de token
    assert c.get("/api/reservas", headers={}).status_code == 200


def test_content_type_precisa_ser_json(app):
    c = cliente_como(app, "admin")
    r = c.post("/api/reservas", data="a=1", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 415
    r = c.post("/api/reservas", data="{}", content_type="text/plain")
    assert r.status_code == 415


def test_multipart_so_no_upload_da_planilha(app):
    c = cliente_como(app, "admin")
    def arq():
        return {"arquivo": (io.BytesIO(b"abc"), "x.txt")}
    assert c.post("/api/reservas", data=arq(), content_type="multipart/form-data").status_code == 415
    # na rota de upload o multipart é aceito (e o arquivo inválido é recusado depois, com 400)
    assert c.post("/api/importar/previa", data=arq(), content_type="multipart/form-data").status_code == 400
    # mas o token CSRF continua obrigatório
    assert c.post("/api/importar/previa", data={"arquivo": (io.BytesIO(b"abc"), "x.xlsx")},
                  content_type="multipart/form-data", sem_csrf=True).status_code == 403


def test_origin_precisa_ser_o_mesmo_site(app):
    c = cliente_como(app, "admin")
    corpo = {"a": "201", "nome": "X", "n": 1, "i": "2026-10-10", "f": "2026-10-11"}
    assert c.post("/api/reservas", json=corpo, headers={"Origin": "http://site-malvado.com"}).status_code == 403
    assert c.post("/api/reservas", json=corpo, headers={"Origin": "null"}).status_code == 403
    assert c.post("/api/reservas", json=dict(corpo, a="202"), headers={"Origin": "http://localhost"}).status_code == 201


def test_login_tambem_exige_csrf(app):
    inserir_usuario(app, "atendente", "maria")
    c = app.test_client()                                         # nunca pegou o token
    assert c.post("/api/login", json={"login": "maria", "senha": SENHA}).status_code == 403


def test_trusted_hosts(tmp_path):
    from tests.conftest import criar_app_teste
    a = criar_app_teste(tmp_path, TRUSTED_HOSTS=["pousada.local"])
    c = a.test_client()
    assert c.get("/api/sessao").status_code == 400                # Host "localhost" não está na lista
    assert c.get("/api/sessao", headers={"Host": "pousada.local:5000"}).status_code == 200


# ---------------------------------------------------------------- passo 4: limite de tentativas

def test_cinco_falhas_bloqueiam_ate_a_senha_certa(app):
    inserir_usuario(app, "atendente", "maria")
    for _ in range(5):
        assert entrar(app, "maria", "senha-errada-123")[1].status_code == 401
    r = entrar(app, "maria", "senha-errada-123")[1]
    assert r.status_code == 429
    assert entrar(app, "maria", SENHA)[1].status_code == 429          # nem a senha certa passa enquanto bloqueado


def test_bloqueio_vale_por_login_e_por_ip(app):
    inserir_usuario(app, "atendente", "maria")
    inserir_usuario(app, "atendente", "joana")
    for _ in range(5):
        entrar(app, "maria", "errada-errada-1")
    assert entrar(app, "joana", SENHA)[1].status_code == 200          # outro login: livre
    c = novo_visitante(app)
    r = c.post("/api/login", json={"login": "maria", "senha": SENHA}, environ_overrides={"REMOTE_ADDR": "10.9.9.9"})
    assert r.status_code == 200                                       # outro IP: livre


def test_bloqueio_expira_depois_da_janela(app):
    inserir_usuario(app, "atendente", "maria")
    for _ in range(5):
        entrar(app, "maria", "errada-errada-1")
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("UPDATE tentativas_login SET em='2000-01-01 00:00:00'")
    finally:
        con.close()
    assert entrar(app, "maria", SENHA)[1].status_code == 200


def test_login_inexistente_tambem_conta_e_mensagem_igual(app):
    for _ in range(5):
        r = entrar(app, "fantasma", "qualquer-senha-1")[1]
        assert r.status_code == 401 and r.get_json() == {"erro": "Login ou senha inválidos"}
    assert entrar(app, "fantasma", "qualquer-senha-1")[1].status_code == 429


def test_sucesso_zera_as_falhas(app):
    inserir_usuario(app, "atendente", "maria")
    for _ in range(4):
        entrar(app, "maria", "errada-errada-1")
    assert entrar(app, "maria", SENHA)[1].status_code == 200
    for _ in range(4):
        assert entrar(app, "maria", "errada-errada-1")[1].status_code == 401


def test_login_inexistente_gasta_o_mesmo_tempo_de_um_hash(app, monkeypatch):
    """Com login inexistente o sistema ainda confere um hash (falso), para não revelar quais logins existem."""
    chamadas = []
    import pousada.usuarios as u
    original = u.check_password_hash
    monkeypatch.setattr(u, "check_password_hash", lambda h, s: chamadas.append(h) or original(h, s))
    entrar(app, "fantasma", "qualquer-senha-1")
    assert len(chamadas) == 1
