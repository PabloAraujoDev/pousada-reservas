"""Testes do sistema de reservas (sempre com banco temporário)."""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pousada.db import conectar  # noqa: E402
from tests.conftest import cliente_como  # noqa: E402
from pousada.regras import cafe_do_dia, hospedes_na_noite  # noqa: E402


def corpo(a="201", i="2026-10-10", f="2026-10-12", n=2, **extra):
    d = {"a": a, "nome": "Hóspede Teste", "extras": "", "n": n, "i": i, "f": f, "p": "pendente", "o": ""}
    d.update(extra)
    return d


def test_mesmo_dia_sai_e_entra(cli):
    assert cli.post("/api/reservas", json=corpo(i="2026-10-10", f="2026-10-12")).status_code == 201
    assert cli.post("/api/reservas", json=corpo(i="2026-10-12", f="2026-10-14")).status_code == 201
    assert cli.post("/api/reservas", json=corpo(i="2026-10-08", f="2026-10-10")).status_code == 201


def test_sobreposicao_409(cli):
    assert cli.post("/api/reservas", json=corpo(i="2026-10-10", f="2026-10-12")).status_code == 201
    assert cli.post("/api/reservas", json=corpo(i="2026-10-11", f="2026-10-13")).status_code == 409
    assert cli.post("/api/reservas", json=corpo(i="2026-10-09", f="2026-10-11")).status_code == 409
    # outra unidade não conflita
    assert cli.post("/api/reservas", json=corpo(a="202", i="2026-10-11", f="2026-10-13")).status_code == 201


def test_saida_igual_entrada_400(cli):
    assert cli.post("/api/reservas", json=corpo(i="2026-10-10", f="2026-10-10")).status_code == 400
    assert cli.post("/api/reservas", json=corpo(i="2026-10-10", f="2026-10-09")).status_code == 400


def test_data_inexistente_400(cli):
    assert cli.post("/api/reservas", json=corpo(i="2026-11-31", f="2026-12-02")).status_code == 400


def test_apto_104_recusado(cli):
    r = cli.post("/api/reservas", json=corpo(a="104"))
    assert r.status_code == 400
    assert "ocupada" in r.get_json()["erro"]


