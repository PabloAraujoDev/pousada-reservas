"""E2E (Edge): etapa 3B do Resumo da conta: Extrato do selecionado, Receber (dinheiro, Pix, cartão parcelado), Estornar com motivo.

Dados de base_operacao.SEMENTE (diária R$ 150,00; datas relativas a hoje, nada depende da hora do dia): 1 Ana (201) extrato;
2 Bruno (202, 3 noites = R$ 450,00) recebimentos;  5 XSS (205, -1..2) estornos. Porta 5121 (faixa 5121-5129).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5121")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import erros_graves  # noqa: E402
from test_resumo_e2e import abrir_pelo_mapa  # noqa: E402

PAINEL = "#rcPainelItens"


def api(p, metodo, url, corpo=None):
    return p.evaluate("([m, u, c]) => api(m, u, c).then(r => ({status: r.status, dados: r.dados}))", [metodo, url, corpo])


def despesa(p, rid, desc, valor, qtd=1):
    r = api(p, "POST", "/api/reservas/%d/despesas" % rid, {"categoria": "bar", "descricao": desc, "quantidade": qtd, "valor_unit_centavos": valor})
    assert r["status"] == 201, r


def capturar_impressao(p):
    p.evaluate("() => { window.__imp = null; window.print = () => { window.__imp = document.getElementById('rcExtratoImp').innerText; }; }")


def texto_impresso(p):
    p.wait_for_function("() => window.__imp !== null")
    return p.evaluate("() => window.__imp")


def esperar_toast(p, texto):
    p.wait_for_function("t => document.getElementById('toast').textContent.includes(t)", arg=texto, timeout=8000)


def valor_tile(p, tile):
    return p.inner_text("#rcHospede .rc-az-%s .rc-az-valor" % tile)


def esperar_tile(p, tile, texto):
    p.wait_for_function("([t, x]) => { const e = document.querySelector('#rcHospede .rc-az-' + t + ' .rc-az-valor'); return e && e.textContent === x; }",
                        arg=[tile, texto], timeout=8000)


def abrir_painel(p, botao):
    p.click('#rcBarraItens [data-rc="%s"]' % botao)
    p.wait_for_selector("%s:not(.oculto) h3" % PAINEL)


def test_extrato_imprime_so_o_selecionado(admin):
    p = admin.page
    despesa(p, 1, "Agua mineral", 800, 2)
    despesa(p, 1, "Suco de uva", 1250)
    abrir_pelo_mapa(p, 1)
    capturar_impressao(p)
    p.check("#rcHospede .rc-item-caixa[data-item='diaria']")
    p.click('#rcBarraItens [data-rc="extrato"]')
    t = texto_impresso(p)
    assert "Pousada Boa Esperança" in t and "Extrato parcial" in t and "Diárias" in t and "Agua mineral" not in t and "Ana Silva" in t
    assert "Apartamento 201" in t and "Emitido em" in t and "R$ 450,00" in t and "Saldo a pagar" not in t
    p.uncheck("#rcHospede .rc-item-caixa[data-item='diaria']")
    p.check("#rcHospede .rc-az-consumo .rc-az-caixa")
    capturar_impressao(p)
    p.click('#rcBarraItens [data-rc="extrato"]')
    t = texto_impresso(p)
    assert "Agua mineral" in t and "Suco de uva" in t and "Diárias" not in t and "R$ 28,50" in t
    p.uncheck("#rcHospede .rc-az-consumo .rc-az-caixa")
    capturar_impressao(p)
    p.click('#rcBarraItens [data-rc="extrato"]')
    t = texto_impresso(p)
    assert "Conta inteira" in t and "Diárias" in t and "Suco de uva" in t and "Saldo a pagar" in t and "R$ 478,50" in t
    assert p.evaluate("() => document.getElementById('rcExtratoImp').textContent") == ""         # nada fica no DOM depois de imprimir
    assert erros_graves(admin.erros) == []


def test_receber_dinheiro_parcial_pix_e_cartao_parcelado(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    assert valor_tile(p, "saldo") == "R$ 450,00" and valor_tile(p, "credito") == "R$ 0,00"
    abrir_painel(p, "receber")
    assert p.get_by_label("Valor a receber (R$)").input_value() == "450,00"          # nada selecionado: a conta inteira da tela
    p.get_by_label("Valor a receber (R$)").fill("500,00")
    p.click(PAINEL + " .primario")
    assert "não pode passar do saldo" in p.inner_text(PAINEL + " .aviso")
    p.get_by_label("Valor a receber (R$)").fill("100,00")
    p.get_by_label("Valor entregue pelo hóspede (R$, opcional)").fill("120,00")
    assert "Troco: R$ 20,00" in p.inner_text(PAINEL)
    p.click(PAINEL + " .primario")
    esperar_toast(p, "Pagamento de R$ 100,00 registrado")
    esperar_tile(p, "saldo", "R$ 350,00")
    assert valor_tile(p, "credito") == "R$ 100,00"
    abrir_painel(p, "receber")
    p.get_by_label("Forma de pagamento").select_option("pix")
    p.get_by_label("Valor a receber (R$)").fill("50,00")
    p.get_by_label("Referência do Pix (opcional, só letras e números)").fill("E2026abc")
    p.click(PAINEL + " .primario")
    esperar_toast(p, "R$ 50,00")
    esperar_tile(p, "saldo", "R$ 300,00")
    abrir_painel(p, "receber")
    p.get_by_label("Forma de pagamento").select_option("cartao")
    p.get_by_label("Valor a receber (R$)").fill("100,01")
    p.get_by_label("Pagamento no crédito").select_option("parcelado")
    p.get_by_label("Número de parcelas (2 a 12)").fill("3")
    assert "2x de R$ 33,34 e 1x de R$ 33,33" in p.inner_text(PAINEL)
    p.get_by_label("Código de autorização / NSU da maquineta (opcional)").fill("4111111111111111")
    assert len(p.get_by_label("Código de autorização / NSU da maquineta (opcional)").input_value()) == 12      # o campo nem comporta um número de cartão
    p.get_by_label("Pagamento no crédito").select_option("parcelado")
    p.get_by_label("Código de autorização / NSU da maquineta (opcional)").fill("AB12 CD")
    p.click(PAINEL + " .primario")
    assert "só letras e números" in p.inner_text(PAINEL + " .aviso")
    p.get_by_label("Código de autorização / NSU da maquineta (opcional)").fill("AB12CD")
    p.click(PAINEL + " .primario")
    esperar_toast(p, "R$ 100,01")
    esperar_tile(p, "saldo", "R$ 199,99")
    itens = api(p, "GET", "/api/reservas/2/pagamentos")["dados"]["itens"]
    assert [(i["forma"], i["valor_centavos"]) for i in itens] == [("cartao", 10001), ("pix", 5000), ("dinheiro", 10000)]
    assert itens[0]["parcelas"] == 3 and itens[0]["autorizacao"] == "AB12CD" and itens[2]["troco_centavos"] == 2000
    assert erros_graves(admin.erros) == []


def test_receber_so_o_selecionado_leva_o_valor_dele(admin):
    p = admin.page
    despesa(p, 2, "Lavagem de roupa", 3000)
    abrir_pelo_mapa(p, 2)
    p.check("#rcHospede .rc-az-consumo .rc-az-caixa")
    abrir_painel(p, "receber")
    assert p.get_by_label("Valor a receber (R$)").input_value() == "30,00"
    p.keyboard.press("Escape")
    p.wait_for_selector(PAINEL + ".oculto", state="attached")
    assert p.evaluate("() => document.activeElement.dataset.rc") == "receber"


def test_estornar_exige_motivo_e_estorna_consumo_e_pagamento(admin):
    p = admin.page
    despesa(p, 5, "Cerveja", 1000)
    abrir_pelo_mapa(p, 5)
    assert p.locator('#rcBarraItens [data-rc="estornar"]').is_hidden()                    # só aparece com seleção
    p.check("#rcHospede .rc-item-caixa[data-item^='d']:not([data-item='diaria'])")
    abrir_painel(p, "estornar")
    p.click(PAINEL + " .perigo")
    assert "motivo" in p.inner_text(PAINEL + " .aviso").lower()
    p.get_by_label("Motivo (obrigatório)").fill("cartão 4111 1111 1111 1111")
    p.click(PAINEL + " .perigo")
    assert "número de cartão" in p.inner_text(PAINEL + " .aviso")
    p.get_by_label("Motivo (obrigatório)").fill("Lançado no apartamento errado")
    p.click(PAINEL + " .perigo")
    esperar_toast(p, "Estornado: 1 item")
    esperar_tile(p, "consumo", "R$ 0,00")
    abrir_painel(p, "info")
    p.select_option("#rcInfoFiltro", "estorno")
    txt = p.inner_text(PAINEL + " .rc-info")
    assert "Estorno: Cerveja" in txt and "Lançado no apartamento errado" in txt and "admin" in txt
    assert erros_graves(admin.erros) == []
