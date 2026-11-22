"""E2E da importação com cancelamentos e atualizações: prévia -> marcar -> confirmar -> desfazer (Edge, banco temporário)."""
import io
from datetime import timedelta

import openpyxl

from tests.e2e.base_operacao import HOJE, Tela, navegador, preferencias_zeradas, servidor  # noqa: F401

MESES = ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
D0 = HOJE + timedelta(days=45)
TITULO = "BOA ESPERANÇA " + MESES[D0.month - 1]


def periodo(ini, fim):
    a, b = D0 + timedelta(days=ini), D0 + timedelta(days=fim)
    return "%02d/%02d A %02d/%02d" % (a.day, a.month, b.day, b.month)


def planilha(grade, cancelamentos=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = TITULO
    ws.cell(2, 1, "HOSPEDAGEM BOA ESPERANÇA - %s %d" % (MESES[D0.month - 1], D0.year))
    for c, t in enumerate(["APTO", "NOME", "Nº PESSOAS", "PERÍODO", "FORMA PGTO"], start=1):
        ws.cell(3, c, t)
    linha = 4
    for lin in grade:
        for c, v in enumerate(lin, start=1):
            ws.cell(linha, c, v)
        linha += 2
    ws.cell(linha, 2, "CANCELAMENTOS")
    for lin in cancelamentos:
        linha += 1
        for c, v in enumerate(lin, start=1):
            ws.cell(linha, c, v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def enviar(page, dados):
    if not page.is_visible("#dlgImp"):
        page.evaluate("() => document.getElementById('dlgImp').showModal()")
    with page.expect_response("**/api/importar/previa"):
        page.set_input_files("#impArq", files=[{"name": "t.xlsx", "mimeType": "application/octet-stream", "buffer": dados}])
    page.wait_for_timeout(300)
    if not page.is_checked(".impAba"):
        page.check(".impAba")
        with page.expect_response("**/api/importar/previa"):
            page.click("#impPrevia")
        page.wait_for_timeout(300)


def test_importar_cancelar_e_desfazer_pela_tela(navegador, servidor):
    from pousada.db import conectar
    t = Tela(navegador, "admin")
    p = t.page
    enviar(p, planilha([(301, "Ana Teste", 2, periodo(0, 2), ""), (302, "Bruno Teste", 3, periodo(5, 7), ""), (303, "Carla Teste", 4, periodo(10, 12), "")]))
    p.click("#impGravar")
    p.wait_for_function("() => document.getElementById('impMsg').textContent.indexOf('3 reserva(s) importada(s)') >= 0", timeout=15000)
    p.click("#impFechar")
    enviar(p, planilha([(301, "Novo Hospede", 2, periodo(0, 2), ""), (302, "BRUNO TESTE", 6, periodo(5, 7), "")],
                       [("301", "ANA TESTE - " + periodo(0, 2) + " - CANCELOU"), ("304", '<img src=x onerror="window.__xss=1"> - ' + periodo(0, 2)),
                        (None, "linha solta sem unidade")]))
    assert p.inner_text("#impConts").count("Atualizações") == 1
    assert p.locator("#impCancTab tbody tr").count() == 2                       # Ana (alta) e Carla (sumiu)
    assert p.locator("#impCancTab .impCancChk:checked").count() == 2
    assert "Nenhuma" not in p.inner_text("#impCanc") and "linha solta sem unidade" in p.inner_text("#impCanc")
    assert p.evaluate("() => window.__xss") is None
    novo = p.locator("#impTab tr", has_text="Novo Hospede").locator(".impInc")
    assert novo.is_checked() and novo.is_enabled()
    p.locator("#impCancTab .impCancChk").first.uncheck()                         # sem cancelar Ana, a nova não entra
    novo = p.locator("#impTab tr", has_text="Novo Hospede").locator(".impInc")
    assert not novo.is_checked() and novo.is_disabled()
    p.locator("#impCancTab .impCancChk").first.check()
    assert p.locator("#impTab tr", has_text="Novo Hospede").locator(".impInc").is_checked()
    assert "atualizar 1" in p.inner_text("#impGravar") and "cancelar 2" in p.inner_text("#impGravar")
    t.foto("importacao_cancelamentos")
    p.click("#impGravar")
    p.wait_for_function("() => document.getElementById('impMsg').textContent.indexOf('2 cancelada(s)') >= 0", timeout=15000)
    con = conectar(servidor["POUSADA_DB"])
    estado = {r[0]: (r[1], r[2]) for r in con.execute("SELECT nome, status, n FROM reservas WHERE a IN ('301','302','303')")}
    assert estado["Ana Teste"][0] == "cancelada" and estado["Carla Teste"][0] == "cancelada"
    assert estado["Novo Hospede"][0] == "ativa" and estado["Bruno Teste"] == ("ativa", 6)
    p.click("#impDesfazer")
    with p.expect_response("**/api/importar/desfazer/*") as resp:
        p.click("#impDesfazer")
    assert resp.value.json()["revertidas"] == 3
    estado = {r[0]: (r[1], r[2]) for r in con.execute("SELECT nome, status, n FROM reservas WHERE a IN ('301','302','303')")}
    con.close()
    assert estado["Ana Teste"][0] == "ativa" and estado["Carla Teste"][0] == "ativa" and estado["Bruno Teste"] == ("ativa", 3)
    assert "Novo Hospede" not in estado
    assert not [e for e in t.erros if "pageerror" in e]
    t.ctx.close()
