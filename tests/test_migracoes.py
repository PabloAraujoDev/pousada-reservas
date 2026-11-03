"""Testes do executor de migrações (sempre com bancos temporários)."""
import os
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pousada.db import conectar, iniciar_banco  # noqa: E402

PASTA_REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


def _pasta(tmp_path, **arquivos):
    pasta = tmp_path / "mig"
    pasta.mkdir(exist_ok=True)
    for nome, sql in arquivos.items():
        (pasta / (nome + ".sql")).write_text(sql, encoding="utf-8")
    return str(pasta)


def _versoes(banco):
    con = conectar(banco)
    try:
        return [r[0] for r in con.execute("SELECT versao FROM schema_version ORDER BY versao")]
    finally:
        con.close()


def test_migracao_com_trigger_aplica(tmp_path):
    pasta = _pasta(tmp_path, **{"001_a": """
        CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);
        CREATE TABLE log (msg TEXT);
        CREATE TRIGGER t_ai AFTER INSERT ON t BEGIN
            INSERT INTO log (msg) VALUES ('inserido; com ponto e vírgula');
            INSERT INTO log (msg) VALUES ('segundo comando');
        END;
    """})
    banco = str(tmp_path / "t.db")
    iniciar_banco(banco, pasta)
    con = conectar(banco)
    try:
        con.execute("INSERT INTO t (v) VALUES ('x')")
        assert [r[0] for r in con.execute("SELECT msg FROM log ORDER BY rowid")] == \
            ["inserido; com ponto e vírgula", "segundo comando"]
    finally:
        con.close()
    assert _versoes(banco) == [1]


def test_migracao_com_erro_desfaz_tudo(tmp_path):
    pasta = _pasta(tmp_path, **{"001_ok": "CREATE TABLE a (x);",
                                "002_ruim": "CREATE TABLE b (x); INSERT INTO nao_existe VALUES (1);"})
    banco = str(tmp_path / "t.db")
    with pytest.raises(sqlite3.Error):
        iniciar_banco(banco, pasta)
    con = conectar(banco)
    try:
        tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "a" in tabelas and "b" not in tabelas          # a 002 foi desfeita por inteiro
        assert not con.in_transaction
    finally:
        con.close()
    assert _versoes(banco) == [1]


def test_nao_repete_migracao_ja_aplicada(tmp_path):
    pasta = _pasta(tmp_path, **{"001_a": "CREATE TABLE a (x);"})
    banco = str(tmp_path / "t.db")
    iniciar_banco(banco, pasta)
    iniciar_banco(banco, pasta)           # se repetisse, CREATE TABLE sem IF NOT EXISTS falharia
    assert _versoes(banco) == [1]


def test_backup_antes_de_migrar_so_quando_ja_existe(tmp_path):
    pasta = _pasta(tmp_path, **{"001_a": "CREATE TABLE a (x);"})
    banco, bk = str(tmp_path / "t.db"), str(tmp_path / "bk")
    iniciar_banco(banco, pasta, pasta_backup=bk)
    assert not os.path.exists(bk)                      # banco novo: nada a proteger
    iniciar_banco(banco, pasta, pasta_backup=bk)
    assert not os.path.exists(bk)                      # nada pendente: sem backup
    _pasta(tmp_path, **{"002_b": "CREATE TABLE b (x);"})
    iniciar_banco(banco, pasta, pasta_backup=bk)
    copias = os.listdir(bk)
    assert len(copias) == 1 and copias[0].startswith("reservas_")
    copia = sqlite3.connect(os.path.join(bk, copias[0]))
    try:
        tabelas = {r[0] for r in copia.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "a" in tabelas and "b" not in tabelas   # a cópia é do estado ANTES da migração
    finally:
        copia.close()


def test_falha_no_backup_impede_a_migracao(tmp_path, monkeypatch):
    pasta = _pasta(tmp_path, **{"001_a": "CREATE TABLE a (x);"})
    banco = str(tmp_path / "t.db")
    iniciar_banco(banco, pasta)
    _pasta(tmp_path, **{"002_b": "CREATE TABLE b (x);"})
    from pousada.backup import ErroBackup

    def falha(*a, **k):
        raise ErroBackup("sem espaço")
    monkeypatch.setattr("pousada.backup.fazer_backup", falha)
    with pytest.raises(ErroBackup):
        iniciar_banco(banco, pasta, pasta_backup=str(tmp_path / "bk"))
    assert _versoes(banco) == [1]


def test_migracoes_reais_aplicam_do_zero(tmp_path):
    banco = str(tmp_path / "t.db")
    iniciar_banco(banco, PASTA_REAL)
    assert _versoes(banco) == sorted(_versoes(banco)) and _versoes(banco)[0] == 1
    shutil.rmtree(str(tmp_path / "mig"), ignore_errors=True)
