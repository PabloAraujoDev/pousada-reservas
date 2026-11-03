"""Migração 014 -> 015 sobre um banco 'de produção' com dados: nada se perde e as travas novas valem."""
import os
import shutil
import sqlite3

import pytest

from pousada.db import conectar, iniciar_banco

REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


@pytest.fixture
def banco_v14(tmp_path):
    pasta = tmp_path / "mig14"
    pasta.mkdir()
    for f in os.listdir(REAL):
        if int(f.split("_")[0]) <= 14:
            shutil.copy(os.path.join(REAL, f), str(pasta / f))
    caminho = str(tmp_path / "prod.db")
    iniciar_banco(caminho, str(pasta))
    con = conectar(caminho)
    for k, (a, st) in enumerate([("101", "ativa"), ("201", "ativa"), ("Chalé A", "cancelada")]):
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,tipo,diaria_centavos) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                    (a, "Hóspede ção %d" % k, "", 2, "2026-10-27", "2026-10-30", "pago", "", "", "2026-10-01 10:00:00", "2026-10-01 10:00:00", st, "socio", 30000))
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em) "
                "VALUES (2,'lancamento','bar','Água',1,800,800,'201','2026-10-29 10:00:00')")
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em,estorno_de,motivo) "
                "VALUES (2,'estorno','bar','Água',1,800,-800,'201','2026-10-29 10:01:00',1,'lançado errado')")
    con.close()
    return caminho


def test_migra_14_para_15_sem_perder_nada(banco_v14, tmp_path):
    antes = conectar(banco_v14)
    dump = [tuple(r) for r in antes.execute("SELECT * FROM reservas ORDER BY id")]
    desp = [tuple(r) for r in antes.execute("SELECT * FROM despesa_lancamento ORDER BY id")]
    antes.close()
    bk = str(tmp_path / "bk")
    iniciar_banco(banco_v14, REAL, pasta_backup=bk)
    con = conectar(banco_v14)
    assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] == 15
    assert [tuple(r) for r in con.execute("SELECT * FROM reservas ORDER BY id")] == dump
    assert [tuple(r)[:-1] for r in con.execute("SELECT * FROM despesa_lancamento ORDER BY id")] == [d for d in desp]
    assert con.execute("SELECT COUNT(*) FROM despesa_lancamento WHERE transferencia_id IS NOT NULL").fetchone()[0] == 0
    for t in ("pagamento", "transferencia", "conta_evento"):
        assert con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] == 0
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and os.listdir(bk)
    con.close()


def test_travas_novas(banco_v14):
    iniciar_banco(banco_v14, REAL)
    con = conectar(banco_v14)
    ins = ("INSERT INTO pagamento (reserva_id,tipo,forma,valor_centavos,apto,em,chave%s) VALUES (2,'recebimento','%s',%d,'201','2026-10-29 10:00:00',%s%s)")
    con.execute(ins % ("", "pix", 100, "'chave-001-x'", ""))
    for cmd in (ins % ("", "pix", 100, "'chave-001-x'", ""),                                      # chave repetida
                ins % ("", "pix", -5, "'chave-002-x'", ""),                                       # recebimento negativo
                ins % ("", "boleto", 5, "'chave-003-x'", ""),
                ins % (",bandeira", "pix", 5, "'chave-004-x'", ",'Visa'"),                         # bandeira no Pix
                ins % ("", "cartao", 5, "'chave-005-x'", ""),                                      # cartão sem bandeira
                ins % (",autorizacao,bandeira,modalidade,parcelas", "cartao", 5, "'chave-006-x'", ",'1234567890123','Visa','credito',1"),
                "UPDATE pagamento SET valor_centavos=9", "DELETE FROM pagamento",
                "INSERT INTO transferencia (origem_id,destino_id,apto_origem,apto_destino,total_centavos,itens,em) VALUES (2,2,'a','b',5,1,'x')",
                "DELETE FROM reservas WHERE id=2"):
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(cmd)
    con.execute("INSERT INTO pagamento (reserva_id,tipo,forma,valor_centavos,apto,em,estorno_de,motivo) VALUES (2,'estorno','pix',-100,'201','x',1,'motivo ok')")
    with pytest.raises(sqlite3.DatabaseError):                                                     # segundo estorno do mesmo recebimento
        con.execute("INSERT INTO pagamento (reserva_id,tipo,forma,valor_centavos,apto,em,estorno_de,motivo) VALUES (2,'estorno','pix',-100,'201','x',1,'motivo ok')")
    con.close()
