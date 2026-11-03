"""Hardening: cabeçalhos em HTTPS, ProxyFix opt-in, cookie Secure, recusa de config insegura, logs."""
import logging
import os

import pytest

from pousada import config as cfg
from tests.conftest import SENHA, cliente_como, criar_app_teste, inserir_usuario

HOSTS = ["reservapousadaboaesperanca.com.br", "www.reservapousadaboaesperanca.com.br"]
CHAVE_BOA = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
SITE = "https://reservapousadaboaesperanca.com.br"


def _prod(tmp_path, **extra):
    c = dict(SERVIDOR=True, HTTPS=True, PROXY=True, TRUSTED_HOSTS=HOSTS, SECRET_KEY=CHAVE_BOA)
    c.update(extra)
    return criar_app_teste(tmp_path, **c)


# ------------------------------------------------------------ cabeçalhos

def test_modo_local_nao_tem_hsts_nem_secure(app):
    r = app.test_client().get("/login")
    assert "Strict-Transport-Security" not in r.headers
    assert "upgrade-insecure-requests" not in r.headers["Content-Security-Policy"]
    assert app.config["SESSION_COOKIE_NAME"] == "pousada_sessao" and not app.config["SESSION_COOKIE_SECURE"]


def test_cabecalhos_novos_sempre(app):
    h = app.test_client().get("/login").headers
    assert "camera=()" in h["Permissions-Policy"] and "geolocation=()" in h["Permissions-Policy"]
    assert h["Cross-Origin-Opener-Policy"] == "same-origin"
    assert h["Cross-Origin-Resource-Policy"] == "same-origin"
    assert h["Server"] == "pousada"


def test_https_liga_hsts_csp_e_cookie_seguro(tmp_path):
    a = _prod(tmp_path)
    h = a.test_client().get("/login", base_url=SITE).headers
    assert h["Strict-Transport-Security"].startswith("max-age=31536000")
    assert "upgrade-insecure-requests" in h["Content-Security-Policy"]
    assert "https://" not in h["Content-Security-Policy"]                # nenhum terceiro (fontes são locais)
    assert a.config["SESSION_COOKIE_SECURE"] is True
    assert a.config["SESSION_COOKIE_NAME"] == "__Host-pousada_sessao"


def test_cookie_de_sessao_https_tem_secure_httponly_e_prefixo_host(tmp_path):
    a = _prod(tmp_path)
    inserir_usuario(a, "admin")
    c = a.test_client()
    c.csrf = c.get("/api/sessao", base_url=SITE).get_json()["csrf"]
    r = c.post("/api/login", json={"login": "admin", "senha": SENHA},
               base_url=SITE, headers={"Origin": SITE})
    assert r.status_code == 200, r.get_data(as_text=True)
    ck = [x for x in r.headers.getlist("Set-Cookie") if x.startswith("__Host-pousada_sessao=")][0]
    assert "Secure" in ck and "HttpOnly" in ck and "SameSite=Lax" in ck
    assert "Domain" not in ck and "Path=/" in ck


def test_api_csv_sem_cache_e_estatico_revalida(app):
    c = cliente_como(app, "admin")
    assert c.get("/api/export.csv").headers["Cache-Control"] == "no-store"
    assert c.get("/static/login.js").headers["Cache-Control"] == "no-cache"
    assert c.get("/").headers["Cache-Control"] == "no-store"


# ------------------------------------------------------------ host e proxy

def test_host_invalido_da_400_em_producao(tmp_path):
    c = _prod(tmp_path).test_client()
    assert c.get("/login", base_url="https://evil.example").status_code == 400
    assert c.get("/login", base_url="https://www.reservapousadaboaesperanca.com.br").status_code == 200


def _rota_eco(app, visto):
    from flask import request

    @app.route("/eco")
    def eco():
        visto.append((request.remote_addr, request.host, request.scheme))
        return "ok"
    app.view_functions["eco"]._publico = True


