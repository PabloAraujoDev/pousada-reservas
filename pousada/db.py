"""Acesso ao banco SQLite e migrações."""
import os
import re
import sqlite3
from contextlib import contextmanager

from flask import current_app, g


def conectar(caminho):
    """Abre uma conexão com WAL, espera por bloqueios e transações manuais."""
    con = sqlite3.connect(caminho, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA recursive_triggers=ON")      # sem isto, INSERT OR REPLACE apagaria linha dos logs imutáveis sem acionar o gatilho
    return con


def obter_con():
    """Conexão do pedido atual (uma por requisição; é fechada sozinha no fim)."""
    if "con" not in g:
        g.con = conectar(current_app.config["CAMINHO_BANCO"])
    return g.con


def fechar_con(_erro=None):
    con = g.pop("con", None)
    if con is not None:
        con.close()


@contextmanager
def transacao(con):
    """Transação imediata: confirma se o bloco terminar bem e desfaz tudo se houver qualquer erro."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def _migracoes_em_disco(pasta):
    """Lista [(numero, nome_do_arquivo)] em ordem, a partir dos arquivos NNN_nome.sql."""
    achadas = [(int(f.split("_")[0]), f) for f in os.listdir(pasta) if re.match(r"^\d+_.*\.sql$", f)]
    return sorted(achadas)


def _aplicar_migracao(con, numero, sql):
    """Roda uma migração inteira (inclusive TRIGGERs) numa única transação: tudo ou nada."""
    registro = ("INSERT INTO schema_version (versao, aplicada) "
                "VALUES (%d, datetime('now','localtime'));" % int(numero))
    script = "BEGIN IMMEDIATE;\n" + sql + "\n;\n" + registro + "\nCOMMIT;\n"
    try:
        con.executescript(script)
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def iniciar_banco(caminho, pasta_migracoes, pasta_backup=None):
    """Cria o banco se preciso e aplica as migrações pendentes (NNN_nome.sql).

    Se o banco já existia e há migração a aplicar, faz antes uma cópia de segurança
    em 'pasta_backup' (quando informada). Se a cópia falhar, a migração NÃO é aplicada.
    """
    existia = os.path.exists(caminho) and os.path.getsize(caminho) > 0
    con = conectar(caminho)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS schema_version (versao INTEGER PRIMARY KEY, aplicada TEXT NOT NULL)")
        atual = con.execute("SELECT COALESCE(MAX(versao), 0) FROM schema_version").fetchone()[0]
        pendentes = [(n, f) for n, f in _migracoes_em_disco(pasta_migracoes) if n > atual]
        if pendentes and existia and atual > 0 and pasta_backup:
            from .backup import fazer_backup
            fazer_backup(caminho, pasta_backup)
        for numero, nome in pendentes:
            with open(os.path.join(pasta_migracoes, nome), encoding="utf-8") as fh:
                _aplicar_migracao(con, numero, fh.read())
    finally:
        con.close()
