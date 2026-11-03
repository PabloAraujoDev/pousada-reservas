"""QA final: migração 010 -> 014 sobre um banco 'de produção' com dados; nada se perde e as travas novas valem."""
import os
import shutil
import sqlite3

import pytest

from pousada.db import conectar, iniciar_banco

REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


@pytest.fixture
def banco_v10(tmp_path):
    pasta = tmp_path / "mig10"
    pasta.mkdir()
    for f in os.listdir(REAL):
        if int(f.split("_")[0]) <= 10:
            shutil.copy(os.path.join(REAL, f), str(pasta / f))
    caminho = str(tmp_path / "prod.db")
    iniciar_banco(caminho, str(pasta))
    con = conectar(caminho)
    con.execute("INSERT INTO usuarios (login,nome,senha_hash,papel,ativo,trocar_senha,criado) VALUES ('adm','Adm','x','admin',1,0,'2026-01-01')")
    for k, (a, i, f, st) in enumerate([("101", "2026-10-20", "2026-10-25", "ativa"), ("101", "2026-10-25", "2026-10-28", "ativa"),
                                      ("Chalé A", "2026-10-29", "2026-11-02", "cancelada"), ("208", "2026-12-30", "2027-01-03", "ativa")]):
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,tipo,diaria_centavos) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                    (a, "Hóspede ção %d" % k, "", 2, i, f, "pago", "obs ç", "", "2026-10-01 10:00:00", "2026-10-01 10:00:00", st, "socio", 30000 + k))
    con.close()
    return caminho


def test_migra_10_para_14_sem_perder_dados(banco_v10, tmp_path):
    antes = conectar(banco_v10)
    colunas = ",".join(r[1] for r in antes.execute("PRAGMA table_info(reservas)"))      # a 014 acrescenta colunas: compara só as antigas
    dump_antes = [tuple(r) for r in antes.execute("SELECT %s FROM reservas ORDER BY id" % colunas)]
    ver = antes.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0]
    antes.close()
    assert ver == 10
    bk = str(tmp_path / "bk")
    iniciar_banco(banco_v10, REAL, pasta_backup=bk)
    con = conectar(banco_v10)
    assert [tuple(r) for r in con.execute("SELECT %s FROM reservas ORDER BY id" % colunas)] == dump_antes
    assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 14
    assert con.execute("SELECT COUNT(*) FROM governanca_unidade").fetchone()[0] == 25
    assert con.execute("SELECT COUNT(*) FROM nota").fetchone()[0] == 0
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert os.path.isdir(bk) and os.listdir(bk), "backup antes de migrar"
    # travas novas: reserva com despesa/nota não apaga; log imutável
    con.execute("INSERT INTO nota (escopo,reserva_id,tipo,texto,em) VALUES ('reserva',1,'nota','ok','2026-10-29 10:00:00')")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM reservas WHERE id=1")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE nota SET texto='x' WHERE id=1")
    con.close()
    # idempotente: segunda partida não muda nada e não faz novo backup
    n = len(os.listdir(bk))
    iniciar_banco(banco_v10, REAL, pasta_backup=bk)
    assert len(os.listdir(bk)) == n


def test_app_sobe_e_serve_no_banco_migrado(banco_v10, tmp_path):
    from pousada import create_app
    from tests import conftest
    app = create_app(banco_v10, config={"SECRET_KEY": "k", "PASTA_INSTANCIA": str(tmp_path / "i"), "PASTA_BACKUP": str(tmp_path / "b")})
    app.test_client_class = conftest.ClienteTeste
    c = conftest.cliente_como(app, "admin")
    r = c.get("/api/reservas")
    assert r.status_code == 200 and len(r.get_json()) == 3      # a cancelada fica de fora
    assert c.get("/api/governanca").status_code == 200
    rid = r.get_json()[0]["id"]
    assert c.get("/api/reservas/%d/notas" % rid).get_json()["notas"] == []
