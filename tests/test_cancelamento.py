"""Cancelamento lógico, reativação, exclusão definitiva e a migração 005 (CHECKs + cópia dos dados)."""
import os
import shutil
import sqlite3

import pytest

from pousada.db import conectar, iniciar_banco
from pousada.regras import cafe_do_dia, hospedes_na_noite
from tests.conftest import cliente_como
from tests.test_reservas import corpo

PASTA_REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
COLUNAS = "id,a,nome,extras,n,i,f,p,o,criado,alterado,versao,grupo,lote_id,chave_import"


def cancelar(c, r, motivo="Hóspede desistiu"):
    return c.delete("/api/reservas/%d" % r["id"], json={"versao": r["versao"], "motivo": motivo})


def test_cancelada_libera_a_unidade_e_some_dos_calculos(app, cli):
    r = cli.post("/api/reservas", json=corpo(i="2026-10-10", f="2026-10-12", n=3)).get_json()
    assert cli.post("/api/reservas", json=corpo(i="2026-10-11", f="2026-10-13")).status_code == 409
    c = cancelar(cli, r)
    assert c.status_code == 200 and c.get_json()["status"] == "cancelada" and c.get_json()["cancelado_por"] == "admin"
    assert cli.post("/api/reservas", json=corpo(i="2026-10-11", f="2026-10-13")).status_code == 201     # agora cabe
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert cafe_do_dia(con, "2026-10-12") == 2 and hospedes_na_noite(con, "2026-10-11") == 2        # só a nova (n=2)
    finally:
        con.close()
    folha = cli.get("/api/camareiras?inicio=2026-10-10&fim=2026-10-10").get_json()["dias"][0]
    assert folha["total_entradas"] == 0                                    # a cancelada não aparece para as camareiras


