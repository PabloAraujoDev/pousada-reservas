"""Hóspedes da hospedagem (titular + acompanhantes), placa e ficha FNRH: validações hostis, máscara, log sem dado pessoal, versão."""
import json
import threading

import pytest

from tests.test_hospedagem import AGORA, acao, app, cli, detalhe, nova, sql  # noqa: F401

CPF = "123.456.789-09"
MARCA = "7788991"          # trecho de documento que nunca pode aparecer em log, histórico nem para quem não pode ver


def put(app, rid, corpo, papel="admin"):
    if "versao" not in corpo:
        corpo = dict(corpo, versao=detalhe(app, rid)["versao"])
    return cli(app, papel).put("/api/reservas/%d/hospedes" % rid, json=corpo)


def lista(app, rid, papel="admin"):
    return cli(app, papel).get("/api/reservas/%d/hospedes" % rid)


def test_lista_vazia_tem_so_o_titular_com_o_nome_da_reserva(app):
    rid = nova(app)["id"]
    d = lista(app, rid).get_json()
    assert d["titular"]["nome"] == "Maria Silva" and d["acompanhantes"] == [] and d["n"] == 3 and d["pode_editar"] is True


def test_salvar_titular_e_acompanhantes_e_ler_de_volta(app):
    rid = nova(app)["id"]
    r = put(app, rid, {"titular": {"documento": CPF, "nascimento": "1980-05-17", "nacionalidade": "Brasileira", "profissao": "Médico"},
                       "acompanhantes": [{"nome": "João Silva", "tipo": "adulto", "documento": "MG-1234567"},
                                         {"nome": "Ana Silva", "tipo": "crianca", "nascimento": "2018-02-01"}]})
    assert r.status_code == 200, r.get_data(as_text=True)
    d = lista(app, rid).get_json()
    assert d["titular"]["documento"] == CPF and d["titular"]["profissao"] == "Médico"
    assert [(a["nome"], a["tipo"]) for a in d["acompanhantes"]] == [("João Silva", "adulto"), ("Ana Silva", "crianca")]
    assert d["versao"] == detalhe(app, rid)["versao"] > 1


def test_edicao_remocao_e_ordem_pelo_id(app):
    rid = nova(app)["id"]
    put(app, rid, {"titular": {}, "acompanhantes": [{"nome": "A Um"}, {"nome": "B Dois"}]})
    ids = [a["id"] for a in lista(app, rid).get_json()["acompanhantes"]]
    r = put(app, rid, {"titular": {}, "acompanhantes": [{"id": ids[1], "nome": "B Dois Novo", "tipo": "crianca"}]})
    assert r.status_code == 200
    ac = lista(app, rid).get_json()["acompanhantes"]
    assert [(a["id"], a["nome"], a["tipo"]) for a in ac] == [(ids[1], "B Dois Novo", "crianca")]
    assert sql(app, "SELECT COUNT(*) FROM hospedagem_hospede")[0][0] == 1          # removido de verdade (minimização)
    assert put(app, rid, {"titular": {}, "acompanhantes": [{"id": 99999, "nome": "X Fantasma"}]}).status_code == 422


def test_sem_mudanca_nao_sobe_a_versao_nem_gera_log(app):
    rid = nova(app)["id"]
    put(app, rid, {"titular": {}, "acompanhantes": [{"nome": "A Um"}]})
    v, ev = detalhe(app, rid)["versao"], sql(app, "SELECT COUNT(*) FROM hospedagem_evento")[0][0]
    a = lista(app, rid).get_json()["acompanhantes"]
    assert put(app, rid, {"titular": {}, "acompanhantes": [{"id": a[0]["id"], "nome": "A Um"}]}).status_code == 200
    assert detalhe(app, rid)["versao"] == v and sql(app, "SELECT COUNT(*) FROM hospedagem_evento")[0][0] == ev


def test_limite_ligado_ao_numero_de_pessoas_e_reducao_de_n(app):
    rid = nova(app, n=2)["id"]
    r = put(app, rid, {"titular": {}, "acompanhantes": [{"nome": "A Um"}, {"nome": "B Dois"}]})
    assert r.status_code == 422 and "número de pessoas" in r.get_json()["erro"]
    assert put(app, rid, {"titular": {}, "acompanhantes": [{"nome": "A Um"}]}).status_code == 200
    v = detalhe(app, rid)
    corpo = {k: v[k] for k in ("a", "nome", "extras", "i", "f", "p", "o", "grupo", "versao")}
    r = cli(app, "admin").put("/api/reservas/%d" % rid, json=dict(corpo, n=1))
    assert r.status_code == 409 and "acompanhante" in r.get_json()["erro"]


def test_versao_velha_e_duplo_clique_dao_409(app):
    rid = nova(app)["id"]
    v = detalhe(app, rid)["versao"]
    assert put(app, rid, {"versao": v, "titular": {}, "acompanhantes": [{"nome": "A Um"}]}).status_code == 200
    r = put(app, rid, {"versao": v, "titular": {}, "acompanhantes": [{"nome": "A Um"}]})
    assert r.status_code == 409 and sql(app, "SELECT COUNT(*) FROM hospedagem_hospede")[0][0] == 1