def test_proxyfix_so_com_opt_in(tmp_path):
    forjado = {"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Host": "reservapousadaboaesperanca.com.br",
               "X-Forwarded-Proto": "https"}
    v_sem, v_com = [], []
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    sem = criar_app_teste(tmp_path / "a")
    com = criar_app_teste(tmp_path / "b", PROXY=True)
    _rota_eco(sem, v_sem)
    _rota_eco(com, v_com)
    sem.test_client().get("/eco", headers=forjado, environ_overrides={"REMOTE_ADDR": "10.0.0.5"})
    assert v_sem == [("10.0.0.5", "localhost", "http")]               # sem opt-in: X-Forwarded-* ignorado
    com.test_client().get("/eco", headers=forjado, environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert v_com == [("6.6.6.6", "reservapousadaboaesperanca.com.br", "https")]


def test_trusted_hosts_vale_para_o_host_vindo_do_proxy(tmp_path):
    r = _prod(tmp_path).test_client().get(
        "/login", headers={"X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https"})
    assert r.status_code == 400


# ------------------------------------------------------------ recusa de config insegura

def test_servidor_exige_trusted_hosts():
    with pytest.raises(cfg.ConfigInsegura, match="TRUSTED_HOSTS"):
        cfg.validar_servidor({"HTTPS": True, "PROXY": True, "TRUSTED_HOSTS": []})


def test_servidor_exige_https_e_proxy():
    with pytest.raises(cfg.ConfigInsegura, match="POUSADA_HTTPS"):
        cfg.validar_servidor({"TRUSTED_HOSTS": HOSTS})
    with pytest.raises(cfg.ConfigInsegura, match="POUSADA_PROXY"):
        cfg.validar_servidor({"TRUSTED_HOSTS": HOSTS, "HTTPS": True})
    cfg.validar_servidor({"TRUSTED_HOSTS": HOSTS, "PERMITIR_HTTP": True})     # rede interna: permitido
    cfg.validar_servidor({"TRUSTED_HOSTS": HOSTS, "HTTPS": True, "PROXY": True})


def test_create_app_recusa_config_insegura(tmp_path):
    with pytest.raises(cfg.ConfigInsegura):
        criar_app_teste(tmp_path, SERVIDOR=True)
    with pytest.raises(cfg.ConfigInsegura, match="fraca"):
        (tmp_path / "x").mkdir()
        _prod(tmp_path / "x", SECRET_KEY="curta")


def test_chave_fraca_no_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("POUSADA_SECRET_KEY", "123")
    assert cfg.carregar_chave_secreta(str(tmp_path)) == "123"           # local: aceita (compatível)
    with pytest.raises(cfg.ConfigInsegura):
        cfg.carregar_chave_secreta(str(tmp_path), estrito=True)
    monkeypatch.setenv("POUSADA_SECRET_KEY", CHAVE_BOA)
    assert cfg.carregar_chave_secreta(str(tmp_path), estrito=True) == CHAVE_BOA


def test_arquivo_de_chave_restrito_e_recusa_permissao_frouxa_ou_chave_fraca(monkeypatch, tmp_path):
    monkeypatch.delenv("POUSADA_SECRET_KEY", raising=False)
    assert len(cfg.carregar_chave_secreta(str(tmp_path))) == 64
    arq = tmp_path / "secret.key"
    if os.name == "posix":
        assert (arq.stat().st_mode & 0o777) == 0o600
        os.chmod(arq, 0o644)
        with pytest.raises(cfg.ConfigInsegura, match="chmod 600"):
            cfg.carregar_chave_secreta(str(tmp_path), estrito=True)
        os.chmod(arq, 0o600)
    arq.write_text("a" * 40)
    with pytest.raises(cfg.ConfigInsegura, match="fraca"):
        cfg.carregar_chave_secreta(str(tmp_path), estrito=True)


def test_app_py_recusa_servir_sem_config(monkeypatch, tmp_path, capsys):
    import app as ponto
    monkeypatch.delenv("POUSADA_SECRET_KEY", raising=False)
    monkeypatch.setattr(cfg, "TRUSTED_HOSTS", [])
    monkeypatch.setattr(cfg, "HTTPS", False)
    monkeypatch.setattr(cfg, "PASTA_INSTANCIA", str(tmp_path / "inst"))
    monkeypatch.setattr(cfg, "CAMINHO_BANCO", str(tmp_path / "x.db"))
    assert ponto.main(["servir"]) == 3
    assert "RECUSADO" in capsys.readouterr().out


# ------------------------------------------------------------ logs

def _fechar_logs():
    for nome in ("pousada.seguranca", "pousada.acesso"):
        lg = logging.getLogger(nome)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()


def test_log_de_seguranca_sem_dados_sensiveis(tmp_path):
    pasta = tmp_path / "logs"
    try:
        a = criar_app_teste(tmp_path, PASTA_LOGS=str(pasta))
        inserir_usuario(a, "admin")
        c = a.test_client()
        c.csrf = c.get("/api/sessao").get_json()["csrf"]
        c.post("/api/login", json={"login": "admin", "senha": "SENHA-ERRADA-XYZ"})
        c.post("/api/login", json={"login": "admin", "senha": SENHA})
        c.get("/api/reservas?q=segredo-na-query")
    finally:
        _fechar_logs()
    seg = (pasta / "seguranca.log").read_text(encoding="utf-8")
    ace = (pasta / "acesso.log").read_text(encoding="utf-8")
    assert "LOGIN_FALHA" in seg and "LOGIN_OK" in seg
    for texto in (seg, ace):
        assert "SENHA-ERRADA-XYZ" not in texto and SENHA not in texto
        assert "segredo-na-query" not in texto
    assert "GET /api/reservas 200" in ace


def test_log_neutraliza_quebra_de_linha(tmp_path):
    pasta = tmp_path / "logs"
    try:
        a = criar_app_teste(tmp_path, PASTA_LOGS=str(pasta))
        a.test_client().get("/api/x%0aFALSO 200")
    finally:
        _fechar_logs()
    assert len((pasta / "acesso.log").read_text(encoding="utf-8").strip().splitlines()) == 1


# ------------------------------------------------------------ arquivos de deploy e dependências

def test_arquivos_de_deploy_e_dependencias():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    def ler(*p):
        with open(os.path.join(raiz, *p), encoding="utf-8") as fh:
            return fh.read()
    req = ler("requirements.txt")
    assert "defusedxml" in req and "waitress" in req and "<4" in req
    import defusedxml  # noqa: F401  (openpyxl o usa sozinho quando instalado)
    caddy = ler("deploy", "Caddyfile")
    assert "reservapousadaboaesperanca.com.br" in caddy and "reverse_proxy 127.0.0.1:5000" in caddy and "redir" in caddy
    unit = ler("deploy", "pousada.service")
    for item in ("NoNewPrivileges=true", "ProtectSystem=strict", "User=pousada", "app.py servir"):
        assert item in unit
    env = ler("deploy", "pousada.env.exemplo")
    assert "POUSADA_PROXY=1" in env and "POUSADA_HTTPS=1" in env and "TRUSTED_HOSTS=" in env
