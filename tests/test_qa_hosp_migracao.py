"""QA: migração 013 -> 015 de uma vez, sobre um banco 'de produção' realista (195 reservas, despesas, histórico, contas fechadas)."""
import os
import shutil

import pytest

from pousada import create_app
from pousada.db import conectar, iniciar_banco
from tests.conftest import cliente_como

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
    for k in range(195):
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,tipo,diaria_centavos) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                    ("%d" % (100 + k % 20), "Hóspede ção %d" % k, "", 2, "2026-%02d-%02d" % (1 + k % 9, 1 + k % 20),
                     "2026-%02d-%02d" % (1 + k % 9, 22 + k % 6), "pago", "", "", "2026-01-01 10:00:00", "2026-01-01 10:00:00",
                     "cancelada" if k % 17 == 0 else "ativa", "socio", None if k % 3 else 25000 + k))
        con.execute("INSERT INTO historico (em,usuario_login,acao,entidade,entidade_id,antes,depois) VALUES ('2026-01-01 10:00:00','adm','criar','reserva',?,NULL,'{}')", (k + 1,))
    for rid in range(2, 60, 3):
        con.execute("INSERT INTO despesa_lancamento (reserva_id,tipo,categoria,descricao,quantidade,valor_unit_centavos,total_centavos,apto,em) "
                    "VALUES (?,'lancamento','bar','Água',2,800,1600,'101','2026-02-01 10:00:00')", (rid,))
    con.execute("INSERT INTO despesa_conta (reserva_id,situacao,quitacao,fechada_em,quitada_em) VALUES (2,'fechada','quitada','2026-02-02 10:00:00','2026-02-02 10:00:00')")
    con.close()
    return caminho


COLS = "id,a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,tipo,diaria_centavos"


def _foto(caminho):
    con = conectar(caminho)
    try:
        return {t: [tuple(r) for r in con.execute("SELECT %s FROM %s ORDER BY 1" % (COLS if t == "reservas" else "*", t))]
                for t in ("reservas", "historico", "despesa_conta", "usuarios")}, \
               [tuple(r)[:15] for r in con.execute("SELECT * FROM despesa_lancamento ORDER BY id")]
    finally:
        con.close()


def test_013_para_015_direto_preserva_tudo_e_e_idempotente(banco_v13, tmp_path):
    antes, desp = _foto(banco_v13)
    bk = str(tmp_path / "bk")
    iniciar_banco(banco_v13, REAL, pasta_backup=bk)
    assert len(os.listdir(bk)) == 1                                    # um backup, antes de migrar
    depois, desp2 = _foto(banco_v13)
    assert depois == antes and desp2 == desp
    iniciar_banco(banco_v13, REAL, pasta_backup=bk)                    # segunda subida: nada a fazer, nem novo backup
    assert len(os.listdir(bk)) == 1 and _foto(banco_v13) == (antes, desp)
    con = conectar(banco_v13)
    assert [r[0] for r in con.execute("SELECT versao FROM schema_version ORDER BY 1")] == list(range(1, 18))
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()


def test_app_sobe_e_conta_antiga_continua_coerente(banco_v13, tmp_path):
    a = create_app(banco_v13, config={"SECRET_KEY": "x", "PASTA_INSTANCIA": str(tmp_path / "i"), "PASTA_BACKUP": str(tmp_path / "bk")})
    c = cliente_como(a, "admin")
    d = c.get("/api/reservas/5/pagamentos").get_json()                  # reserva 5 (k=4) sem diária e sem despesa: conta zerada
    assert d["total"]["pagamentos_centavos"] == 0 and d["total"]["saldo_centavos"] == d["total"]["conta_centavos"]
    d2 = c.get("/api/reservas/2/pagamentos").get_json()                 # conta fechada no passado, com despesa de R$ 16,00
    assert d2["conta"]["situacao"] == "fechada" and d2["total"]["conta_centavos"] >= 1600
    assert c.get("/api/reservas/2/lancamentos").status_code == 200