def test_duas_gravacoes_simultaneas_so_uma_vence(app):
    rid = nova(app)["id"]
    v = detalhe(app, rid)["versao"]
    saida = []

    def enviar(nome):
        saida.append(cli(app, "admin", "u" + nome).put("/api/reservas/%d/hospedes" % rid, json={
            "versao": v, "titular": {}, "acompanhantes": [{"nome": "Hóspede " + nome}]}).status_code)

    ts = [threading.Thread(target=enviar, args=(x,)) for x in ("A", "B")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(saida) == [200, 409] and sql(app, "SELECT COUNT(*) FROM hospedagem_hospede")[0][0] == 1


HOSTIS = [
    ({"acompanhantes": [{"nome": ""}]}, 422), ({"acompanhantes": [{"nome": "   "}]}, 422), ({"acompanhantes": [{"nome": 5}]}, 422),
    ({"acompanhantes": [{"nome": "x" * 121}]}, 422), ({"acompanhantes": [{"nome": "Fulano‮evil"}]}, 422),
    ({"acompanhantes": [{"nome": "4111 1111 1111 1111"}]}, 422), ({"acompanhantes": [{"nome": "Ok Nome", "tipo": "bebe"}]}, 422),
    ({"acompanhantes": [{"nome": "Ok Nome", "documento": "4111111111111111"}]}, 422),
    ({"acompanhantes": [{"nome": "Ok Nome", "documento": "<script>"}]}, 422), ({"acompanhantes": [{"nome": "Ok Nome", "documento": "ab"}]}, 422),
    ({"acompanhantes": [{"nome": "Ok Nome", "documento": "1" * 21}]}, 422), ({"acompanhantes": [{"nome": "Ok Nome", "documento": 12345}]}, 422),
    ({"acompanhantes": [{"nome": "Ok Nome", "nascimento": "2999-01-01"}]}, 422), ({"acompanhantes": [{"nome": "Ok Nome", "nascimento": "1800-01-01"}]}, 422),
    ({"acompanhantes": [{"nome": "Ok Nome", "nascimento": "31/12/2000"}]}, 422), ({"acompanhantes": [{"nome": "Ok Nome", "profissao": "x" * 61}]}, 422),
    ({"acompanhantes": [{"nome": "Ok Nome", "destino": "4111-1111-1111-1111"}]}, 422), ({"acompanhantes": [{"nome": "Ok", "id": True}]}, 422),
    ({"acompanhantes": "x"}, 400), ({"acompanhantes": [1]}, 400), ({"acompanhantes": [], "titular": {"tipo": "x"}}, 422),
    ({"acompanhantes": [{"nome": "Dup", "id": 1}, {"nome": "Dup2", "id": 1}]}, 422), ({"acompanhantes": [{"nome": "A"}] * 3}, 422),
]


@pytest.mark.parametrize("corpo,status", HOSTIS)
def test_entradas_hostis_sao_recusadas_sem_gravar(app, corpo, status):
    rid = nova(app)["id"]
    r = put(app, rid, dict(corpo))
    assert r.status_code == status and sql(app, "SELECT COUNT(*) FROM hospedagem_hospede")[0][0] == 0
    assert "4111" not in r.get_data(as_text=True)                       # a mensagem nunca repete o texto recebido


def test_corpo_que_nao_e_objeto_ou_sem_versao(app):
    rid = nova(app)["id"]
    c = cli(app, "admin")
    assert c.put("/api/reservas/%d/hospedes" % rid, json=[1, 2]).status_code == 400
    assert c.put("/api/reservas/%d/hospedes" % rid, json={"acompanhantes": []}).status_code == 400
    assert c.put("/api/reservas/%d/hospedes" % rid, json={"versao": "1"}).status_code == 400
    assert c.put("/api/reservas/%d/hospedes" % rid, data="x", content_type="text/plain").status_code == 415


def test_xss_fica_como_texto_e_documento_nao_vai_para_historico_nem_log(app):
    rid = nova(app)["id"]
    xss = '<img src=x onerror="window.__xss=1">'
    put(app, rid, {"titular": {"documento": "MG" + MARCA}, "acompanhantes": [{"nome": xss, "destino": "Belo Horizonte"}]})
    assert lista(app, rid).get_json()["acompanhantes"][0]["nome"] == xss        # o servidor guarda o texto; a tela usa textContent
    tudo = json.dumps(sql(app, "SELECT * FROM historico")) + json.dumps(sql(app, "SELECT * FROM hospedagem_evento"))
    assert MARCA not in tudo and "onerror" not in tudo and "Belo Horizonte" not in tudo and "João" not in tudo
    h = cli(app, "admin").get("/api/reservas/%d/historico" % rid).get_data(as_text=True)
    assert MARCA not in h and "hospedes_alterados" in h


def test_log_da_hospedagem_e_imutavel(app):
    rid = nova(app)["id"]
    acao(app, rid, "checkin")
    for comando in ("UPDATE hospedagem_evento SET detalhe='x'", "DELETE FROM hospedagem_evento"):
        with pytest.raises(Exception, match="não pode ser"):
            sql(app, comando)
    with pytest.raises(Exception, match="inexistente"):
        sql(app, "INSERT INTO hospedagem_evento (reserva_id, acao, em) VALUES (9999, 'checkin', 'x')")


def test_excluir_a_reserva_leva_os_dados_pessoais_dos_hospedes(app):
    rid = nova(app)["id"]
    put(app, rid, {"titular": {"documento": CPF}, "acompanhantes": [{"nome": "A Um", "documento": "MG1234567"}]})
    assert sql(app, "SELECT COUNT(*) FROM hospedagem_hospede")[0][0] == 2
    r = cli(app, "admin").post("/api/reservas/%d/excluir-definitivo" % rid, json={"versao": detalhe(app, rid)["versao"]})
    assert r.status_code == 200 and sql(app, "SELECT COUNT(*) FROM hospedagem_hospede")[0][0] == 0


def test_cancelada_nao_aceita_alteracao_de_hospedes(app):
    rid = nova(app)["id"]
    cli(app, "admin").delete("/api/reservas/%d" % rid, json={"versao": detalhe(app, rid)["versao"], "motivo": "teste de cancelamento"})
    assert put(app, rid, {"titular": {}, "acompanhantes": []}).status_code == 409
