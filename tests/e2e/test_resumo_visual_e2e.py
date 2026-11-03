"""E2E (Edge): aparência do Resumo da conta em claro/escuro, desktop e celular (390 px). Screenshots em POUSADA_E2E_SHOTS."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import SHOTS, Tela, erros_graves  # noqa: E402
from test_resumo_e2e import RESUMO, abrir_pelo_mapa  # noqa: E402


def sem_rolagem_horizontal(p):
    return p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")


def foto(p, nome):
    if SHOTS:
        p.locator("#dlgResumo").screenshot(path=os.path.join(SHOTS, nome + ".png"))


def lancar(p, rid, descricao, qtd, centavos):
    p.evaluate("([r, d, q, c]) => api('POST', '/api/reservas/' + r + '/despesas', {categoria: 'bar', descricao: d, quantidade: q, valor_unit_centavos: c, chave: 'chave-' + d.replace(/ /g, '')})",
               [rid, descricao, qtd, centavos])


@pytest.mark.parametrize("esquema,largura,altura", [("light", 1400, 1000), ("dark", 1400, 1000), ("light", 390, 844), ("dark", 390, 844)])
def test_resumo_visual(navegador, servidor, esquema, largura, altura):
    t = Tela(navegador, "admin", largura, altura, esquema)
    p = t.page
    try:
        lancar(p, 1, "Agua 500ml", 2, 800)
        p.evaluate("() => carregar()")
        abrir_pelo_mapa(p, 1)
        p.wait_for_selector("#rcTotal strong")
        foto(p, "resumo_%s_%d" % (esquema, largura))
        assert sem_rolagem_horizontal(p) and erros_graves(t.erros) == []
        if largura == 390:
            for b in p.locator("#rcCartao .rc-bt").all():
                c = b.bounding_box()
                assert c["height"] >= 44 and c["width"] >= 44
            assert p.locator("#dlgResumo").bounding_box()["width"] >= 388
            assert p.locator("#rcCartao").bounding_box()["x"] + p.locator("#rcCartao").bounding_box()["width"] <= 390      # nada cortado à direita
            assert p.locator("#rcAbas").bounding_box()["x"] + p.locator("#rcAbas").bounding_box()["width"] <= 390
    finally:
        t.fechar()


def test_ficha_a4_gera_pdf_de_uma_pagina_so_com_o_resumo(navegador, servidor):
    t = Tela(navegador, "admin", 1400, 1000)
    p = t.page
    try:
        abrir_pelo_mapa(p, 1)
        p.evaluate("() => document.body.classList.add('imp-resumo')")
        caminho = os.path.join(SHOTS, "resumo_ficha.pdf") if SHOTS else None
        pdf = p.pdf(format="A4", print_background=True, path=caminho)
        paginas = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
        assert paginas == 1, paginas                                  # a ficha cabe em uma página e não arrasta o mapa junto
        assert len(pdf) > 3000 and erros_graves(t.erros) == []
        p.evaluate("() => document.body.classList.remove('imp-resumo')")
    finally:
        t.fechar()
