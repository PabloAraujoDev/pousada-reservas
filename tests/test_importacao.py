"""Testes da importação de planilha e da folha das camareiras.

Todas as planilhas aqui são FICTÍCIAS, geradas por código (nada de dados reais).
"""
import io
import os
import shutil
import sys
from datetime import date

import openpyxl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import criar_app_teste  # noqa: E402
from pousada.db import conectar, iniciar_banco  # noqa: E402
from pousada.importador import (calcular_periodo, extrair_grupo, interpretar_pagamento,  # noqa: E402
                                normalizar_apto, sugerir_apto)

HOJE = date(2026, 10, 1)


@pytest.fixture
def app(tmp_path):
    a = criar_app_teste(tmp_path)
    a.config["HOJE"] = HOJE
    return a


# ---------------------------------------------------------------- ajudantes

def xlsx(abas):
    """abas: {titulo_da_aba: [linhas (A..E)]}. Gera a planilha fictícia em bytes."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, linhas in abas.items():
        ws = wb.create_sheet(titulo)
        mes_ano = titulo.replace("BOA ESPERANÇA ", "")
        ws.cell(2, 1, "HOSPEDAGEM BOA ESPERANÇA - %s 2026" % mes_ano)
        for c, t in enumerate(["APTO", "HOSPEDE", "Nº PESSOAS", "PERÍODO", "FORMA PGTO/CONTATO"], start=1):
            ws.cell(3, c, t)
        for k, lin in enumerate(linhas, start=4):
            if lin is None:
                continue
            for c, v in enumerate(lin, start=1):
                if v is not None:
                    ws.cell(k, c, v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def previa(cli, planilha, **form):
    dados = {"arquivo": (io.BytesIO(xlsx(planilha)), "teste.xlsx")}
    dados.update(form)
    return cli.post("/api/importar/previa", data=dados, content_type="multipart/form-data")


def corpo_confirmar(j, so_status=("ok", "aviso")):
    linhas = [{"aba": l["aba"], "linha": l["linha"], "a": l["apto"], "nome": l["hospede"],
               "extras": "\n".join(l["extras"]), "n": l["n"], "i": l["entrada"], "f": l["saida"],
               "p": l["pagamento"], "o": l["texto_pagamento"], "grupo": l["grupo"]}
              for l in j["linhas"] if l["status"] in so_status]
    return {"arquivo": "teste.xlsx", "linhas": linhas, "pedidos": j["pedidos"]}


OUT = "BOA ESPERANÇA OUTUBRO"
NOV = "BOA ESPERANÇA NOVEMBRO"
DEZ = "BOA ESPERANÇA DEZEMBRO"
JAN = "BOA ESPERANÇA JANEIRO"


def planilha_limpa():
    return {OUT: [
        (201, "Ana Teste", 2, "10/10 A 12/10", "PAGO - tel 11 90000-0000"),
        None,
        (202, "Bruno Teste", 3, "11/10 a 14/10", "VAI PAGAR NA POUSADA"),
        None,
        ("CHALE A", "Carla Teste", 4, "13/11 A16/11", "PAGO 30% R$ 100"),
    ]}


# ---------------------------------------------------------------- importação

def test_importar_planilha_limpa(cli):
    r = previa(cli, planilha_limpa(), abas=[OUT])
    assert r.status_code == 200
    j = r.get_json()
    assert j["contadores"]["prontas"] == 3 and j["contadores"]["erros"] == 0
    assert cli.get("/api/reservas").get_json() == []          # prévia não grava nada
    c = cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    assert c.status_code == 201 and c.get_json()["criadas"] == 3
    res = cli.get("/api/reservas").get_json()
    assert len(res) == 3 and all(x["lote_id"] == c.get_json()["lote_id"] for x in res)


def test_reimportar_cria_zero(cli):
    j = previa(cli, planilha_limpa(), abas=[OUT]).get_json()
    assert cli.post("/api/importar/confirmar", json=corpo_confirmar(j)).get_json()["criadas"] == 3
    j2 = previa(cli, planilha_limpa(), abas=[OUT]).get_json()
    assert j2["contadores"]["prontas"] == 0 and j2["contadores"]["ignoradas"] == 3
    assert {l["categoria"] for l in j2["linhas"]} == {"ja_importada"}
    # mesmo forçando o envio das linhas, nada é criado nem sobrescrito
    c = cli.post("/api/importar/confirmar", json=corpo_confirmar(j, so_status=("ok", "aviso", "ignorada")))
    assert c.status_code == 201 and c.get_json()["criadas"] == 0 and c.get_json()["ignoradas"] == 3
    assert len(cli.get("/api/reservas").get_json()) == 3


def test_virada_de_mes_fundida(cli):
    abas = {OUT: [(201, "Dani Teste", 2, "30/10 A 02/11", "")],
            NOV: [(201, "DANI  TESTE", 2, "30/10 A 02/11", "")]}
    j = previa(cli, abas, abas=[OUT, NOV]).get_json()
    assert sorted(l["status"] for l in j["linhas"]) == ["ignorada", "ok"]
    assert [l["categoria"] for l in j["linhas"] if l["status"] == "ignorada"] == ["repetida"]
    assert cli.post("/api/importar/confirmar", json=corpo_confirmar(j)).get_json()["criadas"] == 1


def test_data_invalida_e_apto_inexistente_nao_bloqueiam(cli):
    abas = {NOV: [(201, "Ok Um", 2, "05/11 A 07/11", ""),
                  None,
                  (202, "Data Ruim", 2, "31/11 A 03/12", ""),
                  None,
                  (309, "Apto Ruim", 2, "05/11 A 07/11", ""),
                  None,
                  (203, "Ok Dois", 2, "05/11 A 07/11", "")]}
    j = previa(cli, abas, abas=[NOV]).get_json()
    por_nome = {l["hospede"]: l for l in j["linhas"]}
    assert por_nome["Data Ruim"]["status"] == "erro" and por_nome["Data Ruim"]["categoria"] == "data_invalida"
    assert "31/11" in por_nome["Data Ruim"]["motivo"]
    assert por_nome["Apto Ruim"]["categoria"] == "apto_inexistente"
    assert por_nome["Apto Ruim"]["sugestao"] == "308"
    assert j["contadores"]["prontas"] + j["contadores"]["avisos"] == 2 and j["contadores"]["erros"] == 2
    assert cli.post("/api/importar/confirmar", json=corpo_confirmar(j)).get_json()["criadas"] == 2


def test_acompanhantes_viram_extras_e_n(cli):
    abas = {OUT: [(201, "Titular Teste", None, "10/10 A 12/10", ""),
                  (None, "Filho Teste (12 ANOS)"),
                  (None, "Esposa Teste"),
                  None,
                  (202, "Outro Teste", 5, "10/10 A 12/10", ""),
                  (None, "Acomp Teste")]}
    j = previa(cli, abas, abas=[OUT]).get_json()
    a, b = j["linhas"]
    assert a["extras"] == ["Filho Teste (12 ANOS)", "Esposa Teste"]
    assert a["n"] == 3 and a["n_estimado"] and a["status"] == "aviso"
    assert b["n"] == 5 and b["extras"] == ["Acomp Teste"] and b["status"] == "ok"
    cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    r = [x for x in cli.get("/api/reservas").get_json() if x["a"] == "201"][0]
    assert r["extras"] == "Filho Teste (12 ANOS)\nEsposa Teste" and r["n"] == 3


def test_conflito_planilha_x_banco_e_dentro_da_planilha(cli):
    cli.post("/api/reservas", json={"a": "201", "nome": "Ja Existe", "n": 2, "i": "2026-10-10", "f": "2026-10-13"})
    abas = {OUT: [(201, "Choca Banco", 2, "11/10 A 14/10", ""),
                  None,
                  (202, "Primeiro Teste", 2, "20/10 A 24/10", ""),
                  None,
                  (202, "Segundo Teste", 2, "22/10 A 26/10", ""),
                  None,
                  (201, "Sai e Entra", 2, "13/10 A 15/10", "")]}
    j = previa(cli, abas, abas=[OUT]).get_json()
    por = {l["hospede"]: l for l in j["linhas"]}
    assert por["Choca Banco"]["status"] == "erro" and por["Choca Banco"]["conflitos"][0]["origem"] == "banco"
    assert "Ja Existe" in por["Choca Banco"]["motivo"]
    assert por["Primeiro Teste"]["status"] == "ok"
    seg = por["Segundo Teste"]
    assert seg["status"] == "erro" and seg["conflitos"][0]["origem"] == "planilha"
    assert seg["conflitos"][0]["linha"] == por["Primeiro Teste"]["linha"]
    assert por["Sai e Entra"]["status"] == "ok"       # sair e entrar no mesmo dia é permitido


def test_confirmar_revalida_conflito_tudo_ou_nada(cli, app):
    j = previa(cli, planilha_limpa(), abas=[OUT]).get_json()
    # depois da prévia, alguém cadastra uma reserva que conflita com a segunda linha
    cli.post("/api/reservas", json={"a": "202", "nome": "Chegou Antes", "n": 1, "i": "2026-10-12", "f": "2026-10-13"})
    c = cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    assert c.status_code == 409 and c.get_json()["problemas"]
    assert len(cli.get("/api/reservas").get_json()) == 1      # nada da planilha foi gravado
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert con.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0] == 0
    finally:
        con.close()


def test_confirmar_conflito_dentro_do_proprio_envio(cli):
    base = {"nome": "Teste", "n": 1, "p": "pendente", "o": "", "extras": "", "grupo": ""}
    linhas = [dict(base, a="201", i="2026-10-10", f="2026-10-12", nome="Um"),
              dict(base, a="201", i="2026-10-11", f="2026-10-13", nome="Dois")]
    c = cli.post("/api/importar/confirmar", json={"linhas": linhas, "pedidos": []})
    assert c.status_code == 409
    assert cli.get("/api/reservas").get_json() == []


def test_periodos_variados():
    assert calcular_periodo("13/11 A16/11", 2026, 11)[:2] == ("2026-11-13", "2026-11-16")
    assert calcular_periodo("  13/11   a   16/11 ", 2026, 11)[:2] == ("2026-11-13", "2026-11-16")
    assert calcular_periodo("13/11 - 16/11", 2026, 11)[:2] == ("2026-11-13", "2026-11-16")
    assert calcular_periodo("28/12 A 03/01", 2026, 12)[:2] == ("2026-12-28", "2027-01-03")   # virada de ano
    assert calcular_periodo("30/12 A 02/01", 2027, 1)[:2] == ("2026-12-30", "2027-01-02")    # aba de janeiro
    e, s, av = calcular_periodo("10A12/05", 2026, 5)
    assert (e, s) == ("2026-05-10", "2026-05-12") and av
    from pousada.importador import ErroLinha
    with pytest.raises(ErroLinha) as ei:
        calcular_periodo("31/11 A 02/12", 2026, 11)
    assert ei.value.categoria == "data_invalida"
    with pytest.raises(ErroLinha) as ei:
        calcular_periodo("05/11 A 05/11", 2026, 11)
    assert ei.value.categoria == "saida_invalida"


def test_chale_normalizado_e_104_ignorado(cli):
    assert normalizar_apto("CHALE A") == "Chalé A" and normalizar_apto("Chalé b") == "Chalé B"
    assert normalizar_apto(101) == "101" and normalizar_apto("APTO 305") == "305"
    assert normalizar_apto("999") is None and sugerir_apto("CHALE F") in ("Chalé E", None, "Chalé A", "Chalé B", "Chalé C", "Chalé D")
    abas = {OUT: [(104, "OCUPADO", None, None, ""), None,
                  ("CHALE C", "Eva Teste", 2, "10/10 A 12/10", "")]}
    j = previa(cli, abas, abas=[OUT]).get_json()
    assert [l["categoria"] for l in j["linhas"] if l["status"] == "ignorada"] == ["ocupado"]
    assert [l["apto"] for l in j["linhas"] if l["status"] != "ignorada"] == ["Chalé C"]


def test_pagamento_interpretado():
    casos = {"GRATUIDADE": "gratis", "cortesia da casa": "gratis", "GRÁTIS": "gratis",
             "PAGO 30% R$ 200": "parcial", "sinal de 100": "parcial", "PARCIAL": "parcial",
             "PAGO - 11/09": "pago", "VAI PAGAR NA POUSADA": "pousada", "acerta na chegada": "pousada",
             "tel 11 99999-0000": "pendente", "": "pendente", "PAGO 100%": "pago"}
    for texto, esperado in casos.items():
        assert interpretar_pagamento(texto) == esperado, texto
    # prioridade: gratuidade vence tudo
    assert interpretar_pagamento("GRATUIDADE - PAGO 30%") == "gratis"


def test_grupo_e_texto_original_nas_observacoes(cli):
    assert extrair_grupo("TURMA ALFA", "") == "TURMA ALFA"
    assert extrair_grupo("Fulano", "TURMA BETA - 30% pago") == "TURMA BETA"
    assert extrair_grupo("Fulano", "PAGO") == ""
    abas = {OUT: [(201, "TURMA ALFA", 4, "10/10 A 12/10", "PAGO - 11/09"), None,
                  (202, "Gil Teste", 2, "10/10 A 12/10", "TURMA BETA - 30% R$ 50")]}
    j = previa(cli, abas, abas=[OUT]).get_json()
    assert [l["grupo"] for l in j["linhas"]] == ["TURMA ALFA", "TURMA BETA"]
    cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    res = {r["a"]: r for r in cli.get("/api/reservas").get_json()}
    assert res["201"]["grupo"] == "TURMA ALFA" and res["202"]["o"] == "TURMA BETA - 30% R$ 50" and res["202"]["p"] == "parcial"


def test_reserva_encerrada_ignorada_por_padrao(cli, app):
    app.config["HOJE"] = date(2026, 10, 27)
    abas = {OUT: [(201, "Passada Teste", 2, "10/10 A 12/10", ""), None, (202, "Futura Teste", 2, "28/10 A 30/10", "")]}
    j = previa(cli, abas, abas=[OUT]).get_json()
    assert {l["hospede"]: l["categoria"] for l in j["linhas"]} == {"Passada Teste": "encerrada", "Futura Teste": ""}
    j2 = previa(cli, abas, abas=[OUT], incluir_passadas="1").get_json()
    assert j2["contadores"]["prontas"] == 2


def test_abas_padrao_so_out_nov_dez(cli):
    abas = {"BOA ESPERANÇA SETEMBRO": [(201, "Set Teste", 2, "10/09 A 12/09", "")],
            OUT: [(201, "Out Teste", 2, "10/10 A 12/10", "")],
            DEZ: [(201, "Dez Teste", 2, "10/12 A 12/12", "")]}
    j = previa(cli, abas).get_json()
    assert [(a["titulo"].split()[-1], a["selecionada"]) for a in j["abas"]] == [("SETEMBRO", False), ("OUTUBRO", True), ("DEZEMBRO", True)]
    assert sorted(l["hospede"] for l in j["linhas"]) == ["Dez Teste", "Out Teste"]
    j = previa(cli, abas, abas=["BOA ESPERANÇA SETEMBRO"]).get_json()
    assert [l["hospede"] for l in j["linhas"]] == ["Set Teste"]


def test_secoes_lista_de_espera_e_cancelamentos(cli):
    abas = {NOV: [(201, "Real Teste", 2, "05/11 A 07/11", ""),
                  None,
                  (None, "LISTA DE ESPERA"),
                  (None, "Espera Um - 03 PESSOAS - 03 A 06/12 - (11) 98888-1111"),
                  (None, "Espera Dois - 15/12 A 18/12/2026 - sem telefone"),
                  (None, "texto qualquer sem data"),
                  None,
                  (None, "CANCELAMENTOS"),
                  (202, "Cancelada Teste", 2, "05/11 A 07/11", "")]}
    j = previa(cli, abas, abas=[NOV]).get_json()
    assert [l["hospede"] for l in j["linhas"]] == ["Real Teste"]       # nada depois dos títulos é reserva
    assert j["contadores"]["lista_espera"] == 3 and j["contadores"]["cancelamentos"] == 1
    p = {x["nome"]: x for x in j["pedidos"]}
    assert p["Espera Um"]["pessoas"] == 3 and (p["Espera Um"]["entrada"], p["Espera Um"]["saida"]) == ("2026-12-03", "2026-12-06")
    assert "98888" in p["Espera Um"]["contato"]
    assert p["Espera Dois"]["entrada"] == "2026-12-15"
    assert p["texto qualquer sem data"]["entrada"] is None
    c = cli.post("/api/importar/confirmar", json=corpo_confirmar(j))
    assert c.get_json()["pedidos_criados"] == 3
    assert len(cli.get("/api/pedidos").get_json()) == 3
    # reimportar não duplica os pedidos
    j2 = previa(cli, abas, abas=[NOV]).get_json()
    assert j2["contadores"]["lista_espera"] == 0
    assert cli.post("/api/importar/confirmar", json=corpo_confirmar(j2)).get_json()["pedidos_criados"] == 0


def test_desfazer_remove_so_o_lote(cli):
    manual = cli.post("/api/reservas", json={"a": "301", "nome": "Manual", "n": 1, "i": "2026-10-10", "f": "2026-10-11"}).get_json()
    j = previa(cli, planilha_limpa(), abas=[OUT]).get_json()
    lote1 = cli.post("/api/importar/confirmar", json=corpo_confirmar(j)).get_json()["lote_id"]
    outro = {OUT: [(203, "Outro Lote", 2, "20/10 A 22/10", "")]}
    lote2 = cli.post("/api/importar/confirmar", json=corpo_confirmar(previa(cli, outro, abas=[OUT]).get_json())).get_json()["lote_id"]
    assert len(cli.get("/api/reservas").get_json()) == 5
    r = cli.post("/api/importar/desfazer/%d" % lote1)
    assert r.status_code == 200 and r.get_json()["removidas"] == 3
    restantes = {x["nome"] for x in cli.get("/api/reservas").get_json()}
    assert restantes == {"Manual", "Outro Lote"} and manual["id"]
    assert cli.post("/api/importar/desfazer/9999").status_code == 404
    assert lote2 != lote1


def test_upload_invalido(cli):
    r = cli.post("/api/importar/previa", data={"arquivo": (io.BytesIO(b"abc"), "x.txt")}, content_type="multipart/form-data")
    assert r.status_code == 400
    r = cli.post("/api/importar/previa", data={"arquivo": (io.BytesIO(b"nao e zip"), "x.xlsx")}, content_type="multipart/form-data")
    assert r.status_code == 400 and "xlsx" in r.get_json()["erro"]
    r = cli.post("/api/importar/previa", data={"arquivo": (io.BytesIO(b"0" * (5 * 1024 * 1024 + 10)), "x.xlsx")},
                 content_type="multipart/form-data")
    assert r.status_code == 413
    assert cli.post("/api/importar/previa", data={}, content_type="multipart/form-data").status_code == 400


def test_migracao_002_preserva_dados(tmp_path):
    pasta = tmp_path / "mig"
    pasta.mkdir()
    origem = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
    shutil.copy(os.path.join(origem, "001_inicial.sql"), pasta)
    banco = str(tmp_path / "velho.db")
    iniciar_banco(banco, str(pasta))
    con = conectar(banco)
    con.execute("INSERT INTO reservas (a,nome,i,f,criado,alterado) VALUES ('201','Antigo','2026-10-10','2026-10-12','x','x')")
    con.close()
    iniciar_banco(banco, origem)
    con = conectar(banco)
    try:
        r = con.execute("SELECT nome, grupo, lote_id, chave_import FROM reservas").fetchone()
        assert tuple(r) == ("Antigo", "", None, None)
        assert con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 0
    finally:
        con.close()


# ---------------------------------------------------------------- camareiras

def _reserva(cli, a, nome, i, f, **extra):
    d = {"a": a, "nome": nome, "n": 2, "i": i, "f": f, "p": "pago",
         "o": "PAGO 30% R$ 500,00 - (11) 98888-7777 - chega tarde - pagou no pix"}
    d.update(extra)
    assert cli.post("/api/reservas", json=d).status_code == 201


def test_camareiras_sem_valores_nem_telefone_e_destaque(cli):
    _reserva(cli, "205", "Sai Segredo", "2026-10-10", "2026-10-12")
    _reserva(cli, "205", "Entra Segredo", "2026-10-12", "2026-10-15")
    _reserva(cli, "101", "Só Entra", "2026-10-12", "2026-10-13")
    _reserva(cli, "102", "Fica Segredo", "2026-10-10", "2026-10-20")
    r = cli.get("/api/camareiras?inicio=2026-10-12&fim=2026-10-12")
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    for proibido in ("500", "98888", "pago", "pix", "Segredo", "30%", "R$", '"p"'):
        assert proibido not in texto, proibido
    dia = r.get_json()["dias"][0]
    assert [u["a"] for u in dia["unidades"]] == ["205", "101"]      # saída+entrada primeiro
    assert dia["unidades"][0]["saida_e_entrada"] is True and dia["unidades"][1]["saida_e_entrada"] is False
    assert dia["unidades"][0]["saida"]["n"] == 2 and "chega tarde" in dia["unidades"][0]["saida"]["obs"]
    assert not any(u["estadia"] for u in dia["unidades"])           # estadias só se pedidas
    # estadias e nomes só quando solicitados
    r2 = cli.get("/api/camareiras?inicio=2026-10-12&fim=2026-10-12&estadias=1&nomes=1").get_json()["dias"][0]
    assert [u["a"] for u in r2["unidades"]] == ["205", "101", "102"]
    assert r2["unidades"][2]["estadia"]["nome"] == "Fica Segredo"
    bruto = str(r2)
    assert "98888" not in bruto and "500" not in bruto


def test_camareiras_periodo_invalido_e_padrao(cli):
    assert cli.get("/api/camareiras?inicio=2026-10-12&fim=2026-10-10").status_code == 400
    assert cli.get("/api/camareiras?inicio=2026-13-01&fim=2026-10-10").status_code == 400
    assert cli.get("/api/camareiras?inicio=2026-01-01&fim=2026-12-31").status_code == 400
    j = cli.get("/api/camareiras").get_json()                         # padrão: hoje até hoje+6
    assert (j["inicio"], j["fim"]) == ("2026-10-01", "2026-10-07") and len(j["dias"]) == 7