def test_editar_sem_mudar_datas_nao_conflita(cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    novo = corpo(nome="Outro Nome", versao=r["versao"])
    resp = cli.put("/api/reservas/%d" % r["id"], json=novo)
    assert resp.status_code == 200
    assert resp.get_json()["versao"] == 2


def test_virada_do_mes(cli):
    r = cli.post("/api/reservas", json=corpo(i="2026-10-30", f="2026-11-02"))
    assert r.status_code == 201
    assert cli.post("/api/reservas", json=corpo(i="2026-10-31", f="2026-11-01")).status_code == 409
    assert cli.post("/api/reservas", json=corpo(i="2026-11-02", f="2026-11-03")).status_code == 201


def test_cafe_e_hospedes(app, cli):
    cli.post("/api/reservas", json=corpo(i="2026-10-10", f="2026-10-12", n=2))
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert cafe_do_dia(con, "2026-10-10") == 0
        assert cafe_do_dia(con, "2026-10-11") == 2
        assert cafe_do_dia(con, "2026-10-12") == 2
        assert hospedes_na_noite(con, "2026-10-10") == 2
        assert hospedes_na_noite(con, "2026-10-11") == 2
        assert hospedes_na_noite(con, "2026-10-12") == 0
    finally:
        con.close()


def test_importar_duas_vezes(cli):
    r1 = cli.post("/api/importar")
    assert r1.status_code == 201 and r1.get_json()["importadas"] >= 10
    assert cli.post("/api/importar").status_code == 409


def test_threads_mesma_unidade(app):
    resultados = []
    barreira = threading.Barrier(2)

    clientes = [cliente_como(app, "atendente", "atendente%d" % k) for k in range(2)]

    def gravar(c):
        barreira.wait()
        resultados.append(c.post("/api/reservas", json=corpo()).status_code)

    ts = [threading.Thread(target=gravar, args=(c,)) for c in clientes]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(resultados) == [201, 409]


def test_conflito_de_versao_no_put(cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    assert cli.put("/api/reservas/%d" % r["id"], json=corpo(nome="A", versao=1)).status_code == 200
    resp = cli.put("/api/reservas/%d" % r["id"], json=corpo(nome="B", versao=1))
    assert resp.status_code == 409
    assert resp.get_json() == {"erro": "Esta reserva foi alterada por outra pessoa"}


def test_cancelar_e_exportar(cli):
    # Desde a etapa 1, DELETE não apaga: cancela (exige motivo) e a reserva continua guardada.
    r = cli.post("/api/reservas", json=corpo()).get_json()
    assert "Hóspede Teste" in cli.get("/api/export.csv").get_data(as_text=True)
    assert "Hóspede Teste" in cli.get("/api/export.csv?inicio=2026-10-09&dias=7").get_data(as_text=True)
    url = "/api/reservas/%d" % r["id"]
    assert cli.delete(url).status_code == 400                                   # sem versão
    assert cli.delete(url, json={"versao": r["versao"]}).status_code == 400     # sem motivo
    assert cli.delete(url, json={"versao": 99, "motivo": "x"}).status_code == 409
    assert cli.delete(url, json={"versao": r["versao"], "motivo": "Hóspede desistiu"}).status_code == 200
    assert cli.delete(url, json={"versao": 2, "motivo": "de novo"}).status_code == 409      # já cancelada
    assert cli.delete("/api/reservas/9999", json={"versao": 1, "motivo": "x"}).status_code == 404
    assert cli.get("/api/reservas").get_json() == []
    assert "Hóspede Teste" not in cli.get("/api/export.csv?inicio=2026-10-09&dias=7").get_data(as_text=True)
    assert "cancelada" in cli.get("/api/export.csv").get_data(as_text=True)


# ---------------------------------------------------------------- passo 0: endurecimentos

@pytest.mark.parametrize("campo,valor", [
    ("nome", "x" * 121), ("extras", "x" * 1001), ("o", "x" * 1001), ("grupo", "x" * 121),
    ("n", 0), ("n", 51), ("n", True), ("n", 2.0), ("n", "2"), ("n", None),
    ("i", "2019-12-30"), ("f", "2101-01-02"), ("nome", 123), ("p", "inventado"),
])
def test_limites_do_servidor(cli, campo, valor):
    d = corpo()
    if campo == "i":
        d["f"] = "2019-12-31"
    d[campo] = valor
    assert cli.post("/api/reservas", json=d).status_code == 400


def test_limites_no_limite_passam(cli):
    d = corpo(nome="x" * 120, extras="y" * 1000, o="z" * 1000, grupo="g" * 120, n=50)
    assert cli.post("/api/reservas", json=d).status_code == 201


def test_estadia_maxima_365_noites(cli):
    assert cli.post("/api/reservas", json=corpo(i="2026-01-01", f="2027-01-01")).status_code == 201       # 365
    r = cli.post("/api/reservas", json=corpo(a="202", i="2026-01-01", f="2027-01-02"))                    # 366
    assert r.status_code == 400 and "noites" in r.get_json()["erro"]


def test_erros_viram_json_em_api(cli):
    for r in (cli.get("/api/nao-existe"), cli.patch("/api/reservas"), cli.get("/api/reservas/9999999/xyz")):
        assert r.content_type.startswith("application/json")
        assert "erro" in r.get_json()
    assert cli.get("/api/nao-existe").status_code == 404
    assert cli.patch("/api/reservas").status_code == 405


def test_erro_500_vira_json(app, cli, monkeypatch):
    def quebrar(*a, **k):
        raise RuntimeError("falha de teste")
    monkeypatch.setattr("pousada.rotas.validar_reserva", quebrar)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = cli.post("/api/reservas", json=corpo())
    assert r.status_code == 500 and r.content_type.startswith("application/json")
    assert "falha de teste" not in r.get_data(as_text=True)          # não vaza detalhes


def test_csv_neutraliza_formula(cli):
    for k, nome in enumerate(["=1+1", "+cmd", "-2", "@soma"]):
        cli.post("/api/reservas", json=corpo(a="30%d" % (k + 1), nome=nome))
    saida = cli.get("/api/export.csv").get_data(as_text=True)
    for nome in ["'=1+1", "'+cmd", "'-2", "'@soma"]:
        assert ";" + nome + ";" in saida
    assert ";=1+1;" not in saida


def test_celula_csv_trata_tab_e_cr():
    from pousada.rotas import _celula_csv
    assert _celula_csv("\tabc") == "'\tabc" and _celula_csv("\rabc") == "'\rabc"
    assert _celula_csv("normal") == "normal" and _celula_csv(5) == 5


def test_texto_com_controle_de_direcao_recusado_com_mensagem_clara(cli):
    """Regressão: antes a mensagem era só 'Observações inválido'. Texto RTL comum (hebraico, árabe) continua valendo."""
    base = {"a": "101", "nome": "Ok", "n": 1, "i": "2026-11-10", "f": "2026-11-11", "p": "pendente"}
    r = cli.post("/api/reservas", json=dict(base, o="texto ‮oculto"))
    assert r.status_code == 400 and "caracteres não permitidos" in r.get_json()["erro"] and "Observações" in r.get_json()["erro"]
    assert cli.post("/api/reservas", json=dict(base, o="שלום עולם مرحبا")).status_code == 201
