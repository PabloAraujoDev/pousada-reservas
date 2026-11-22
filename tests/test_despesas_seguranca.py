"""Despesas: migração com dados, triggers, concorrência, permissões nos 6 papéis, vazamento de valor e histórico."""
import json
import os
import sqlite3
import threading

import pytest

from pousada.db import conectar, iniciar_banco
from tests.conftest import criar_app_teste
from tests.test_despesas import AGORA, LANC, RES, cli, lancar, nova_reserva

PAPEIS = ["admin", "atendente", "recepcao", "diretoria", "consulta", "camareira"]
PASTA_REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
MARCADOR = 777123          # valor unitário "marcador": não pode aparecer fora das rotas de despesas
DESCR = "Marcador Secreto"


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def sql(app, comando, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return con.execute(comando, args).fetchall()
    finally:
        con.close()


def test_migracao_012_sobre_banco_da_versao_11_com_dados(tmp_path):
    pasta = tmp_path / "mig"
    pasta.mkdir()
    for f in os.listdir(PASTA_REAL):
        if int(f.split("_")[0]) <= 11:
            (pasta / f).write_bytes(open(os.path.join(PASTA_REAL, f), "rb").read())
    banco = str(tmp_path / "b.db")
    iniciar_banco(banco, str(pasta))
    con = conectar(banco)
    con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao) "
                "VALUES ('201','Ana','',1,'2026-10-27','2026-10-30','pago','','','x','x',1)")
    con.close()
    iniciar_banco(banco, PASTA_REAL, pasta_backup=str(tmp_path / "bk"))
    con = conectar(banco)
    try:
        assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 12
        assert con.execute("SELECT nome FROM reservas").fetchone()[0] == "Ana"
        con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,"
                    "total_centavos,apto,em) VALUES (1,'lancamento','bar','Agua',2,800,1600,'201','2026-10-01 10:00:00')")
    finally:
        con.close()


def inserir(con, rid=1, tipo="lancamento", total=1600, estorno_de=None, motivo="", qtd=2, unit=800, chave=None):
    con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,"
                "total_centavos,apto,em,estorno_de,motivo,chave) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, tipo, "bar", "Agua", qtd, unit, total, "201", "2026-10-01 10:00:00", estorno_de, motivo, chave))


def test_triggers_e_checks_do_banco(app):
    rid = nova_reserva(app)["id"]
    lid = lancar(cli(app, "admin"), rid).get_json()["id"]
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        for comando in ("UPDATE despesa_lancamento SET descricao='x'", "DELETE FROM despesa_lancamento"):
            with pytest.raises(sqlite3.DatabaseError, match="não pode ser"):
                con.execute(comando)
        with pytest.raises(sqlite3.IntegrityError):          # total errado
            inserir(con, rid, total=1500)
        with pytest.raises(sqlite3.IntegrityError):          # estorno sem motivo
            inserir(con, rid, "estorno", -1600, lid, "abc")
        with pytest.raises(sqlite3.DatabaseError, match="Reserva inexistente"):
            inserir(con, 999)
        outra = nova_reserva(app, a="202")["id"]
        with pytest.raises(sqlite3.DatabaseError, match="Estorno inválido"):    # estorno de outra reserva
            inserir(con, outra, "estorno", -1600, lid, "motivo certo")
        inserir(con, rid, "estorno", -1600, lid, "motivo certo")
        with pytest.raises(sqlite3.IntegrityError):          # estorno repetido (índice único)
            inserir(con, rid, "estorno", -1600, lid, "motivo certo")
        with pytest.raises(sqlite3.DatabaseError, match="Reserva com despesas"):
            con.execute("DELETE FROM reservas WHERE id=?", (rid,))
    finally:
        con.close()


