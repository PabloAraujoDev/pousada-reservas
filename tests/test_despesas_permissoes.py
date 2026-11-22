"""Despesas: matriz de permissões nos 6 papéis e vazamento do valor em TODAS as rotas de leitura."""
import re

import pytest

from pousada.permissoes import capacidades
from tests.conftest import criar_app_teste
from tests.test_despesas import AGORA, cli, lancar, nova_reserva
from tests.test_despesas_seguranca import DESCR, MARCADOR

PAPEIS = ["admin", "atendente", "recepcao", "diretoria", "consulta", "camareira"]
VER = {"admin", "atendente", "recepcao", "diretoria"}
LANCAR = {"admin", "atendente", "recepcao"}
ESTORNAR = {"admin", "atendente"}


@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def test_capacidades_por_papel():
    for papel in PAPEIS:
        c = capacidades(papel)
        assert ("despesas.ver" in c) == (papel in VER), papel
        assert ("despesas.lancar" in c) == (papel in LANCAR), papel
        assert ("despesas.estornar" in c) == (papel in ESTORNAR), papel
        assert ("despesas.conta" in c) == (papel in LANCAR), papel
        if "despesas.lancar" in c or "despesas.estornar" in c:
            assert "despesas.ver" in c            # quem escreve também precisa ler
    assert not any(x.startswith("despesas.") for x in capacidades("consulta") | capacidades("camareira"))


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_das_rotas_de_despesas(app, papel):
    rid = nova_reserva(app)["id"]
    lid = lancar(cli(app, "admin"), rid, chave="chave-base-1").get_json()["id"]
    c = cli(app, papel, "u_" + papel)
    assert (c.get("/api/reservas/%d/despesas" % rid).status_code == 200) == (papel in VER)
    assert (c.get("/api/despesas/resumo").status_code == 200) == (papel in VER)
    r = c.post("/api/reservas/%d/despesas" % rid, json={"item_id": 1, "item_versao": 1, "quantidade": 1, "chave": "chave-novo-" + papel})
    assert (r.status_code == 201) == (papel in LANCAR)
    if papel not in LANCAR:
        assert r.status_code == 403 and "permissão" in r.get_json()["erro"]
    e = c.post("/api/despesas/%d/estorno" % lid, json={"motivo": "digitado errado"})
    assert (e.status_code == 201) == (papel in ESTORNAR)
    if papel not in ESTORNAR:
        assert e.status_code == 403


def _urls_get(app, rid):
    """Todas as rotas GET do aplicativo (menos estáticos e despesas), com parâmetros preenchidos."""
    urls = set()
    for regra in app.url_map.iter_rules():
        if "GET" not in regra.methods or regra.rule.startswith(("/static", "/api/despesas", "/api/reservas/<int:rid>/despesas",
                                                                     "/api/reservas/<int:rid>/lancamentos", "/api/reservas/<int:rid>/pagamentos")):
            continue
        urls.add(re.sub(r"<int:[a-z_]+>", str(rid), re.sub(r"<[a-z_]+>", "201", regra.rule)))
    urls |= {"/api/export.csv?inicio=2026-10-26&dias=7", "/api/folha.pdf?inicio=2026-10-26&orientacao=retrato",
             "/api/camareiras?inicio=2026-10-26&fim=2026-11-02&estadias=1&nomes=1", "/api/reservas?canceladas=1",
             "/api/historico?limite=500"}
    return sorted(urls)


@pytest.mark.parametrize("papel", PAPEIS)
def test_valor_e_descricao_nao_vazam_em_nenhuma_outra_rota(app, papel):
    rid = nova_reserva(app)["id"]
    lid = lancar(cli(app, "admin"), rid, descricao=DESCR, valor_unit_centavos=MARCADOR).get_json()["id"]
    cli(app, "admin").post("/api/despesas/%d/estorno" % lid, json={"motivo": "motivo privado xyz"})
    lancar(cli(app, "admin"), rid, descricao=DESCR, valor_unit_centavos=MARCADOR, chave="chave-segunda")
    c = cli(app, papel, "v_" + papel)
    urls = _urls_get(app, rid)
    assert len(urls) > 15
    for url in urls:
        corpo = c.get(url).get_data()
        texto = corpo.decode("utf-8", "ignore")
        for proibido in (str(MARCADOR), str(2 * MARCADOR), DESCR, "privado xyz", "15,54", "7.771,23", "7771,23"):
            assert proibido not in texto, "%s vazou em %s para %s" % (proibido, url, papel)
        assert str(MARCADOR).encode() not in corpo


@pytest.mark.parametrize("papel", PAPEIS)
def test_tem_despesa_na_lista_so_para_quem_ve_despesas(app, papel):
    rid = nova_reserva(app)["id"]
    lancar(cli(app, "admin"), rid)
    lista = cli(app, papel, "w_" + papel).get("/api/reservas").get_json()
    if papel in VER:
        assert lista[0]["tem_despesa"] is True
    else:
        assert all("tem_despesa" not in r for r in lista)
    assert "centavos" not in cli(app, papel, "w_" + papel).get("/api/reservas").get_data(as_text=True)


def test_detalhe_da_reserva_sem_centavos_para_consulta(app):
    rid = nova_reserva(app)["id"]
    lancar(cli(app, "admin"), rid)
    assert "centavos" not in cli(app, "consulta").get("/api/reservas/%d" % rid).get_data(as_text=True)


def test_csv_e_importacao_nao_criam_nem_trazem_despesas(app):
    nova_reserva(app)
    assert "despesa" not in cli(app, "admin").get("/api/export.csv").get_data(as_text=True).lower()


def test_desfazer_importacao_com_despesa_409(app):
    from pousada.db import conectar
    rid = nova_reserva(app)["id"]
    con = conectar(app.config["CAMINHO_BANCO"])
    lote = con.execute("INSERT INTO importacoes (arquivo, criado) VALUES ('t.xlsx', 'x')").lastrowid
    con.execute("UPDATE reservas SET lote_id=? WHERE id=?", (lote, rid))
    con.close()
    c = cli(app, "admin")
    assert lancar(c, rid).status_code == 201
    assert c.post("/api/importar/desfazer/%d" % lote).status_code == 409
    assert c.get("/api/reservas/%d" % rid).status_code == 200            # a reserva continua lá
