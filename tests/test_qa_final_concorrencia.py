"""QA final: concorrência real (threads, um cliente por thread) em notas, despesas e governança."""
import threading
from collections import Counter
from datetime import datetime

import pytest

from pousada.db import conectar
from tests import conftest
from tests.conftest import criar_app_teste

AGORA = datetime(2026, 10, 29, 9, 0, 0)
RES = {"a": "201", "nome": "Maria", "extras": "", "n": 2, "i": "2026-10-27", "f": "2026-10-30", "p": "pendente", "o": "", "grupo": ""}


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def cl(app, papel, login=None):
    cache = app.__dict__.setdefault("_cl", {})
    chave = (papel, login or papel)
    if chave not in cache:
        cache[chave] = conftest.cliente_como(app, papel, login)
    return cache[chave]


def paralelo(app, papel, n, fazer):
    """Roda fazer(cliente, k) em n threads ao mesmo tempo; devolve [(status, json)]."""
    clientes = [cl(app, papel, "%s%d" % (papel, k)) for k in range(n)]
    saida, barreira = [None] * n, threading.Barrier(n)

    def corre(k):
        barreira.wait()
        r = fazer(clientes[k], k)
        saida[k] = (r.status_code, r.get_json(silent=True))
    ts = [threading.Thread(target=corre, args=(k,)) for k in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return saida


def contar(app, sql, args=()):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return con.execute(sql, args).fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def rid(app):
    return cl(app, "admin").post("/api/reservas", json=RES).get_json()["id"]


def test_duplo_clique_nota_mesma_chave(app, rid):
    r = paralelo(app, "atendente", 8, lambda c, k: c.post("/api/reservas/%d/notas" % rid, json={"texto": "oi", "chave": "chave-12345678"}))
    assert {s for s, _ in r} <= {200, 201}
    assert Counter(s for s, _ in r)[201] == 1
    assert contar(app, "SELECT COUNT(*) FROM nota") == 1


def test_lancamento_mesma_chave_e_estorno_duplo(app, rid):
    corpo = {"categoria": "bar", "descricao": "Cerveja", "quantidade": 2, "valor_unit_centavos": 1000, "chave": "abcdefgh-1"}
    r = paralelo(app, "atendente", 8, lambda c, k: c.post("/api/reservas/%d/despesas" % rid, json=corpo))
    assert {s for s, _ in r} <= {200, 201} and Counter(s for s, _ in r)[201] == 1
    lid = [j for s, j in r if s == 201][0]["id"]
    e = paralelo(app, "atendente", 8, lambda c, k: c.post("/api/despesas/%d/estorno" % lid, json={"motivo": "lancado errado"}))
    assert Counter(s for s, _ in e) == {201: 1, 409: 7}, e
    assert contar(app, "SELECT COALESCE(SUM(total_centavos),0) FROM despesa_lancamento") == 0


def test_correcao_simultanea_mesma_versao_so_uma(app, rid):
    n = cl(app, "admin").post("/api/reservas/%d/notas" % rid, json={"texto": "base"}).get_json()
    r = paralelo(app, "atendente", 6, lambda c, k: c.post("/api/notas/%d/corrigir" % n["id"], json={"texto": "novo %d" % k, "versao": 1}))
    assert Counter(s for s, _ in r) == {200: 1, 409: 5}, r
    assert contar(app, "SELECT COUNT(*) FROM nota WHERE tipo='correcao'") == 1


def test_corrigir_e_ocultar_ao_mesmo_tempo(app, rid):
    n = cl(app, "admin").post("/api/reservas/%d/notas" % rid, json={"texto": "base"}).get_json()
    def f(c, k):
        if k % 2:
            return c.post("/api/notas/%d/ocultar" % n["id"], json={"motivo": "engano", "versao": 1})
        return c.post("/api/notas/%d/corrigir" % n["id"], json={"texto": "novo", "versao": 1})
    r = paralelo(app, "atendente", 6, f)
    assert all(s in (200, 409) for s, _ in r), r
    assert contar(app, "SELECT COUNT(*) FROM nota WHERE tipo<>'nota'") >= 1


def test_governanca_dois_marcam_a_mesma_unidade(app):
    c0 = cl(app, "admin")
    v = next(u for u in c0.get("/api/governanca").get_json()["unidades"] if u["u"] == "202")["versao"]
    r = paralelo(app, "atendente", 6, lambda c, k: c.post("/api/governanca/acao", json={"acao": "iniciar", "unidades": [{"u": "202", "versao": v}]}))
    cont = Counter(s for s, _ in r)
    assert cont[200] >= 1 and set(cont) <= {200, 409}, r
    assert contar(app, "SELECT COUNT(*) FROM governanca_evento WHERE unidade='202'") == 1


def test_reservas_simultaneas_mesma_unidade_so_uma(app):
    corpo = dict(RES, a="203")
    r = paralelo(app, "atendente", 6, lambda c, k: c.post("/api/reservas", json=corpo))
    assert Counter(s for s, _ in r) == {201: 1, 409: 5}, r
