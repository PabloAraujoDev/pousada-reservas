"""Folha da semana em PDF: conteúdo (totais), segurança do texto, permissões e erros."""
from datetime import date

from pousada.db import conectar
from pousada.folha_pdf import montar_semana
from tests.conftest import cliente_como

SEGUNDA = date(2026, 10, 5)     # uma segunda-feira


def _reserva(a, i, f, n=2, nome="Hóspede Teste", **extra):
    return dict({"a": a, "nome": nome, "extras": "", "n": n, "i": i, "f": f, "p": "pendente", "o": "", "grupo": ""}, **extra)


def _semana(app):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        return montar_semana(con, SEGUNDA)
    finally:
        con.close()


def test_pdf_baixa_como_arquivo(cli):
    cli.post("/api/reservas", json=_reserva("201", "2026-10-06", "2026-10-08"))
    r = cli.get("/api/folha.pdf?inicio=2026-10-05")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF")
    assert "attachment" in r.headers["Content-Disposition"]
    assert "folha_2026-10-05.pdf" in r.headers["Content-Disposition"]


def test_totais_seguem_as_regras_do_mapa(app, cli):
    # 2 pessoas de 06/10 a 08/10: café em 07 e 08; na noite em 06 e 07; entrada dia 06; saída dia 08.
    cli.post("/api/reservas", json=_reserva("201", "2026-10-06", "2026-10-08", n=2))
    sem = {d["data"].day: d for d in _semana(app)}
    assert [sem[x]["cafe"] for x in (5, 6, 7, 8, 9)] == [0, 0, 2, 2, 0]
    assert [sem[x]["noite"] for x in (5, 6, 7, 8, 9)] == [0, 2, 2, 0, 0]
    assert len(sem[6]["entradas"]) == 1 and len(sem[8]["saidas"]) == 1
    assert sem[5]["livres"] == 24            # 25 unidades menos o 104, que não aceita reserva
    assert sem[6]["livres"] == 23


def test_sai_e_entra_no_mesmo_dia(app, cli):
    cli.post("/api/reservas", json=_reserva("201", "2026-10-05", "2026-10-07"))
    cli.post("/api/reservas", json=_reserva("201", "2026-10-07", "2026-10-09", nome="Outro"))
    dia7 = {d["data"].day: d for d in _semana(app)}[7]
    assert len(dia7["saidas"]) == 1 and len(dia7["entradas"]) == 1
    assert dia7["livres"] == 23              # só a reserva que entra ocupa a noite do dia 7


def test_reserva_cancelada_nao_entra(app, cli):
    r = cli.post("/api/reservas", json=_reserva("202", "2026-10-06", "2026-10-08")).get_json()
    cli.delete("/api/reservas/%d" % r["id"], json={"versao": r["versao"], "motivo": "teste"})
    assert all(not d["entradas"] and d["cafe"] == 0 for d in _semana(app))


def test_texto_com_marcacao_nao_quebra_o_pdf(cli):
    cli.post("/api/reservas", json=_reserva("203", "2026-10-06", "2026-10-08", nome='A <b>&</b> </para><font size="99"> "x"'))
    r = cli.get("/api/folha.pdf?inicio=2026-10-05")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_semana_muito_cheia_gera_pdf(cli):
    unidades = ["101", "102", "103"] + [str(x) for x in range(201, 209)] + [str(x) for x in range(301, 309)]
    for k, u in enumerate(unidades):
        assert cli.post("/api/reservas", json=_reserva(u, "2026-10-06", "2026-10-09", nome="Hóspede %d" % k)).status_code == 201
    r = cli.get("/api/folha.pdf?inicio=2026-10-05")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_semana_vazia_gera_pdf(cli):
    r = cli.get("/api/folha.pdf?inicio=2030-01-07")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_data_invalida_ou_ausente_da_400(cli):
    for url in ("/api/folha.pdf", "/api/folha.pdf?inicio=", "/api/folha.pdf?inicio=2026-31-11",
                "/api/folha.pdf?inicio=2026-11-31", "/api/folha.pdf?inicio=1999-01-04", "/api/folha.pdf?inicio=lixo"):
        r = cli.get(url)
        assert r.status_code == 400, url
        assert r.is_json and r.get_json()["erro"]


def _tamanho_da_pagina(pdf):
    """Largura e altura (em pontos) da primeira página, lidas do /MediaBox."""
    import re
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", pdf)
    return float(m.group(1)), float(m.group(2))


def test_orientacao_paisagem_e_padrao(cli):
    for url in ("/api/folha.pdf?inicio=2026-10-05", "/api/folha.pdf?inicio=2026-10-05&orientacao=paisagem"):
        largura, altura = _tamanho_da_pagina(cli.get(url).data)
        assert largura > altura


def test_orientacao_retrato(cli):
    largura, altura = _tamanho_da_pagina(cli.get("/api/folha.pdf?inicio=2026-10-05&orientacao=retrato").data)
    assert altura > largura
    assert abs(largura - 595.3) < 1 and abs(altura - 841.9) < 1      # A4 em pé


def test_retrato_com_semana_cheia_e_nomes_longos(cli):
    unidades = ["101", "102", "103"] + [str(x) for x in range(201, 209)] + [str(x) for x in range(301, 309)]
    for k, u in enumerate(unidades):
        cli.post("/api/reservas", json=_reserva(u, "2026-10-%02d" % (5 + k % 6), "2026-10-%02d" % (7 + k % 6),
                                                nome="Hóspede com um nome bem comprido número %d" % k))
    r = cli.get("/api/folha.pdf?inicio=2026-10-05&orientacao=retrato")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_orientacao_invalida_da_400(cli):
    for valor in ("diagonal", "RETRATO", "paisagem;x", "1"):
        r = cli.get("/api/folha.pdf?inicio=2026-10-05&orientacao=" + valor)
        assert r.status_code == 400, valor
        assert "Orientação" in r.get_json()["erro"]


def test_tela_tem_a_escolha_de_papel_na_folha_e_nas_camareiras(cli):
    html = cli.get("/").get_data(as_text=True)
    assert html.count('class="sel-orientacao"') == 2
    assert 'value="retrato"' in html


def test_exige_login(app):
    assert app.test_client().get("/api/folha.pdf?inicio=2026-10-05").status_code == 401


def test_camareira_nao_baixa_a_folha_com_nomes(app):
    assert cliente_como(app, "camareira").get("/api/folha.pdf?inicio=2026-10-05").status_code == 403


def test_resposta_nao_fica_em_cache(cli):
    assert "no-store" in cli.get("/api/folha.pdf?inicio=2026-10-05").headers["Cache-Control"]
