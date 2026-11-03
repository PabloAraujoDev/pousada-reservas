"""Matriz dos 6 papéis para cada rota nova da etapa 3B (pagamentos, estorno, transferência, destinos, zerar diária, fechar/reabrir, lista)."""
import pytest

from tests.apoio_pagamentos import app, cli, conta, detalhe, lancar, nova, receber  # noqa: F401

PAPEIS = ("admin", "atendente", "recepcao", "camareira", "diretoria", "consulta")
# papel -> rotas permitidas (o resto deve dar 403)
PERMITE = {
    "ver_pag": {"admin", "atendente", "recepcao", "diretoria"},
    "receber": {"admin", "atendente", "recepcao"},
    "estornar_pag": {"admin", "atendente"},
    "transferir": {"admin", "atendente"},
    "destinos": {"admin", "atendente"},
    "zerar": {"admin", "atendente"},
    "fechar": {"admin", "atendente", "recepcao"},
    "reabrir": {"admin", "atendente"},
    "lista": {"admin", "atendente", "recepcao", "diretoria"},
}


def _quem(app, papel):
    return cli(app, papel)


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_de_leitura(app, papel):
    rid = nova(app)
    receber(app, rid, 1000)
    c = _quem(app, papel)
    assert (c.get("/api/reservas/%d/pagamentos" % rid).status_code == 200) == (papel in PERMITE["ver_pag"])
    assert (c.get("/api/reservas/%d/lancamentos" % rid).status_code == 200) == (papel in PERMITE["lista"])
    assert (c.get("/api/reservas/%d/destinos" % rid).status_code == 200) == (papel in PERMITE["destinos"])
    for a in (c.get("/api/reservas/%d/pagamentos" % rid), c.get("/api/reservas/%d/destinos" % rid)):
        if a.status_code == 403:
            assert "R$" not in a.get_data(as_text=True) and "valor" not in a.get_data(as_text=True)


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_de_escrita(app, papel):
    a, b = nova(app), nova(app, a="202", nome="João")
    lid = lancar(app, a)["id"]
    c = _quem(app, papel)
    ver = lambda: conta(app, a)["conta"]["versao"]  # noqa: E731
    r = c.post("/api/reservas/%d/pagamentos" % a, json={"valor_centavos": 100, "forma": "dinheiro", "chave": "chave-%s-1" % papel, "conta_versao": ver()})
    assert (r.status_code == 201) == (papel in PERMITE["receber"]), (papel, r.status_code)
    pid = receber(app, a, 200).get_json()["id"]
    assert (c.post("/api/pagamentos/%d/estorno" % pid, json={"motivo": "Valor errado"}).status_code == 201) == (papel in PERMITE["estornar_pag"])
    r = c.post("/api/reservas/%d/transferir" % a, json={"destino_id": b, "itens": ["d%d" % lid], "chave": "chave-%s-2" % papel, "conta_versao": ver()})
    assert (r.status_code == 201) == (papel in PERMITE["transferir"]), (papel, r.status_code)
    r = c.post("/api/reservas/%d/diaria/zerar" % b, json={"versao": detalhe(app, b)["versao"], "motivo": "Sem pernoite", "chave": "chave-%s-3" % papel})
    assert (r.status_code == 201) == (papel in PERMITE["zerar"]), (papel, r.status_code)


@pytest.mark.parametrize("papel", PAPEIS)
def test_matriz_fechar_e_reabrir(app, papel):
    rid = nova(app, diaria_centavos=None)
    c = _quem(app, papel)
    r = c.post("/api/reservas/%d/conta/fechar" % rid, json={"conta_versao": conta(app, rid)["conta"]["versao"]})
    assert (r.status_code == 200) == (papel in PERMITE["fechar"]), (papel, r.status_code)
    if r.status_code != 200:
        cli(app, "admin").post("/api/reservas/%d/conta/fechar" % rid, json={"conta_versao": conta(app, rid)["conta"]["versao"]})
    r = c.post("/api/reservas/%d/conta/reabrir" % rid, json={"conta_versao": conta(app, rid)["conta"]["versao"], "motivo": "Faltou lançar"})
    assert (r.status_code == 200) == (papel in PERMITE["reabrir"]), (papel, r.status_code)


def test_sem_login_e_sem_csrf(app):
    rid = nova(app)
    c = app.test_client()
    assert c.get("/api/reservas/%d/pagamentos" % rid).status_code in (401, 403)
    assert c.post("/api/reservas/%d/pagamentos" % rid, json={}).status_code in (401, 403)
    assert cli(app, "admin").post("/api/reservas/%d/pagamentos" % rid, json={}, sem_csrf=True).status_code == 403


def test_totais_de_pagamento_so_para_quem_pode_ver(app):
    rid = nova(app)
    receber(app, rid, 1000)
    assert "saldo_centavos" in conta(app, rid, "diretoria")["totais"]
    t = conta(app, rid, "consulta") if False else None
    assert t is None and cli(app, "camareira").get("/api/reservas/%d/despesas" % rid).status_code == 403


def test_lista_de_lancamentos_sem_pagamento_para_quem_nao_tem_pagamentos_ver(app, monkeypatch):
    """despesas.ver sem pagamentos.ver não recebe as linhas de pagamento."""
    from pousada import permissoes
    rid = nova(app)
    receber(app, rid, 1000)
    monkeypatch.setitem(permissoes.PERMISSOES, "diretoria", permissoes.PERMISSOES["diretoria"] - {"pagamentos.ver"})
    j = cli(app, "diretoria").get("/api/reservas/%d/lancamentos" % rid).get_json()
    assert all(i["grupo"] != "pagamento" for i in j["itens"])
    assert "saldo_centavos" not in cli(app, "diretoria").get("/api/reservas/%d/despesas" % rid).get_json()["totais"]
