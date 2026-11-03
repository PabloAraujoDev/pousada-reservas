"""E2E (Edge): listas dos cartões no Mapa da reserva (painel embutido) e no Calendário.

Só com POUSADA_E2E=1. Instância própria na porta 5067 (veja base_operacao.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import SEMENTE, Tela, br, dia, erros_graves, esperado, hora_agora  # noqa: E402

LINHAS = "#mrTabela tbody tr.cd-linha"


def abrir(p, cat):
    p.click("#mrResumo .cd-cat-" + cat)
    p.wait_for_selector("#mrLista:not(.oculto)")


def test_cada_cartao_abre_a_lista_certa_no_mapa(admin):
    p, e = admin.page, esperado(hora_agora())
    esperados = {"ins": e["ins"], "outs": e["outs"], "interditados": 1, "ocupados": e["ocupados"], "vagos": e["vagos"]}
    assert p.locator("#mrLista").is_hidden()
    for cat, qtd in esperados.items():
        abrir(p, cat)
        titulo = {"ins": "Check-ins", "outs": "Check-outs", "interditados": "Interditados", "ocupados": "Ocupados", "vagos": "Vagos"}[cat]
        assert p.inner_text("#mrListaTit") == "%s de %s (hoje)" % (titulo, br(0))
        assert p.locator(LINHAS).count() == qtd, cat
        assert p.get_attribute("#mrResumo .cd-cat-" + cat, "aria-pressed") == "true"
        assert p.locator('#mrResumo .cd-cartao[aria-pressed="true"]').count() == 1
        assert "apartamento" in p.inner_text("#mrListaCont")
    assert p.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-mapa"        # nunca saiu do Mapa


def test_vagos_e_interditados_mostram_unidades_e_quando(admin):
    p = admin.page
    abrir(p, "vagos")
    cab = p.locator("#mrTabela thead th").all_inner_texts()
    assert [c for c in cab if c != "Ações"] == ["Apto", "Situação", "Quando fica ocupada/livre"]
    chale = p.locator(LINHAS, has_text="Chalé A").inner_text()
    assert "Livre até %s" % br(5)[:5] in chale and "José Pereira" in chale and "14h" in chale
    assert "Sem próxima reserva" in p.locator(LINHAS, has_text="101").first.inner_text()
    assert p.locator("#mrTabela").evaluate("t => t.querySelector('caption').textContent") != ""
    abrir(p, "interditados")
    linha = p.locator(LINHAS)
    assert linha.count() == 1 and "104" in linha.inner_text() and "Fora de venda" in linha.inner_text()
    assert p.locator("#mrTabela .od-nova, #mrTabela button.cd-apto-btn").count() == 0       # interditada não abre reserva


def test_ocupados_tem_coluna_sai_em(admin):
    p = admin.page
    abrir(p, "ocupados")
    assert "Sai em" in p.locator("#mrTabela thead th").all_inner_texts()
    assert "12h" in p.locator(LINHAS).first.inner_text()


def test_segundo_clique_fecha_e_foco_volta_ao_cartao(admin):
    p = admin.page
    abrir(p, "outs")
    assert p.evaluate("() => document.activeElement.id") == "mrListaTit"            # foco no título ao abrir
    p.keyboard.press("Escape")
    assert p.locator("#mrLista").is_hidden()
    assert p.evaluate("() => document.activeElement.dataset.foco") == "cat:outs"    # e volta ao cartão
    assert p.get_attribute("#mrResumo .cd-cat-outs", "aria-pressed") == "false"
    abrir(p, "ins")
    p.click("#mrResumo .cd-cat-ins")
    assert p.locator("#mrLista").is_hidden()
    abrir(p, "ins")
    p.click("#mrListaFechar")
    assert p.locator("#mrLista").is_hidden() and p.get_attribute("#mrResumo .cd-cat-ins", "aria-pressed") == "false"


def test_teclado_abre_com_enter(admin):
    p = admin.page
    p.focus("#mrResumo .cd-cat-ins")
    p.keyboard.press("Enter")
    p.wait_for_selector("#mrLista:not(.oculto)")
    assert p.evaluate("() => document.activeElement.id") == "mrListaTit"


def test_pesquisa_filtra_e_sobrevive_ao_polling(admin):
    p = admin.page
    abrir(p, "ocupados")
    total = p.locator(LINHAS).count()
    p.fill("#mrBusca", "zzzz")
    assert p.locator(LINHAS).count() == 0 and "Nenhuma reserva corresponde à busca" in p.inner_text("#mrTabela")
    p.fill("#mrBusca", "Ana")
    assert p.locator(LINHAS).count() <= total
    p.focus("#mrBusca")
    p.keyboard.type(" Silva")
    p.wait_for_timeout(9500)                                                          # passa um ciclo do polling de 8 s
    assert p.input_value("#mrBusca") == "Ana Silva"
    assert p.evaluate("() => document.activeElement.id") == "mrBusca"                 # nem texto nem foco se perdem
    assert p.locator("#mrLista").is_visible() and "(de " in p.inner_text("#mrListaCont")


def test_trocar_o_dia_atualiza_a_lista(admin):
    p = admin.page
    abrir(p, "outs")
    p.click("#mrProx")
    assert p.inner_text("#mrListaTit") == "Check-outs de %s (neste dia)" % br(1)
    assert p.locator(LINHAS).count() == 1 and "Ana Silva" in p.inner_text("#mrTabela")      # 201 sai amanhã
    p.click("#mrHoje")
    assert "(hoje)" in p.inner_text("#mrListaTit")


def test_clique_na_linha_abre_a_reserva_e_no_vago_a_nova_reserva(admin):
    p = admin.page
    abrir(p, "ins")
    p.click('#mrTabela .cd-apto-btn[aria-label*="Bruno Lima"]')
    p.wait_for_selector("#dlgResumo[open]")
    p.click('#rcCartao [data-rc="editar"]')
    assert p.evaluate("() => document.getElementById('dlg').open") is True and p.input_value("#fnome") == "Bruno Lima"
    p.click("#btnCancelar")
    p.evaluate("() => document.getElementById('dlgResumo').close()")
    abrir(p, "vagos")
    p.click('#mrTabela .od-nova[data-apto="101"]')
    assert p.input_value("#fa") == "101" and p.input_value("#fi") == dia(0) and p.inner_text("#dlgTitulo") == "Nova reserva"
    p.click("#btnCancelar")


def test_dia_passado_nao_oferece_nova_reserva(admin):
    p = admin.page
    abrir(p, "vagos")
    p.click("#mrAnt")
    assert p.locator("#mrTabela .od-nova").count() == 0 and p.locator("#mrTabela button[data-apto]").count() == 0
    p.click("#mrProx")
    p.click("#mrProx")
    assert p.locator("#mrTabela .od-nova").count() > 0


def test_consulta_ve_a_lista_mas_nao_cria(navegador, servidor):
    t = Tela(navegador, "consulta")
    try:
        t.page.click("#mrResumo .cd-cat-vagos")
        assert t.page.locator(LINHAS).count() == esperado(hora_agora())["vagos"]
        assert t.page.locator("#mrTabela .od-nova, #mrTabela button[data-apto]").count() == 0
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()


def test_calendario_cabecalho_colunas_e_fechar(admin):
    p = admin.page
    p.click('nav button[data-aba="calendario"]')
    p.wait_for_selector("#cdTabela tbody tr")
    assert p.inner_text("#cdListaTit") == "Movimento de %s (hoje)" % br(0)
    p.click("#cdResumo .cd-cat-vagos")
    assert p.inner_text("#cdListaTit") == "Vagos de %s (hoje)" % br(0)
    cab = [c for c in p.locator("#cdTabela thead th").all_inner_texts() if c != "Ações"]
    assert cab == ["Apto", "Situação", "Quando fica ocupada/livre"]
    assert "apartamentos" in p.inner_text("#cdListaResumo")
    p.click("#cdResumo .cd-cat-ocupados")
    assert "Sai em" in p.locator("#cdTabela thead th").all_inner_texts()
    assert p.inner_text("#cdLimpar") == "Fechar lista"
    p.click("#cdLimpar")
    assert p.inner_text("#cdListaTit").startswith("Movimento de") and p.locator("#cdLimpar").is_hidden()
    p.click("#cdResumo .cd-cat-interditados")
    assert "Nenhum apartamento interditado" not in p.inner_text("#cdTabela") and "104" in p.inner_text("#cdTabela")
    assert erros_graves(admin.erros) == []


def test_vazio_por_categoria_no_calendario(admin):
    p = admin.page
    p.click('nav button[data-aba="calendario"]')
    p.evaluate("() => { document.getElementById('cdData').value = '2030-01-15'; document.getElementById('cdData').dispatchEvent(new Event('change')); }")
    p.click("#cdResumo .cd-cat-ins")
    assert "Nenhum check-in neste dia." in p.inner_text("#cdTabela")
    p.click("#cdResumo .cd-cat-ocupados")
    assert "Nenhum apartamento ocupado." in p.inner_text("#cdTabela")


def test_xss_no_nome_continua_texto_na_lista_do_mapa(admin):
    p = admin.page
    abrir(p, "ocupados")
    assert p.locator("#mrTabela img").count() == 0 and p.evaluate("() => window.__xss") is None
