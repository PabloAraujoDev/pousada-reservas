"""E2E exploratório (QA hospedagem): celular 390 px, tema escuro, Esc, duplo clique e perda de conexão no Receber. Porta 5131."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5131")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import erros_graves  # noqa: E402
from test_pagamentos_e2e import PAINEL, abrir_painel, api, esperar_toast  # noqa: E402
from test_resumo_e2e import abrir_pelo_mapa  # noqa: E402


def sem_rolagem_lateral(p, seletor="#dlgResumo"):
    return p.evaluate("""(s) => { const e = document.querySelector(s); return [e.scrollWidth, e.clientWidth, document.documentElement.scrollWidth, window.innerWidth]; }""", seletor)


def test_celular_escuro_sem_rolagem_lateral_e_esc_fecha(servidor, navegador):
    t = Tela(navegador, "admin", largura=390, altura=800, esquema="dark")
    p = t.page
    abrir_pelo_mapa(p, 2)
    sw, cw, dw, iw = sem_rolagem_lateral(p)
    assert sw <= cw + 1 and dw <= iw + 1, (sw, cw, dw, iw)
    abrir_painel(p, "receber")
    p.get_by_label("Forma de pagamento").select_option("cartao")
    p.get_by_label("Pagamento no crédito").select_option("parcelado")
    p.get_by_label("Número de parcelas (2 a 12)").fill("12")
    sw, cw, dw, iw = sem_rolagem_lateral(p)
    assert sw <= cw + 1 and dw <= iw + 1, (sw, cw, dw, iw)
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    assert not p.is_visible(PAINEL + " h3")                                   # o 1º Esc fecha só o painel de recebimento
    p.keyboard.press("Escape")
    p.wait_for_timeout(300)
    assert not p.is_visible("#dlgResumo") or not p.evaluate("() => document.getElementById('dlgResumo').open")
    assert erros_graves(t.erros) == []
    t.fechar()


def test_duplo_clique_e_perda_de_conexao_nao_duplicam_pagamento(servidor, navegador):
    t = Tela(navegador, "admin")
    p = t.page
    abrir_pelo_mapa(p, 4)
    antes = len(api(p, "GET", "/api/reservas/4/pagamentos")["dados"]["itens"])
    abrir_painel(p, "receber")
    p.get_by_label("Valor a receber (R$)").fill("10,00")
    p.dblclick(PAINEL + " .primario")
    p.wait_for_timeout(1200)
    depois = len(api(p, "GET", "/api/reservas/4/pagamentos")["dados"]["itens"])
    assert depois == antes + 1, (antes, depois)
    abrir_painel(p, "receber")
    p.get_by_label("Valor a receber (R$)").fill("5,00")
    t.ctx.set_offline(True)
    p.click(PAINEL + " .primario")
    p.wait_for_timeout(1500)
    t.ctx.set_offline(False)
    assert len(api(p, "GET", "/api/reservas/4/pagamentos")["dados"]["itens"]) == depois      # nada gravado offline
    assert p.is_visible(PAINEL)                                                               # o painel continua aberto para tentar de novo
    p.click(PAINEL + " .primario")
    esperar_toast(p, "R$ 5,00")
    assert len(api(p, "GET", "/api/reservas/4/pagamentos")["dados"]["itens"]) == depois + 1
    t.fechar()


def test_textos_longos_nao_estouram_o_celular(servidor, navegador):
    t = Tela(navegador, "admin", largura=390, altura=800)
    p = t.page
    longo = "Wolfeschlegelsteinhausenbergerdorff" * 3
    r = api(p, "GET", "/api/reservas/5")["dados"]
    r2 = api(p, "PUT", "/api/reservas/5", dict(r, nome=longo[:100]))
    assert r2["status"] == 200, r2
    api(p, "POST", "/api/reservas/5/despesas", {"categoria": "outros", "descricao": ("Serviçoextraordinariamente" * 6)[:120],
                                               "quantidade": 1, "valor_unit_centavos": 1234})
    p.reload()
    p.wait_for_selector("#mrResumo .cd-cartao")
    abrir_pelo_mapa(p, 5)
    for botao in (None, "info", "receber", "extrato"):
        if botao and botao != "extrato":
            abrir_painel(p, botao)
        sw, cw, dw, iw = sem_rolagem_lateral(p)
        assert sw <= cw + 1 and dw <= iw + 1, (botao, sw, cw, dw, iw)
    t.fechar()
