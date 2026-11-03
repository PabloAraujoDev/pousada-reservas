"""Migração 013 -> 014 sobre um banco 'de produção' com dados: nada se perde, o estado novo nasce neutro e as travas valem."""
import os
import shutil
import sqlite3

import pytest

from pousada.db import conectar, iniciar_banco

REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


@pytest.fixture
def banco_v13(tmp_path):
    pasta = tmp_path / "mig13"
    pasta.mkdir()
    for f in os.listdir(REAL):
        if int(f.split("_")[0]) <= 13:
            shutil.copy(os.path.join(REAL, f), str(pasta / f))
    caminho = str(tmp_path / "prod.db")
    iniciar_banco(caminho, str(pasta))
    con = conectar(caminho)
    con.execute("INSERT INTO usuarios (login,nome,senha_hash,papel,ativo,trocar_senha,criado) VALUES ('adm','Adm','x','admin',1,0,'2026-01-01')")
    for k, (a, i, f, st) in enumerate([("101", "2026-10-20", "2026-10-25", "ativa"), ("201", "2026-10-27", "2026-10-31", "ativa"),
                                      ("Chalé A", "2026-10-29", "2026-11-02", "cancelada")]):
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,tipo,diaria_centavos) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                    (a, "Hóspede ção %d" % k, "", 2, i, f, "pago", "obs ç", "", "2026-10-01 10:00:00", "2026-10-01 10:00:00", st, "socio", 30000 + k))
    con.execute("INSERT INTO nota (escopo,reserva_id,tipo,texto,em) VALUES ('reserva',2,'nota','ok','2026-10-29 10:00:00')")
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em) "
                "VALUES (2,'lancamento','bar','Água',1,800,800,'201','2026-10-29 10:00:00')")
    con.close()
    return caminho


def test_migra_13_para_14_sem_perder_nada(banco_v13, tmp_path):
    antes = conectar(banco_v13)
    colunas = ",".join(r[1] for r in antes.execute("PRAGMA table_info(reservas)"))
    dump = [tuple(r) for r in antes.execute("SELECT %s FROM reservas ORDER BY id" % colunas)]
    assert antes.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] == 13
    antes.close()
    bk = str(tmp_path / "bk")
    iniciar_banco(banco_v13, REAL, pasta_backup=bk)
    con = conectar(banco_v13)
    assert [tuple(r) for r in con.execute("SELECT %s FROM reservas ORDER BY id" % colunas)] == dump
    assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 14
    # estado novo nasce neutro: nada de check-in, conta aberta, placa nem hóspedes
    assert con.execute("SELECT COUNT(*) FROM reservas WHERE checkin_em IS NOT NULL OR conta_aberta_em IS NOT NULL OR placa IS NOT NULL").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM hospedagem_hospede").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM nota").fetchone()[0] == 1 and con.execute("SELECT COUNT(*) FROM despesa_lancamento").fetchone()[0] == 1
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and os.listdir(bk)
    con.close()


def test_travas_novas(banco_v13):
    iniciar_banco(banco_v13, REAL)
    con = conectar(banco_v13)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE reservas SET placa='ABC' WHERE id=1")                   # exatamente 7 caracteres
    con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, tipo) VALUES (2, 1, 'adulto')")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, tipo) VALUES (2, 1, 'adulto')")      # um titular só
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, nome, tipo) VALUES (2, 0, NULL, 'adulto')")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, nome, tipo) VALUES (2, 0, 'X', 'bebe')")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO hospedagem_hospede (reserva_id, titular, nome) VALUES (999, 0, 'Sem reserva')")
    con.execute("INSERT INTO hospedagem_evento (reserva_id, acao, em) VALUES (2, 'checkin', '2026-10-29 10:00:00')")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE hospedagem_evento SET detalhe='x'")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM hospedagem_evento")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("INSERT INTO hospedagem_evento (reserva_id, acao, em) VALUES (2, 'inventada', 'x')")
    con.close()


def test_app_sobe_no_banco_migrado_e_novas_rotas_respondem(banco_v13, tmp_path):
    from pousada import create_app
    from tests import conftest
    app = create_app(banco_v13, config={"SECRET_KEY": "k", "PASTA_INSTANCIA": str(tmp_path / "i"), "PASTA_BACKUP": str(tmp_path / "b")})
    app.test_client_class = conftest.ClienteTeste
    c = conftest.cliente_como(app, "admin")
    r = c.get("/api/reservas")
    assert r.status_code == 200 and all(x["estado_hospedagem"] == "pendente" for x in r.get_json())
    assert c.get("/api/reservas/2/hospedes").get_json()["acompanhantes"] == [] and c.get("/api/contas-abertas").get_json()["contas_abertas"] == 0
    assert c.get("/api/reservas/2").get_json()["placa"] is None
