"""E2E (Edge): aparência da Operação do dia em claro/escuro, desktop e celular (390 px), impressão e cabeçalho em uma linha.

Gera screenshots em POUSADA_E2E_SHOTS (se definida). Porta 5067.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, erros_graves  # noqa: E402

TEMAS = ("light", "dark")


def sem_rolagem_horizontal(p):
    return p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")


@pytest.mark.parametrize("esquema", TEMAS)
def test_desktop_mapa_lista_e_dialogos(navegador, servidor, esquema):
    t = Tela(navegador, "admin", 1400, 1000, esquema)
    p = t.page
    try:
        p.click("#mrResumo .cd-cat-ins")
        p.wait_for_selector("#mrLista:not(.oculto)")
        t.foto("desktop_%s_mapa_checkins" % esquema)
        p.click("#mrResumo .cd-cat-vagos")
        t.foto("desktop_%s_mapa_vagos" % esquema)
        p.click("#mrResumo .cd-cat-ocupados")
        p.click('#mrTabela [data-acao="info"] >> nth=0')
        p.wait_for_selector("#dlgInfo[open]")
        t.foto("desktop_%s_dialogo_info" % esquema)
        p.keyboard.press("Escape")
        p.click('#mrTabela [data-un="201"][data-acao="obs"]')
        p.wait_for_selector("#dlgNotas[open]")
        t.foto("desktop_%s_dialogo_notas" % esquema)
        p.keyboard.press("Escape")
        p.click('nav button[data-aba="calendario"]')
        p.click("#cdResumo .cd-cat-outs")
        t.foto("desktop_%s_calendario_checkouts" % esquema)
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()


@pytest.mark.parametrize("esquema", TEMAS)
def test_celular_390_cartoes_empilhados_sem_rolagem_horizontal(navegador, servidor, esquema):
    t = Tela(navegador, "admin", 390, 844, esquema)
    p = t.page
    try:
        p.click("#mrResumo .cd-cat-ocupados")
        p.wait_for_selector("#mrLista:not(.oculto)")
        assert sem_rolagem_horizontal(p)
        t.foto("celular_%s_mapa_ocupados" % esquema)
        caixa = p.locator("#mrTabela button.od-acao").first.bounding_box()
        assert caixa["height"] >= 44 and caixa["width"] >= 44
        assert p.locator("#mrTabela .od-rot-curto").first.is_visible()              # rótulo curto ("Dados", "Notas") no celular
        p.click('#mrTabela [data-acao="info"] >> nth=0')
        p.wait_for_selector("#dlgInfo[open]")
        assert sem_rolagem_horizontal(p)
        caixa = p.locator("#dlgInfo").bounding_box()
        assert caixa["width"] >= 388                                                # diálogo ocupa a largura toda
        t.foto("celular_%s_dialogo_info" % esquema)
        p.keyboard.press("Escape")
        p.click("#mrResumo .cd-cat-vagos")
        t.foto("celular_%s_mapa_vagos" % esquema)
        assert sem_rolagem_horizontal(p) and erros_graves(t.erros) == []
    finally:
        t.fechar()


@pytest.mark.parametrize("largura", (1366, 1920))
def test_cabecalho_do_administrador_em_uma_linha(navegador, servidor, largura):
    t = Tela(navegador, "admin", largura, 900)
    try:
        altura = t.page.evaluate("() => document.querySelector('header').getBoundingClientRect().height")
        assert altura < 80, altura                                                  # uma linha (duas linhas passariam de 90 px)
        t.foto("cabecalho_%d" % largura)
    finally:
        t.fechar()


def test_impressao_do_painel_do_mapa_so_tem_cabecalho_e_tabela(navegador, servidor):
    t = Tela(navegador, "admin")
    p = t.page
    try:
        p.click("#mrResumo .cd-cat-ocupados")
        p.evaluate("() => document.body.classList.add('imp-lista-mapa')")
        p.emulate_media(media="print")
        assert p.locator("#mrLista").is_visible() and p.locator("#mrResumo").is_hidden() and p.locator("#mapa").is_hidden()
        assert p.locator("#mrBusca").is_hidden() and p.locator("#mrTabela .od-col-acoes").first.is_hidden()
        assert p.locator("#mrListaTit").is_visible()
        p.evaluate("() => document.body.classList.remove('imp-lista-mapa')")
        p.emulate_media(media="print")
        assert p.locator("#mrLista").is_hidden()                                    # as demais impressões não herdam o painel
    finally:
        t.fechar()