def test_listar_canceladas_so_com_permissao(app, cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    cancelar(cli, r, "Motivo X")
    lista = cli.get("/api/reservas?canceladas=1").get_json()
    assert len(lista) == 1 and lista[0]["motivo_cancelamento"] == "Motivo X" and lista[0]["cancelado_em"]
    assert cliente_como(app, "atendente").get("/api/reservas?canceladas=1").status_code == 200
    for papel in ("recepcao", "camareira", "diretoria"):
        assert cliente_como(app, papel).get("/api/reservas?canceladas=1").status_code == 403
    assert "Motivo X" not in cli.get("/api/reservas").get_data(as_text=True)         # lista normal não traz o motivo


def test_reativar_revalida_conflito(app, cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    cancelar(cli, r)
    outra = cli.post("/api/reservas", json=corpo()).get_json()                     # ocupa o mesmo período
    cancelada = cli.get("/api/reservas?canceladas=1").get_json()[0]
    ruim = cli.post("/api/reservas/%d/reativar" % r["id"], json={"versao": cancelada["versao"]})
    assert ruim.status_code == 409 and "Conflito" in ruim.get_json()["erro"]
    cancelar(cli, outra)
    ok = cli.post("/api/reservas/%d/reativar" % r["id"], json={"versao": cancelada["versao"]})
    assert ok.status_code == 200 and ok.get_json()["status"] == "ativa" and ok.get_json()["motivo_cancelamento"] is None
    assert [x["id"] for x in cli.get("/api/reservas").get_json()] == [r["id"]]
    # não dá para reativar quem já está ativa
    assert cli.post("/api/reservas/%d/reativar" % r["id"], json={"versao": ok.get_json()["versao"]}).status_code == 409


def test_nao_edita_reserva_cancelada(app, cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    c = cancelar(cli, r).get_json()
    resp = cli.put("/api/reservas/%d" % r["id"], json=corpo(nome="Novo", versao=c["versao"]))
    assert resp.status_code == 409 and "cancelada" in resp.get_json()["erro"]


def test_exclusao_definitiva_so_admin_e_deixa_historico(app, cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    at = cliente_como(app, "atendente")
    assert at.post("/api/reservas/%d/excluir-definitivo" % r["id"], json={"versao": 1}).status_code == 403
    assert cli.post("/api/reservas/%d/excluir-definitivo" % r["id"], json={"versao": 9}).status_code == 409
    assert cli.post("/api/reservas/%d/excluir-definitivo" % r["id"], json={"versao": 1}).status_code == 200
    assert cli.post("/api/reservas/%d/excluir-definitivo" % r["id"], json={"versao": 1}).status_code == 404
    acoes = [h["acao"] for h in cli.get("/api/historico?entidade=reserva").get_json()]
    assert acoes == ["excluir", "criar"]


def test_cancelar_e_reativar_ficam_no_historico_da_reserva(app, cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    c = cancelar(cli, r, "SEGREDO-MOTIVO").get_json()
    cli.post("/api/reservas/%d/reativar" % r["id"], json={"versao": c["versao"]})
    h = cliente_como(app, "atendente").get("/api/reservas/%d/historico" % r["id"]).get_json()
    assert [x["acao"] for x in h] == ["reativar", "cancelar", "criar"]
    assert h[1]["depois"] == {"status": "cancelada"} and "SEGREDO" not in str(h)


def test_motivo_obrigatorio_e_limitado(cli):
    r = cli.post("/api/reservas", json=corpo()).get_json()
    assert cancelar(cli, r, "   ").status_code == 400
    assert cancelar(cli, r, "x" * 301).status_code == 400


def test_importacao_nao_ressuscita_cancelada_mas_cancelada_nao_gera_conflito(app, cli):
    from datetime import date
    from tests.test_importacao import corpo_confirmar, planilha_limpa, previa
    app.config["HOJE"] = date(2026, 10, 1)
    j = previa(cli, planilha_limpa()).get_json()
    cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    primeira = cli.get("/api/reservas").get_json()[0]
    cancelar(cli, primeira)
    j2 = previa(cli, planilha_limpa()).get_json()
    assert j2["contadores"]["erros"] == 0                              # a cancelada não conflita com ela mesma
    assert cli.post("/api/importar/confirmar", json=corpo_confirmar(j2)).get_json()["criadas"] == 0
    assert len(cli.get("/api/reservas").get_json()) == 2               # continua cancelada, não voltou


# ---------------------------------------------------------------- migração 005

def _banco_ate_004(tmp_path):
    pasta = tmp_path / "mig"
    pasta.mkdir()
    for nome in os.listdir(PASTA_REAL):
        if int(nome.split("_")[0]) <= 4:
            shutil.copy(os.path.join(PASTA_REAL, nome), pasta)
    banco = str(tmp_path / "velho.db")
    iniciar_banco(banco, str(pasta))
    return banco


def test_migracao_005_preserva_dados_ids_e_contador(tmp_path):
    banco = _banco_ate_004(tmp_path)
    con = conectar(banco)
    for k, nome in enumerate(["A", "B", "C"], start=1):
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,criado,alterado,versao,grupo,lote_id,chave_import)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("20%d" % k, nome, "ex" + nome, k, "2026-10-1%d" % k, "2026-10-2%d" % k, "pago", "obs" + nome,
                     "c", "a", k + 1, "G" + nome, 7, "chave" + nome))
    con.execute("DELETE FROM reservas WHERE nome='C'")            # o id 3 já foi usado: não pode ser reaproveitado
    antes = [tuple(r) for r in con.execute("SELECT %s FROM reservas ORDER BY id" % COLUNAS)]
    con.close()
    iniciar_banco(banco, PASTA_REAL, pasta_backup=str(tmp_path / "bk"))
    con = conectar(banco)
    try:
        depois = [tuple(r) for r in con.execute("SELECT %s FROM reservas ORDER BY id" % COLUNAS)]
        assert depois == antes and len(depois) == 2
        assert {r[0] for r in con.execute("SELECT status FROM reservas")} == {"ativa"}
        novo = con.execute("INSERT INTO reservas (a,nome,n,i,f,criado,alterado) "
                           "VALUES ('301','N',1,'2026-11-01','2026-11-02','c','a')").lastrowid
        assert novo == 4                                              # contador preservado (nada de id repetido)
        idx = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reservas'")}
        assert {"idx_reservas_apto_status_datas", "idx_reservas_lote", "idx_reservas_chave"} <= idx
    finally:
        con.close()
    assert len(os.listdir(tmp_path / "bk")) == 1                      # backup feito antes de migrar


BASE = "INSERT INTO reservas (a,nome,n,i,f,p,criado,alterado%s) VALUES ('201','x',%s,'%s','%s','%s','c','a'%s)"


@pytest.mark.parametrize("n,i,f,p,status", [
    (2, "2026-10-12", "2026-10-12", "pago", None),         # saída = entrada
    (2, "2026-10-12", "2026-10-10", "pago", None),         # saída antes da entrada
    (2, "2026-10-10", "2026-10-12", "inventado", None),    # pagamento inexistente
    (0, "2026-10-10", "2026-10-12", "pago", None),         # pessoas demais ou de menos
    (51, "2026-10-10", "2026-10-12", "pago", None),
    (2, "10/10/2026", "2026-10-12", "pago", None),         # data fora do padrão
    (2, "2026-10-10", "2026-10-12", "pago", "apagada"),    # status inexistente
])
def test_check_do_banco_recusa_dados_invalidos(app, n, i, f, p, status):
    sql = BASE % (",status" if status else "", n, i, f, p, ",'%s'" % status if status else "")
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
    finally:
        con.close()


def test_migracao_005_com_dado_invalido_desfaz_tudo(tmp_path):
    banco = _banco_ate_004(tmp_path)
    con = conectar(banco)
    con.execute("INSERT INTO reservas (a,nome,i,f,criado,alterado) VALUES ('201','Bom','2026-10-10','2026-10-12','c','a')")
    con.execute("INSERT INTO reservas (a,nome,i,f,criado,alterado) VALUES ('202','Ruim','2026-10-12','2026-10-10','c','a')")
    con.close()
    with pytest.raises(sqlite3.IntegrityError):
        iniciar_banco(banco, PASTA_REAL)
    con = conectar(banco)
    try:
        assert con.execute("SELECT COUNT(*) FROM reservas").fetchone()[0] == 2          # tabela original intacta
        assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] == 4
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='reservas_nova'").fetchone() is None
    finally:
        con.close()
