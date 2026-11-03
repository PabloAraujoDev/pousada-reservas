"""Backup, rotação, restauração e proteção contra o OneDrive (tudo em pastas temporárias)."""
import os
import sqlite3
import time
from datetime import date, datetime, timedelta

import pytest

from pousada import create_app
from pousada.backup import (BackupPeriodico, ErroBackup, fazer_backup, listar_backups, pasta_backup_padrao,
                            restaurar, validar_pasta)
from pousada.db import conectar
from tests.conftest import cliente_como, criar_app_teste
from tests.test_reservas import corpo


def contar(caminho):
    con = sqlite3.connect(caminho)
    try:
        return con.execute("SELECT COUNT(*) FROM reservas").fetchone()[0]
    finally:
        con.close()


def test_trinta_e_um_backups_deixam_trinta(app, cli, tmp_path):
    banco, pasta = app.config["CAMINHO_BANCO"], str(tmp_path / "bk")
    base = datetime(2026, 10, 1, 8, 0, 0)
    for k in range(31):
        fazer_backup(banco, pasta, agora=base + timedelta(minutes=k))
    arquivos = listar_backups(pasta)
    assert len(arquivos) == 30 and len(os.listdir(pasta)) == 30
    assert arquivos[0] == "reservas_20261001_080100.db" and arquivos[-1] == "reservas_20261001_083000.db"   # o mais velho saiu


def test_backup_abre_e_confere_contagem(app, cli, tmp_path):
    for k in range(3):
        cli.post("/api/reservas", json=corpo(a="20%d" % (k + 1)))
    caminho = fazer_backup(app.config["CAMINHO_BANCO"], str(tmp_path / "bk"))
    assert os.path.basename(caminho).startswith("reservas_") and caminho.endswith(".db")
    assert contar(caminho) == 3
    con = sqlite3.connect(caminho)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()
    assert not [f for f in os.listdir(tmp_path / "bk") if f.endswith(".tmp")]


def test_dois_backups_no_mesmo_segundo_nao_se_sobrescrevem(app, tmp_path):
    agora = datetime(2026, 10, 1, 8, 0, 0)
    fazer_backup(app.config["CAMINHO_BANCO"], str(tmp_path / "bk"), agora=agora)
    fazer_backup(app.config["CAMINHO_BANCO"], str(tmp_path / "bk"), agora=agora)
    assert len(listar_backups(str(tmp_path / "bk"))) == 2


def test_recusa_pasta_dentro_do_onedrive(app, tmp_path):
    for ruim in ("C:\\Users\\x\\OneDrive\\Backups", "C:/Users/x/OneDrive - Empresa/b", str(tmp_path / "onedrive" / "b")):
        with pytest.raises(ErroBackup, match="OneDrive"):
            validar_pasta(ruim)
        with pytest.raises(ErroBackup):
            fazer_backup(app.config["CAMINHO_BANCO"], ruim)
    assert not (tmp_path / "onedrive").exists()


def test_pasta_padrao(monkeypatch):
    monkeypatch.delenv("POUSADA_BACKUP_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\x\\AppData\\Local")
    assert pasta_backup_padrao().endswith("PousadaBackups") and "AppData" in pasta_backup_padrao()
    monkeypatch.setenv("POUSADA_BACKUP_DIR", "D:\\Meus Backups")
    assert pasta_backup_padrao() == "D:\\Meus Backups"


def test_restauracao_devolve_o_estado(app, cli, tmp_path):
    banco, pasta = app.config["CAMINHO_BANCO"], str(tmp_path / "bk")
    cli.post("/api/reservas", json=corpo(a="201"))
    cli.post("/api/reservas", json=corpo(a="202"))
    copia = fazer_backup(banco, pasta)
    cli.post("/api/reservas", json=corpo(a="203"))                    # alteração DEPOIS do backup
    assert contar(banco) == 3
    for sufixo in ("-wal", "-shm"):                                   # restos que o SQLite deixa
        open(banco + sufixo, "ab").close()
    msg = restaurar(banco, copia)
    assert "restaurado" in msg and contar(banco) == 2
    assert not os.path.exists(banco + "-wal") and not os.path.exists(banco + "-shm")
    guardado = [f for f in os.listdir(tmp_path) if f.startswith("reservas_pre_restauracao_")]
    assert len(guardado) == 1 and contar(str(tmp_path / guardado[0])) == 3     # o estado de antes não se perdeu
    # e o sistema volta a funcionar com o banco restaurado
    app2 = criar_app_teste(tmp_path)
    assert len(cliente_como(app2, "admin", "outro").get("/api/reservas").get_json()) == 2


