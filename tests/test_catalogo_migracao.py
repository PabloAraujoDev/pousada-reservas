"""Migração 015 -> 016 (catálogo) sobre cópia de um banco de produção (v15) com despesas: nada se altera, nada se perde."""
import os
import shutil

import pytest

from pousada.db import conectar, iniciar_banco

REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")


@pytest.fixture
def banco_v15(tmp_path):
    pasta = tmp_path / "mig15"
    pasta.mkdir()
    for f in os.listdir(REAL):
        if int(f.split("_")[0]) <= 15:
            shutil.copy(os.path.join(REAL, f), str(pasta / f))
    caminho = str(tmp_path / "prod.db")
    iniciar_banco(caminho, str(pasta))
    con = conectar(caminho)
    con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,tipo,diaria_centavos) "
                "VALUES ('201','Ana','',2,'2026-10-27','2026-10-30','pago','','','2026-10-01 10:00:00','2026-10-01 10:00:00',1,'ativa','socio',30000)")
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em,usuario_login) "
                "VALUES (1,'lancamento','bar','Água',2,800,1600,'201','2026-10-29 10:00:00','ana')")
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em,estorno_de,motivo) "
                "VALUES (1,'estorno','bar','Água',2,800,-1600,'201','2026-10-29 10:05:00',1,'lançado errado')")
    con.close()
    return caminho


def test_migra_15_para_16_sem_perder_nada(banco_v15, tmp_path):
    antes = conectar(banco_v15)
    reservas = [tuple(r) for r in antes.execute("SELECT * FROM reservas ORDER BY id")]
    linhas = [tuple(r) for r in antes.execute("SELECT * FROM despesa_lancamento ORDER BY id")]
    antes.close()
    bk = str(tmp_path / "bk")
    iniciar_banco(banco_v15, REAL, pasta_backup=bk)
    con = conectar(banco_v15)
    assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] == 16 and os.listdir(bk)
    assert [tuple(r) for r in con.execute("SELECT * FROM reservas ORDER BY id")] == reservas
    novas = [tuple(r) for r in con.execute("SELECT * FROM despesa_lancamento ORDER BY id")]
    assert [l[:-1] for l in novas] == linhas and all(l[-1] is None for l in novas)        # item_id NULL: lançamento antigo
    assert con.execute("SELECT COUNT(*) FROM catalogo_item").fetchone()[0] == 28
    assert con.execute("SELECT COUNT(*) FROM catalogo_log WHERE acao='criado'").fetchone()[0] == 28
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()
    iniciar_banco(banco_v15, REAL)             # idempotente: rodar de novo não duplica a carga
    con = conectar(banco_v15)
    assert con.execute("SELECT COUNT(*) FROM catalogo_item").fetchone()[0] == 28
    con.close()


def test_carga_inicial_em_ordem_alfabetica_e_precos(banco_v15):
    from pousada import catalogo as cat
    iniciar_banco(banco_v15, REAL)
    con = conectar(banco_v15)
    lista = [(cat.CATEGORIAS[l["categoria"]][0], l["grupo"], l["descricao"], l["preco_centavos"]) for l in cat.listar(con)]
    con.close()
    assert [x[0] for x in lista] == ["Bebidas"] * 16 + ["Porções"] * 12
    assert lista[0] == ("Bebidas", "Águas", "Água com gás", 500) and lista[1][3] == 400
    beb = [x for x in lista if x[0] == "Bebidas"]
    grupos = [g for i, (_, g, _, _) in enumerate(beb) if i == 0 or beb[i - 1][1] != g]
    assert grupos == ["Águas", "Cervejas (600ml)", "Cervejas Long Neck", "Refrigerantes", "Sucos", "Vinhos"]
    for g in grupos:
        nomes = [cat.chave_ordem(x[2]) for x in beb if x[1] == g]
        assert nomes == sorted(nomes)
    porc = [x[2] for x in lista if x[0] == "Porções"]
    assert porc == sorted(porc, key=cat.chave_ordem) and porc[0] == "Batata Frita c/ queijo" and "Ovo frito" in porc
    assert dict((x[2], x[3]) for x in lista)["Ovo frito"] == 200 and dict((x[2], x[3]) for x in lista)["Vinho Tinto Suave Marcon/Bordô"] == 3500


def test_travas_da_migracao(banco_v15):
    import sqlite3
    iniciar_banco(banco_v15, REAL)
    con = conectar(banco_v15)
    for cmd in ("DELETE FROM catalogo_item", "UPDATE catalogo_log SET acao='editado'", "DELETE FROM catalogo_log",
                "INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em) "
                "VALUES (1,'lancamento','bar','Agua',1,1,1,'201','ontem')",
                "INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em,item_id) "
                "VALUES (1,'lancamento','bar','Agua',1,1,1,'201','2026-10-29 10:00:00',9999)"):
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(cmd)
    con.close()
