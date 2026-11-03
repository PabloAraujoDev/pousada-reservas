"""E2E (Edge): etapa 3A por perfil, celular 390 px, tema escuro, contraste, foco visível e a ficha FNRH em A4. Porta 5113."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5113")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import SHOTS, Tela, erros_graves  # noqa: E402
from test_hospedagem_e2e import api  # noqa: E402
from test_resumo_e2e import abrir_pelo_mapa, botoes_do_cartao, como  # noqa: E402

DOC = "123.456.789-09"


def preparar(p):
    """Reserva 6 (José, Chalé A): titular com documento, um acompanhante e placa (como o administrador)."""
    r = api(p, "GET", "/api/reservas/6")["dados"]
    h = api(p, "PUT", "/api/reservas/6/hospedes", {"versao": r["versao"], "titular": {"documento": DOC, "profissao": "Médico"},
                                                  "acompanhantes": [{"nome": "Ana Pereira", "documento": "MG-1234567", "destino": "Ouro Preto"}]})
    assert h["status"] == 200, h
    assert api(p, "PUT", "/api/reservas/6/placa", {"versao": h["dados"]["versao"], "placa": "ABC1234"})["status"] == 200


def test_perfis_veem_a_lista_mascarada_ou_completa_e_nada_a_mais(navegador, servidor):
    t0 = Tela(navegador, "admin")
    try:
        preparar(t0.page)
    finally:
        t0.fechar()
    for login, completo in (("dir", False), ("consulta", False), ("recep", True), ("atend", True)):
        t = como(navegador, login, 6)
        p = t.page
        try:
            p.click('#rcCartao [data-rc="hospedes"]')
            p.wait_for_selector("#rcPainelAcao .rc-hp-linha")
            dom = p.evaluate("() => document.getElementById('dlgResumo').innerHTML + [...document.querySelectorAll('#dlgResumo input')].map(i => i.value).join('|')")
            if completo:
                assert p.locator("#rcPainelAcao input").evaluate_all("els => els.map(e => e.value)").count(DOC) == 1
                assert "ABC-1234" in p.inner_text("#rcCartao") and p.locator("#rcHpAdd").count() == 1
            else:
                for segredo in (DOC, "123.456", "MG-1234", "Médico", "Ouro Preto", "ABC-1234"):
                    assert segredo not in dom, (login, segredo)
                assert "ABC****" in p.inner_text("#rcCartao") and p.locator("#rcHpAdd").count() == 0
                assert p.locator("#rcPainelAcao input[readonly]").count() >= 2
                assert botoes_do_cartao(p) == (["hospedes", "imprimir", "despesas"] if login == "dir" else ["hospedes", "imprimir"])
            assert erros_graves(t.erros) == []
        finally:
            t.fechar()


def test_recepcao_libera_e_reverte_mas_o_motivo_e_obrigatorio(navegador, servidor):
    t = como(navegador, "recep", 2)
    p = t.page
    try:
        assert botoes_do_cartao(p) == ["editar", "hospedes", "liberar", "ficha", "checkin", "imprimir", "despesas"]
        v = api(p, "GET", "/api/reservas/2")["dados"]["versao"]
        assert api(p, "POST", "/api/reservas/2/liberar", {"versao": v})["status"] == 400        # recepção pode, mas o motivo é obrigatório
        assert api(p, "POST", "/api/reservas/2/checkin/reverter", {"versao": v})["status"] == 400
        assert p.locator("#rcBarraItens [data-rc='placa']").count() == 1
    finally:
        t.fechar()


def test_consulta_nao_tem_placa_nem_ficha_nem_tiles(navegador, servidor):
    t = como(navegador, "consulta", 6)
    try:
        p = t.page
        assert p.locator("#rcBarraItens").count() == 0 and p.locator("#rcHospede .rc-az").count() == 0
        assert api(p, "POST", "/api/reservas/6/ficha", {})["status"] == 403
    finally:
        t.fechar()


def luminancia(rgb):
    c = [x / 255 for x in rgb]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contraste(a, b):
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def cores(p, seletor):
    """Cor do texto e do fundo efetivo (o primeiro ancestral com fundo opaco)."""
    return p.evaluate("""(s) => {
        const el = document.querySelector(s); const num = c => (c.match(/[\\d.]+/g) || []).map(Number);
        let bg = el; let fundo = [255, 255, 255];
        while (bg) { const c = num(getComputedStyle(bg).backgroundColor); if (c.length >= 3 && (c.length < 4 || c[3] === 1)) { fundo = c.slice(0, 3); break; } bg = bg.parentElement; }
        return {texto: num(getComputedStyle(el).color).slice(0, 3), fundo: fundo};
    }""", seletor)


@pytest.mark.parametrize("esquema,largura,altura", [("light", 390, 844), ("dark", 390, 844), ("dark", 1400, 1000), ("light", 1400, 1000)])
def test_aparencia_contraste_alvos_e_sem_rolagem_horizontal(navegador, servidor, esquema, largura, altura):
    t = Tela(navegador, "admin", largura, altura, esquema)
    p = t.page
    try:
        preparar(p)
        abrir_pelo_mapa(p, 6)
        p.click('#rcCartao [data-rc="hospedes"]')
        p.wait_for_selector("#rcPainelAcao .rc-hp-linha")
        p.locator("#rcPainelAcao summary").first.click()
        assert p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        box = p.locator("#rcPainelAcao").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= largura
        if SHOTS:
            p.locator("#dlgResumo").screenshot(path=os.path.join(SHOTS, "hosp_%s_%d.png" % (esquema, largura)))
        if largura == 390:
            for b in p.locator("#dlgResumo button:visible, #dlgResumo select:visible, #dlgResumo input:not([type=checkbox]):visible").all():
                c = b.bounding_box()
                if c and b.get_attribute("aria-controls") is None and b.get_attribute("role") != "tab":
                    assert c["height"] >= 43, (b.inner_text()[:20], c)
            for cx in p.locator("#rcHospede input[type=checkbox]:visible").all():
                assert cx.bounding_box()["height"] >= 20           # a linha toda (label) é o alvo de 44 px
        p.keyboard.press("Escape")
        p.check("#rcHospede .rc-az-diaria .rc-az-caixa")
        for seletor in ("#rcTotalSel", ".rc-hp-tit, .rc-apto-nome", ".rc-item-tipo", ".rc-az-nota", ".rc-estado .rc-val", "#rcCartao .rc-rot"):
            if p.locator(seletor).count():
                c = cores(p, seletor)
                assert contraste(c["texto"], c["fundo"]) >= 4.5, (seletor, esquema, c)
        p.focus("#rcCartao [data-rc='editar']")
        p.keyboard.press("Tab")                                         # foco por teclado: contorno visível (3 px) no botão Hóspedes
        assert p.evaluate("() => document.activeElement.dataset.rc") == "hospedes"
        assert p.evaluate("() => getComputedStyle(document.activeElement).outlineStyle") == "solid"
        assert float(p.evaluate("() => getComputedStyle(document.activeElement).outlineWidth").replace("px", "")) >= 2
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()


def test_ficha_fnrh_a4_uma_pagina_com_campos_em_branco_e_so_ela(navegador, servidor):
    t = Tela(navegador, "admin", 1400, 1000)
    p = t.page
    try:
        preparar(p)
        abrir_pelo_mapa(p, 6)
        d = api(p, "POST", "/api/reservas/6/ficha", {})["dados"]
        p.evaluate("(d) => fnrhMontar(document.getElementById('fnrhImpressao'), d)", d)
        p.evaluate("() => document.body.classList.add('imp-fnrh')")
        p.emulate_media(media="print")
        assert p.locator("#fnrhImpressao").is_visible() and p.locator("#mapa").is_hidden() and p.locator("#dlgResumo").is_hidden()
        assert p.locator("#aba-camareiras").is_hidden() and p.locator(".fnrh-bloco").count() == 3        # hospedagem + titular + 1 acompanhante
        texto = p.inner_text("#fnrhImpressao")
        for esperado in ("Pousada Boa Esperança", "Chalé A", "ABC-1234", DOC, "Ana Pereira", "Ouro Preto", "Médico", "Meio de transporte", "Motivo da viagem"):
            assert esperado in texto, esperado
        caminho = os.path.join(SHOTS, "ficha_fnrh.pdf") if SHOTS else None
        pdf = p.pdf(format="A4", print_background=True, path=caminho)
        assert len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 1
        p.evaluate("() => { document.body.classList.remove('imp-fnrh'); document.getElementById('fnrhImpressao').textContent = ''; }")
        p.emulate_media(media="print")
        assert p.locator("#fnrhImpressao").is_hidden()                          # as outras impressões não herdam a ficha
        p.emulate_media(media="screen")
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()