def test_limite_de_200_lancamentos(app):
    rid = nova_reserva(app)["id"]
    con = conectar(app.config["CAMINHO_BANCO"])
    for k in range(199):
        inserir(con, rid, total=1, qtd=1, unit=1)
    con.close()
    c = cli(app, "admin")
    saidas = []
    barreira = threading.Barrier(2)
    # clientes de teste não são seguros entre threads; cada thread usa o seu
    from tests import conftest
    clientes = [conftest.cliente_como(app, "admin", "t%d" % n) for n in range(2)]

    def disparar(n):
        barreira.wait()
        saidas.append(lancar(clientes[n], rid, chave="chave-par-%d" % n).status_code)

    ts = [threading.Thread(target=disparar, args=(n,)) for n in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(saidas) == [201, 409]
    assert sql(app, "SELECT COUNT(*) FROM despesa_lancamento WHERE tipo='lancamento'")[0][0] == 200
    lid = sql(app, "SELECT id FROM despesa_lancamento ORDER BY id DESC LIMIT 1")[0][0]
    assert c.post("/api/despesas/%d/estorno" % lid, json={"motivo": "conta cheia, corrige"}).status_code == 201


def test_duplo_clique_simultaneo_cria_um_so(app):
    from tests import conftest
    rid = nova_reserva(app)["id"]
    clientes = [conftest.cliente_como(app, "admin", "d%d" % n) for n in range(4)]
    barreira, saidas = threading.Barrier(4), []

    def vai(n):
        barreira.wait()
        saidas.append(lancar(clientes[n], rid, chave="mesma-chave-1").status_code)

    ts = [threading.Thread(target=vai, args=(n,)) for n in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(saidas) == [200, 200, 200, 201]
    assert sql(app, "SELECT COUNT(*) FROM despesa_lancamento")[0][0] == 1


def test_estorno_simultaneo_so_um_passa(app):
    from tests import conftest
    rid = nova_reserva(app)["id"]
    lid = lancar(cli(app, "admin"), rid).get_json()["id"]
    clientes = [conftest.cliente_como(app, "admin", "e%d" % n) for n in range(4)]
    barreira, saidas = threading.Barrier(4), []

    def vai(n):
        barreira.wait()
        saidas.append(clientes[n].post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"}).status_code)

    ts = [threading.Thread(target=vai, args=(n,)) for n in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(saidas) == [201, 409, 409, 409]
    assert sql(app, "SELECT COALESCE(SUM(total_centavos),0) FROM despesa_lancamento")[0][0] == 0


def test_saldo_maximo_da_reserva(app):
    rid = nova_reserva(app)["id"]
    c, ok = cli(app, "admin"), 0
    for k in range(101):
        r = lancar(c, rid, quantidade=1, valor_unit_centavos=1000000, chave="chave-sal-%03d" % k)
        ok += r.status_code == 201
    assert ok == 100 and r.status_code == 422 and "máximo" in r.get_json()["erro"]


def test_atomicidade_falha_no_historico_desfaz_o_lancamento(app, monkeypatch):
    rid = nova_reserva(app)["id"]
    from pousada import rotas_despesas

    def quebra(*a, **k):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(rotas_despesas, "registrar", quebra)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    assert lancar(cli(app, "admin"), rid).status_code == 500
    assert sql(app, "SELECT COUNT(*) FROM despesa_lancamento")[0][0] == 0
    assert sql(app, "SELECT COUNT(*) FROM despesa_conta")[0][0] == 0


def test_historico_so_tem_categoria_e_itens(app):
    rid = nova_reserva(app)["id"]
    lid = lancar(cli(app, "admin"), rid, descricao=DESCR, valor_unit_centavos=MARCADOR).get_json()["id"]
    cli(app, "admin").post("/api/despesas/%d/estorno" % lid, json={"motivo": "motivo privado xyz"})
    linhas = sql(app, "SELECT acao, antes, depois FROM historico WHERE acao LIKE 'despesa%' ORDER BY id")
    assert [l[0] for l in linhas] == ["despesa_lancada", "despesa_estornada"]
    for acao, antes, depois in linhas:
        assert json.loads(depois) == {"categoria": "bar", "itens": 1} and antes is None
    tudo = json.dumps([tuple(l) for l in sql(app, "SELECT * FROM historico")])
    for proibido in (str(MARCADOR), DESCR, "privado", str(2 * MARCADOR)):
        assert proibido not in tudo
    api = cli(app, "admin").get("/api/historico").get_data(as_text=True)
    assert DESCR not in api and str(MARCADOR) not in api
