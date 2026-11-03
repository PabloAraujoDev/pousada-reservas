"""Ajudantes comuns dos testes: aplicativo com banco temporário e clientes já autenticados.

Nenhum teste usa o reservas.db real: tudo vai para a pasta temporária do pytest.
"""
import os
import sys

import pytest
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pousada import create_app  # noqa: E402
from pousada.db import conectar  # noqa: E402
from pousada.regras import agora  # noqa: E402

SENHA = "senha-de-teste-123"
# Hash rápido só para os testes (em produção o werkzeug usa scrypt, que é bem mais lento de propósito).
_HASH_RAPIDO = generate_password_hash(SENHA, method="pbkdf2:sha256:1000")
MUTANTES = {"POST", "PUT", "PATCH", "DELETE"}


class ClienteTeste(FlaskClient):
    """Cliente que envia sozinho o token CSRF e o Content-Type JSON nos pedidos que alteram dados."""
    csrf = None

    def open(self, *args, **kw):
        if str(kw.get("method", "GET")).upper() in MUTANTES:
            if self.csrf is not None and not kw.pop("sem_csrf", False):
                kw["headers"] = {"X-CSRF-Token": self.csrf, **(kw.get("headers") or {})}
            if not any(k in kw for k in ("json", "data", "content_type")):
                kw["json"] = {}
        kw.pop("sem_csrf", None)
        return super().open(*args, **kw)


def criar_app_teste(tmp_path, **extra):
    config = {"SECRET_KEY": "chave-so-de-teste", "PASTA_INSTANCIA": str(tmp_path / "instance"),
              "PASTA_BACKUP": str(tmp_path / "backups")}
    config.update(extra)
    a = create_app(str(tmp_path / "teste.db"), config=config)
    a.test_client_class = ClienteTeste
    return a


def inserir_usuario(app, papel, login=None, ativo=1, trocar_senha=0):
    login = login or papel
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        cur = con.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, ativo, trocar_senha, criado) VALUES (?,?,?,?,?,?,?)",
            (login, login.capitalize(), _HASH_RAPIDO, papel, ativo, trocar_senha, agora()))
        return cur.lastrowid
    finally:
        con.close()


def cliente_como(app, papel, login=None):
    """Cliente já logado (sessão criada direto, sem passar pela tela de login)."""
    uid = inserir_usuario(app, papel, login)
    from pousada.seguranca import assinatura_da_senha
    c = app.test_client()
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        senha_hash, sessao_ver = con.execute("SELECT senha_hash, sessao_ver FROM usuarios WHERE id=?", (uid,)).fetchone()
    finally:
        con.close()
    c.csrf = "token-de-teste-" + papel
    with c.session_transaction() as sess:
        sess.permanent = True
        sess["uid"], sess["sv"], sess["sn"], sess["csrf"] = uid, assinatura_da_senha(senha_hash), sessao_ver, c.csrf
    return c


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path)


@pytest.fixture
def cli(app):
    """Cliente autenticado como administrador (os testes de reservas usam este)."""
    return cliente_como(app, "admin")
