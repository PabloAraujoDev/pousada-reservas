"""E2E (Edge): etapa 3A do Resumo da conta (hóspedes, check-in e reversão, liberar com conta aberta, placa, seleção por tipo).

Dados de base_operacao.SEMENTE (datas relativas a hoje; nada depende da hora do dia). Cada teste usa a sua reserva:
2 Bruno (202, hoje a +3): hóspedes e seleção;  4 Davi (203, hoje a +2): check-in/reversão;  5 XSS (205): liberar;  1 Ana (201): placa e ficha.
Porta: POUSADA_E2E_PORTA (5112 por padrão aqui; faixa 5111-5119).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5112")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, XSS, erros_graves  # noqa: E402
from test_resumo_e2e import RESUMO, abrir_pelo_mapa, botoes_do_cartao, como  # noqa: E402


def painel(p, nome="rcPainelAcao"):
    return p.locator("#%s" % nome)


def confirmar(p, classe="primario", motivo=None):
    if motivo:
        p.get_by_label("Motivo (obrigatório)").fill(motivo)       # liberar, desfazer a liberação e reverter check-in exigem motivo
    p.click("#rcPainelAcao .%s" % classe)


def api(p, metodo, url, corpo=None):
    return p.evaluate("([m, u, c]) => api(m, u, c).then(r => ({status: r.status, dados: r.dados}))", [metodo, url, corpo])


def test_hospedes_adicionar_salvar_limite_e_xss(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    p.click('#rcCartao [data-rc="hospedes"]')
    p.wait_for_selector("#rcPainelAcao .rc-hp-linha")
    assert p.evaluate("() => document.activeElement.textContent") == "Manutenção de hóspedes"
    assert "Titular: Bruno Lima" in p.inner_text("#rcPainelAcao")
    p.click("#rcHpAdd")
    linha = p.locator("#rcPainelAcao .rc-hp-linha").nth(1)
    linha.locator("input").first.fill(XSS)
    linha.locator("select").select_option("crianca")
    linha.locator("summary").click()
    linha.locator("input").nth(1).fill("MG-1234567")
    assert p.locator("#rcHpAdd").is_disabled() and "Todas as 2 pessoas" in p.inner_text("#rcHpDica")      # n = 2: titular + 1
    confirmar(p)
    p.wait_for_selector("#rcPainelAcao.oculto", state="attached")
    assert "Hóspedes salvos" in p.inner_text("#toast")
    p.click('#rcCartao [data-rc="hospedes"]')
    p.wait_for_selector("#rcPainelAcao .rc-hp-linha >> nth=1")
    assert p.locator("#rcPainelAcao .rc-hp-linha").nth(1).locator("input").first.input_value() == XSS      # texto, nunca HTML
    assert p.locator("#dlgResumo img").count() == 0 and p.evaluate("() => window.__xss") is None
    p.keyboard.press("Escape")
    assert erros_graves(admin.erros) == []


def test_hospedes_nome_vazio_e_cartao_nao_gravam(admin):
    p = admin.page
    abrir_pelo_mapa(p, 4)
    p.click('#rcCartao [data-rc="hospedes"]')
    p.wait_for_selector("#rcPainelAcao .rc-hp-linha")
    p.click("#rcHpAdd")
    confirmar(p)
    assert "Informe o nome" in p.inner_text("#rcPainelAcao")
    linha = p.locator("#rcPainelAcao .rc-hp-linha").nth(1)
    linha.locator("input").first.fill("4111 1111 1111 1111")
    confirmar(p)
    p.wait_for_selector("#rcPainelAcao .aviso.erro:has-text('número de cartão')")
    assert "4111" not in p.inner_text("#rcPainelAcao .aviso")
    p.keyboard.press("Escape")


def test_checkin_reversao_bloqueada_e_depois_liberada_sem_mexer_nos_cartoes(admin):
    p = admin.page
    antes = admin.numeros("#mrResumo")
    abrir_pelo_mapa(p, 4)
    assert "Check-in pendente" in p.inner_text("#rcCartao")
    p.click('#rcCartao [data-rc="checkin"]')
    confirmar(p)
    p.wait_for_selector("#rcCartao [data-rc='reverter']")
    assert "Check-in efetuado" in p.inner_text("#rcCartao") and "por admin" in p.inner_text("#rcCartao")
    assert p.locator("#rcCartao [data-rc='checkin']").count() == 0
    p.click('#rcCartao [data-rc="reverter"]')                       # a diária está informada (R$ 150,00): o servidor bloqueia
    confirmar(p, "perigo", "Motivo do teste e2e")
    p.wait_for_selector("#rcPainelAcao .aviso.erro")
    assert "diária" in p.inner_text("#rcPainelAcao .aviso") and "Alterar estadia" in p.inner_text("#rcPainelAcao .aviso")
    p.keyboard.press("Escape")
    r = api(p, "GET", "/api/reservas/4")["dados"]
    assert api(p, "PUT", "/api/reservas/4", dict(r, diaria_centavos=None))["status"] == 200
    p.evaluate("() => rcAtualizar(true)")
    p.click('#rcCartao [data-rc="reverter"]')
    confirmar(p, "perigo", "Motivo do teste e2e")
    p.wait_for_selector("#rcCartao [data-rc='checkin']")
    assert "Check-in pendente" in p.inner_text("#rcCartao")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    assert admin.numeros("#mrResumo") == antes                      # Check-ins/Ocupados seguem as datas


def test_duplo_clique_no_checkin_registra_uma_vez(admin):
    p = admin.page
    abrir_pelo_mapa(p, 5)
    v0 = api(p, "GET", "/api/reservas/5")["dados"]["versao"]
    p.click('#rcCartao [data-rc="checkin"]')
    p.locator("#rcPainelAcao .primario").dblclick()
    p.wait_for_selector("#rcCartao [data-rc='reverter']")
    d = api(p, "GET", "/api/reservas/5")["dados"]
    assert d["versao"] == v0 + 1 and d["estado_hospedagem"] == "efetuado"
    p.keyboard.press("Escape")


def test_liberar_deixa_conta_aberta_aparece_em_contas_abertas_e_governanca(admin):
    p = admin.page
    abrir_pelo_mapa(p, 1)
    p.click('#rcCartao [data-rc="liberar"]')
    assert "livre (e suja)" in p.inner_text("#rcPainelAcao")
    confirmar(p, "primario", "Hóspede saiu sem acertar a conta")
    p.wait_for_selector("#rcCartao [data-rc='reabrir']")
    assert "Apartamento liberado, conta aberta" in p.inner_text("#rcCartao") and p.locator("#rcCartao [data-rc='checkin']").count() == 0
    p.wait_for_selector("#rcContasBtn:visible")
    assert "Contas abertas: 1" in p.inner_text("#rcContasBtn")
    p.click("#rcContasBtn")
    assert "Apto 201" in p.inner_text("#rcContasLista") and p.get_attribute("#rcContasBtn", "aria-expanded") == "true"
    gov = api(p, "GET", "/api/governanca")["dados"]["unidades"]
    u201 = next(u for u in gov if u["u"] == "201")
    assert u201["situacao"] == "suja" and u201["ocupacao"] == "vaga"
    assert api(p, "GET", "/api/reservas/1/despesas")["status"] == 200               # a conta continua acessível
    p.click('#rcCartao [data-rc="reabrir"]')
    confirmar(p, "primario", "Hóspede voltou para acertar")
    p.wait_for_selector("#rcCartao [data-rc='liberar']")
    p.wait_for_selector("#rcContas.oculto", state="attached")
    p.keyboard.press("Escape")


def test_placa_valida_normaliza_e_aparece_na_ficha(admin):
    p = admin.page
    abrir_pelo_mapa(p, 1)
    p.click('#rcBarraItens [data-rc="placa"]')
    assert p.evaluate("() => document.activeElement.textContent") == "Placa do veículo"
    p.fill("#rcPainelItens input", "xx-12")
    p.click("#rcPainelItens .primario")
    assert "Placa inválida" in p.inner_text("#rcPainelItens")
    p.fill("#rcPainelItens input", "abc-1d23")
    p.click("#rcPainelItens .primario")
    p.wait_for_selector("#rcCartao .rc-placa .rc-val:text-is('ABC1D23')")
    p.evaluate("() => { window.print = () => { window.__ficha = document.getElementById('fnrhImpressao').innerText; }; }")
    p.click('#rcCartao [data-rc="ficha"]')
    p.wait_for_function("() => window.__ficha")
    ficha = p.evaluate("() => window.__ficha")
    for esperado in ("Ficha de check-in", "Apartamento", "ABC1D23", "Meio de transporte", "Motivo da viagem", "Nacionalidade", "Procedência", "Destino",
                     "Data de nascimento", "Profissão", "Acompanhante 1", "Assinatura do hóspede"):
        assert esperado in ficha, esperado
    assert p.evaluate("() => document.getElementById('fnrhImpressao').textContent") == ""       # nada fica no DOM depois de imprimir
    p.click('#rcBarraItens [data-rc="placa"]')
    p.fill("#rcPainelItens input", "")
    p.click("#rcPainelItens .primario")
    p.wait_for_selector("#rcCartao .rc-placa", state="detached")
    p.keyboard.press("Escape")


def test_selecao_visual_por_tipo_com_total_selecionado(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    api(p, "POST", "/api/reservas/2/despesas", {"categoria": "bar", "descricao": "Cerveja", "quantidade": 2, "valor_unit_centavos": 1000})
    p.evaluate("() => rcAtualizar(true)")
    p.wait_for_selector("#rcHospede .rc-item-caixa >> nth=1")
    assert "Nenhum item selecionado" in p.inner_text("#rcTotalSel")
    assert p.locator("#rcHospede .rc-az-evento .rc-az-caixa").is_disabled() and p.locator("#rcHospede .rc-az-credito .rc-az-caixa").is_disabled()
    p.check("#rcHospede .rc-az-diaria .rc-az-caixa")
    assert "Total selecionado: R$ 450,00 (1 item)" in p.inner_text("#rcTotalSel")
    p.check("#rcHospede .rc-az-consumo .rc-az-caixa")
    assert "R$ 470,00 (2 itens)" in p.inner_text("#rcTotalSel")
    p.uncheck("#rcHospede .rc-item-caixa[data-item='diaria']")
    assert p.locator("#rcHospede .rc-az-diaria .rc-az-caixa").is_checked() is False and "Total selecionado: R$ 20,00" in p.inner_text("#rcTotalSel")
    p.keyboard.press("Escape")
