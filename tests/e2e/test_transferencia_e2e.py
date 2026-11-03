"""E2E (Edge): etapa 3B: Transferir com busca, Info (lista), estorno da diária, Fechar/Reabrir conta, perfis, celular 390 px e tema escuro.

SEMENTE (diária R$ 150,00): 4 Davi (203, 2 noites) origem;  2 Bruno (202) destino;  1 Ana (201) estorno da diária;  5 XSS fecha a conta.
Porta 5122 (faixa 5121-5129). Nada depende da hora do dia.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5122")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, erros_graves  # noqa: E402
from test_hospedagem_visual_e2e import contraste, cores  # noqa: E402
from test_pagamentos_e2e import PAINEL, abrir_painel, api, despesa, esperar_tile, esperar_toast, valor_tile  # noqa: E402
from test_resumo_e2e import abrir_pelo_mapa  # noqa: E402


def barra(p):
    return p.locator("#rcBarraItens [data-rc]").evaluate_all("els => els.filter(e => !e.classList.contains('oculto')).map(e => e.dataset.rc)")


def test_transferir_diaria_e_consumo_com_busca_do_destino(admin):
    p = admin.page
    despesa(p, 4, "Refrigerante", 700, 2)
    abrir_pelo_mapa(p, 4)
    p.check("#rcHospede .rc-item-caixa")                    # todos os itens marcados, um a um
    for cx in p.locator("#rcHospede .rc-item-caixa").all():
        cx.check()
    abrir_painel(p, "transferir")
    assert p.get_by_label("Buscar por nome do hóspede ou número do quarto").input_value() == ""
    assert p.locator(PAINEL + " .rc-dest").count() >= 1 and p.locator(PAINEL + " .primario").is_disabled()
    p.fill("#rcDestBusca", "José")                          # reserva futura: não é destino
    p.click(PAINEL + " .rc-dest-buscar")
    p.wait_for_selector(PAINEL + " .rc-dests:has-text('Nenhuma hospedagem')")
    p.fill("#rcDestBusca", "bruno")
    p.keyboard.press("Enter")
    p.wait_for_selector(PAINEL + " .rc-dest:has-text('Bruno Lima')")
    assert p.locator(PAINEL + " .rc-dest").count() == 1
    p.check(PAINEL + " .rc-dest input")
    p.click(PAINEL + " .primario")
    esperar_toast(p, "Transferido para o apartamento 202")
    esperar_tile(p, "diaria", "R$ 0,00")
    esperar_tile(p, "consumo", "R$ 0,00")
    destino = api(p, "GET", "/api/reservas/2/despesas")["dados"]["itens"]
    assert {i["descricao"] for i in destino} >= {"Refrigerante", "Diária da reserva #4 (2 noites)"}
    abrir_painel(p, "info")
    p.select_option("#rcInfoFiltro", "transferencia")
    txt = p.inner_text(PAINEL + " .rc-info")
    assert "Transferido para #2 (apto 202)" in txt and "Diária zerada" in txt and "admin" in txt
    p.select_option("#rcInfoFiltro", "")
    assert p.locator(PAINEL + " .rc-info li").count() == 3
    assert erros_graves(admin.erros) == []


def test_transferir_por_numero_do_quarto_e_nao_para_si_mesmo(admin):
    p = admin.page
    despesa(p, 1, "Pastel", 900)
    abrir_pelo_mapa(p, 1)
    p.check("#rcHospede .rc-az-consumo .rc-az-caixa")
    abrir_painel(p, "transferir")
    p.fill("#rcDestBusca", "201")
    p.click(PAINEL + " .rc-dest-buscar")
    p.wait_for_selector(PAINEL + " .rc-dests:has-text('Nenhuma hospedagem')")           # o próprio apartamento não aparece
    p.fill("#rcDestBusca", "202")
    p.click(PAINEL + " .rc-dest-buscar")
    p.wait_for_selector(PAINEL + " .rc-dest:has-text('Apto 202')")
    p.keyboard.press("Escape")
    assert p.evaluate("() => document.activeElement.dataset.rc") == "transferir"


def test_estornar_a_diaria_zera_com_motivo_e_aparece_no_historico_sem_valor(admin):
    p = admin.page
    abrir_pelo_mapa(p, 1)
    p.check("#rcHospede .rc-az-diaria .rc-az-caixa")
    abrir_painel(p, "estornar")
    assert "zerada" in p.inner_text(PAINEL)
    p.get_by_label("Motivo (obrigatório)").fill("Hóspede não pernoitou")
    p.click(PAINEL + " .perigo")
    esperar_tile(p, "diaria", "R$ 0,00")
    h = api(p, "GET", "/api/historico?limite=50")["dados"]
    achados = [x for x in (h if isinstance(h, list) else h.get("itens", [])) if x.get("acao") == "diaria_zerada"]
    assert achados and "450" not in str(achados) and "pernoitou" not in str(achados)


def test_fechar_e_reabrir_a_conta(admin):
    p = admin.page
    abrir_pelo_mapa(p, 5)
    assert "fechar" not in barra(p)                          # saldo diferente de zero
    abrir_painel(p, "receber")
    p.click(PAINEL + " .primario")                           # nada selecionado: o valor sugerido é o saldo inteiro
    esperar_tile(p, "saldo", "R$ 0,00")
    assert "fechar" in barra(p) and "receber" not in barra(p)[:0]
    abrir_painel(p, "fechar")
    p.click(PAINEL + " .primario")
    esperar_toast(p, "Conta fechada")
    p.wait_for_function("() => !document.querySelector('#rcBarraItens [data-rc=receber]')")
    assert "reabrir_conta" in barra(p) and "Fechada em" in p.inner_text("#rcCartao")
    abrir_painel(p, "reabrir_conta")
    p.click(PAINEL + " .primario")
    assert "motivo" in p.inner_text(PAINEL + " .aviso").lower()
    p.get_by_label("Motivo (obrigatório)").fill("Faltou lançar o frigobar")
    p.click(PAINEL + " .primario")
    esperar_toast(p, "Conta reaberta")
    p.wait_for_selector('#rcBarraItens [data-rc="receber"]', state="attached")


def test_recepcao_recebe_e_ve_mas_nao_estorna_nem_transfere(navegador, servidor):
    t = Tela(navegador, "recep")
    p = t.page
    try:
        abrir_pelo_mapa(p, 2)
        p.check("#rcHospede .rc-az-diaria .rc-az-caixa")
        ids = barra(p)
        assert "receber" in ids and "extrato" in ids and "info" in ids and "estornar" not in ids and "transferir" not in ids
        assert api(p, "POST", "/api/reservas/2/transferir", {"destino_id": 1, "itens": ["diaria"], "chave": "chave-recep-1", "conta_versao": 1})["status"] == 403
        assert api(p, "POST", "/api/pagamentos/1/estorno", {"motivo": "tentativa"})["status"] == 403
    finally:
        t.fechar()


def test_diretoria_so_ve_e_camareira_nao_tem_nada(navegador, servidor):
    t = Tela(navegador, "dir")
    try:
        abrir_pelo_mapa(t.page, 2)
        assert barra(t.page) == ["extrato", "info"] and "saldo a pagar" in t.page.inner_text("#rcHospede").lower()
    finally:
        t.fechar()
    c = Tela(navegador, "cam")
    try:
        assert api(c.page, "GET", "/api/reservas/2/pagamentos")["status"] == 403 and api(c.page, "GET", "/api/reservas/2/lancamentos")["status"] == 403
    finally:
        c.fechar()


def test_celular_390_e_tema_escuro_paineis_legiveis(navegador, servidor):
    for esquema in ("dark", "light"):
        t = Tela(navegador, "admin", 390, 844, esquema)
        p = t.page
        try:
            abrir_pelo_mapa(p, 2)
            p.check("#rcHospede .rc-az-diaria .rc-az-caixa")
            for botao in ("receber", "info", "estornar", "transferir"):
                abrir_painel(p, botao)
                assert p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), botao
                box = p.locator(PAINEL).bounding_box()
                assert box["x"] >= 0 and box["x"] + box["width"] <= 390
                for b in p.locator(PAINEL + " button:visible, " + PAINEL + " select:visible, " + PAINEL + " input:not([type=radio]):visible").all():
                    c = b.bounding_box()
                    assert c and c["height"] >= 43, (botao, b.inner_text()[:20], c)
                for seletor in (PAINEL + " h3", PAINEL + " p.suave", PAINEL + " label"):
                    if p.locator(seletor).count():
                        c = cores(p, seletor)
                        assert contraste(c["texto"], c["fundo"]) >= 4.5, (seletor, esquema, c)
                p.keyboard.press("Escape")                               # Esc fecha só o painel e devolve o foco ao botão
                assert p.evaluate("() => document.activeElement.dataset.rc") == botao and p.locator("#dlgResumo[open]").count() == 1
            t.foto("pagamentos_%s" % esquema)
            assert erros_graves(t.erros) == []
        finally:
            t.fechar()