def test_restauracao_recusa_arquivo_ruim(app, tmp_path):
    banco = app.config["CAMINHO_BANCO"]
    lixo = tmp_path / "lixo.db"
    lixo.write_bytes(b"isto nao e um banco de dados" * 50)
    with pytest.raises(ErroBackup):
        restaurar(banco, str(lixo))
    outro = tmp_path / "outro.db"
    con = sqlite3.connect(str(outro))
    con.execute("CREATE TABLE coisa (x)")
    con.commit()
    con.close()
    with pytest.raises(ErroBackup, match="não parece"):
        restaurar(banco, str(outro))
    with pytest.raises(ErroBackup, match="não encontrado"):
        restaurar(banco, str(tmp_path / "nao_existe.db"))
    assert os.path.getsize(banco) > 0                                  # nada foi tocado


def test_restauracao_recusa_com_sistema_ligado(app, tmp_path):
    copia = fazer_backup(app.config["CAMINHO_BANCO"], str(tmp_path / "bk"))
    con = conectar(app.config["CAMINHO_BANCO"])
    con.execute("BEGIN IMMEDIATE")                                     # simula o sistema gravando
    try:
        with pytest.raises(ErroBackup, match="em uso"):
            restaurar(app.config["CAMINHO_BANCO"], copia)
    finally:
        con.execute("ROLLBACK")
        con.close()


def test_comando_restaurar(app, tmp_path, monkeypatch, capsys):
    from pousada import cli as terminal, config
    copia = fazer_backup(app.config["CAMINHO_BANCO"], str(tmp_path / "bk"))
    monkeypatch.setattr(config, "CAMINHO_BANCO", app.config["CAMINHO_BANCO"])
    assert terminal.executar(["restaurar", copia]) == 0
    assert "restaurado" in capsys.readouterr().out
    assert terminal.executar(["restaurar"]) == 1
    assert terminal.executar(["restaurar", str(tmp_path / "nada.db")]) == 1


# ---------------------------------------------------------------- pela API

def test_botao_fazer_backup_agora_so_admin(app, cli):
    r = cli.post("/api/backup")
    assert r.status_code == 201 and r.get_json()["arquivo"].startswith("reservas_") and r.get_json()["total"] == 1
    assert cli.get("/api/backup").get_json()["arquivos"] == [r.get_json()["arquivo"]]
    assert cliente_como(app, "atendente").post("/api/backup").status_code == 403
    assert cli.get("/api/historico?entidade=backup").get_json()[0]["depois"]["arquivo"] == r.get_json()["arquivo"]


def test_backup_antes_de_importar(app, cli):
    from tests.test_importacao import corpo_confirmar, planilha_limpa, previa
    app.config["HOJE"] = date(2026, 10, 1)
    pasta = app.config["PASTA_BACKUP"]
    j = previa(cli, planilha_limpa()).get_json()
    assert not os.path.exists(pasta)                                   # prévia não faz backup
    assert cli.post("/api/importar/confirmar", json=corpo_confirmar(j)).status_code == 201
    copias = listar_backups(pasta)
    assert len(copias) == 1 and contar(os.path.join(pasta, copias[0])) == 0     # cópia do estado ANTES de importar
    assert cli.post("/api/importar").status_code == 409                 # (seed recusado: já tem reservas) ...
    assert len(listar_backups(pasta)) == 2                              # ... mas o backup vem antes de qualquer importação


def test_sem_backup_nao_importa(tmp_path):
    from tests.test_importacao import corpo_confirmar, planilha_limpa, previa
    a = criar_app_teste(tmp_path, PASTA_BACKUP=str(tmp_path / "OneDrive" / "bk"), HOJE=date(2026, 10, 1))
    c = cliente_como(a, "admin")
    j = previa(c, planilha_limpa()).get_json()
    r = c.post("/api/importar/confirmar", json=corpo_confirmar(j))
    assert r.status_code == 503 and "nada foi importado" in r.get_json()["erro"]
    assert c.get("/api/reservas").get_json() == []


# ---------------------------------------------------------------- automático

def test_backup_ao_iniciar_e_periodico(tmp_path):
    banco, pasta = str(tmp_path / "prod.db"), str(tmp_path / "bk")
    cfg = {"SECRET_KEY": "x", "PASTA_INSTANCIA": str(tmp_path / "i"), "PASTA_BACKUP": pasta, "PRODUCAO": True}
    a1 = create_app(banco, config=cfg)                                 # banco novo: ainda não há o que copiar
    a1.extensions["backup_periodico"].parar.set()
    assert listar_backups(pasta) == []
    a2 = create_app(banco, config=cfg)                                 # segunda vez: backup ao iniciar
    a2.extensions["backup_periodico"].parar.set()
    assert len(listar_backups(pasta)) == 1


def test_thread_periodica_faz_backup(app, tmp_path):
    pasta = str(tmp_path / "bk")
    t = BackupPeriodico(app.config["CAMINHO_BANCO"], pasta, horas=0.00003)      # ~0,1 segundo
    t.start()
    for _ in range(50):
        if listar_backups(pasta):
            break
        time.sleep(0.1)
    t.parar.set()
    assert len(listar_backups(pasta)) >= 1
