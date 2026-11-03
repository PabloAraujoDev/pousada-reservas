"""Usuários, comando criar-admin e chave secreta (bancos e pastas sempre temporários)."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pousada import cli, config  # noqa: E402
from pousada.db import conectar, iniciar_banco  # noqa: E402
from pousada.usuarios import criar_usuario, senha_confere  # noqa: E402

SENHA = "senha-bem-longa-123"


@pytest.fixture
def con(tmp_path):
    banco = str(tmp_path / "u.db")
    iniciar_banco(banco, config.PASTA_MIGRACOES)
    c = conectar(banco)
    yield c
    c.close()


def test_criar_usuario_guarda_so_o_hash(con):
    uid = criar_usuario(con, "Maria", "Maria Silva", SENHA, "atendente")
    u = con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    assert SENHA not in u["senha_hash"] and u["senha_hash"] != SENHA
    assert u["ativo"] == 1 and u["papel"] == "atendente" and u["ultimo_login"] is None
    assert senha_confere(u, SENHA) and not senha_confere(u, SENHA + "x")
    assert senha_confere(None, SENHA) is False            # login inexistente também termina sem erro


def test_login_unico_sem_diferenciar_maiusculas(con):
    criar_usuario(con, "Pablo", "Pablo", SENHA, "admin")
    with pytest.raises(ValueError):
        criar_usuario(con, "pablo", "Outro", SENHA, "admin")
    assert con.execute("SELECT id FROM usuarios WHERE login='PABLO'").fetchone() is not None


@pytest.mark.parametrize("login,nome,senha,papel", [
    ("ab", "Nome", SENHA, "admin"),                     # login curto
    ("com espaco", "Nome", SENHA, "admin"),
    ("maria", "", SENHA, "admin"),
    ("maria", "Nome", "curta123", "admin"),              # menos de 10 caracteres
    ("maria", "Nome", SENHA, "chefe"),                   # papel inexistente
])
def test_dados_invalidos_recusados(con, login, nome, senha, papel):
    with pytest.raises(ValueError):
        criar_usuario(con, login, nome, senha, papel)


def test_banco_recusa_papel_invalido(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO usuarios (login,nome,senha_hash,papel,criado) VALUES ('x','x','x','dono','x')")


def _simular_terminal(monkeypatch, tmp_path, respostas, senhas):
    monkeypatch.setattr(config, "CAMINHO_BANCO", str(tmp_path / "cli.db"))
    entradas, segredos = iter(respostas), iter(senhas)
    monkeypatch.setattr("builtins.input", lambda *_: next(entradas))
    monkeypatch.setattr(cli.getpass, "getpass", lambda *_: next(segredos))


def test_comando_criar_admin(tmp_path, monkeypatch, capsys):
    _simular_terminal(monkeypatch, tmp_path, ["pablo", "Pablo Araújo"], [SENHA, SENHA])
    assert cli.executar(["criar-admin"]) == 0
    con = conectar(config.CAMINHO_BANCO)
    try:
        u = con.execute("SELECT login, nome, papel, ativo FROM usuarios").fetchone()
        assert tuple(u) == ("pablo", "Pablo Araújo", "admin", 1)
    finally:
        con.close()
    assert SENHA not in capsys.readouterr().out


def test_criar_admin_recusa_senha_curta_e_diferente(tmp_path, monkeypatch):
    _simular_terminal(monkeypatch, tmp_path, ["pablo", "Pablo"], ["curta", "curta"])
    assert cli.executar(["criar-admin"]) == 1
    _simular_terminal(monkeypatch, tmp_path, ["pablo", "Pablo"], [SENHA, SENHA + "x"])
    assert cli.executar(["criar-admin"]) == 1
    con = conectar(config.CAMINHO_BANCO)
    try:
        assert con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0
    finally:
        con.close()


def test_comando_desconhecido():
    assert cli.executar(["xpto"]) == 2


def test_chave_secreta_persistente(tmp_path, monkeypatch):
    monkeypatch.delenv("POUSADA_SECRET_KEY", raising=False)
    pasta = str(tmp_path / "instance")
    k1 = config.carregar_chave_secreta(pasta)
    k2 = config.carregar_chave_secreta(pasta)
    assert k1 == k2 and len(k1) == 64 and os.path.exists(os.path.join(pasta, "secret.key"))
    monkeypatch.setenv("POUSADA_SECRET_KEY", "vinda-do-ambiente")
    assert config.carregar_chave_secreta(pasta) == "vinda-do-ambiente"


def test_nao_ha_chave_ou_senha_padrao_no_codigo():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for pasta, _, arquivos in os.walk(os.path.join(raiz, "pousada")):
        for nome in arquivos:
            if nome.endswith(".py"):
                with open(os.path.join(pasta, nome), encoding="utf-8") as fh:
                    texto = fh.read()
                assert "SECRET_KEY'] = '" not in texto and 'SECRET_KEY"] = "' not in texto
                assert "admin123" not in texto
