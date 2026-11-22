"""E2E (Edge): Resumo da conta ao clicar numa reserva (cada origem), conteúdo por perfil e fluxos do cartão. Porta via POUSADA_E2E_PORTA.

Os dados vêm de base_operacao.SEMENTE (datas relativas a hoje; nada aqui depende da hora do dia).
Reservas: 1 Ana (201), 2 Bruno (202), 3 Carla (203), 4 Davi (203), 5 XSS (205), 6 José (Chalé A).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, br, dia, erros_graves  # noqa: E402

RESUMO = "#dlgResumo[open]"


def barra(p, rid):
    return p.locator('#mapa .barra-res[data-id="%d"]' % rid)


def abrir_pelo_mapa(p, rid=1):
    barra(p, rid).click()
    p.wait_for_selector(RESUMO)
    p.wait_for_selector("#rcPainel .nt-msg:empty")


def texto(p, seletor="#dlgResumo"):
    return p.inner_text(seletor)


def mudar_n(p, n):
    """Altera o nº de pessoas da reserva 4 direto na API (simula outra pessoa), sempre com a versão atual do servidor."""
    p.evaluate("(n) => api('GET', '/api/reservas/4').then(r => api('PUT', '/api/reservas/4', Object.assign({}, r.dados, {n: n})))", n)


def test_clicar_na_barra_do_mapa_abre_o_resumo_e_nao_o_formulario(admin):
    p = admin.page
    abrir_pelo_mapa(p, 1)
    assert p.evaluate("() => document.getElementById('dlg').open") is False
    assert p.inner_text("#rcTit") == "Apartamento 201 · Reserva #1" and p.evaluate("() => document.activeElement.id") == "rcTit"
    t = texto(p)
    for esperado in ("Ana Silva", "Sócio do clube", "Berço", "In %s (14h)" % br(-2), "Out %s (12h)" % br(1), "3 noites", "2 pessoas",
                     "Pago", "1 - ANA SILVA", "Apartamento 201 - 2º andar", "Tarifa", "Alergia a amendoim"):
        assert esperado in t, esperado
    assert "R$ 450,00 (3 x R$ 150,00)" in t and p.inner_text("#rcTotal").startswith("Total da estadia")
    assert "R$ 450,00" in p.inner_text("#rcTotal")                       # sem despesas ainda: o total é só as diárias
    botoes = p.locator("#rcCartao .rc-barra [data-rc]").evaluate_all("els => els.map(e => e.dataset.rc)")
    assert botoes == ["editar", "hospedes", "trocar", "liberar", "ficha", "checkin", "cancelar", "imprimir", "historico", "despesas"]
    assert "Em breve" in p.inner_text("#rcHospede") and erros_graves(admin.erros) == []


def test_esc_fecha_e_devolve_o_foco_a_barra(admin):
    p = admin.page
    barra(p, 1).focus()
    p.keyboard.press("Enter")
    p.wait_for_selector(RESUMO)
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    assert p.evaluate("() => document.activeElement.dataset.id") == "1"


def test_cada_origem_abre_o_resumo(admin):
    p = admin.page
    p.click("#mrResumo .cd-cat-ins")                                    # lista do Mapa
    p.click('#mrTabela .cd-apto-btn[aria-label*="Bruno Lima"]')
    p.wait_for_selector(RESUMO)
    assert p.inner_text("#rcTit") == "Apartamento 202 · Reserva #2"
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    p.click('nav button[data-aba="calendario"]')                        # lista do Calendário
    p.click("#cdResumo .cd-cat-ins")
    p.click('#cdTabela .cd-apto-btn[aria-label*="Bruno Lima"]')
    p.wait_for_selector(RESUMO)
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    p.click('nav button[data-aba="buscar"]')                            # resultado da Busca
    p.fill("#busca", "Carla")
    p.click("#resultados .item-busca")
    p.wait_for_selector(RESUMO)
    assert p.inner_text("#rcTit") == "Apartamento 203 · Reserva #3"
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    assert erros_graves(admin.erros) == []


def test_celula_vazia_abre_nova_reserva_direto(admin):
    p = admin.page
    p.locator('#mapa .d[data-apto="301"][data-dia="%s"]' % dia(3)).click()
    p.wait_for_selector("#dlg[open]")
    assert p.inner_text("#dlgTitulo") == "Nova reserva" and p.evaluate("() => document.getElementById('dlgResumo').open") is False
    p.click("#btnCancelar")


def test_editar_dados_abre_o_formulario_e_o_resumo_se_atualiza(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    p.click('#rcCartao [data-rc="editar"]')
    p.wait_for_selector("#dlg[open]")
    assert p.input_value("#fnome") == "Bruno Lima" and p.evaluate("() => document.getElementById('dlgResumo').open") is True
    p.fill("#fnome", "Bruno Lima Neto")
    p.click("#btnSalvar")
    p.wait_for_function("() => !document.getElementById('dlg').open")
    p.wait_for_selector("#rcCartao .rc-titular .rc-val:text-is('Bruno Lima Neto')")
    assert p.evaluate("() => document.getElementById('dlgResumo').open") is True
    assert p.evaluate("() => document.activeElement.dataset.rc") == "editar"
    p.click('#rcCartao [data-rc="editar"]')
    p.fill("#fnome", "Bruno Lima")
    p.click("#btnSalvar")
    p.wait_for_selector("#rcCartao .rc-titular .rc-val:text-is('Bruno Lima')")


def test_edicao_com_versao_antiga_da_409_como_sempre(admin):
    p = admin.page
    abrir_pelo_mapa(p, 4)
    mudar_n(p, 3)                                                       # "outra pessoa" altera
    p.click('#rcCartao [data-rc="editar"]')
    p.fill("#fnome", "Davi Rocha 2")
    p.click("#btnSalvar")
    p.wait_for_selector("#aviso.erro")
    assert "alterada por outra pessoa" in p.inner_text("#aviso")
    p.click("#btnCancelar")
    p.wait_for_selector("#rcMudou:not(.oculto), #rcCartao")
    mudar_n(p, 2)                                                       # devolve o estado


def test_trocar_de_apartamento_com_seletor_de_livres(admin):
    p = admin.page
    abrir_pelo_mapa(p, 6)                                                # José, Chalé A, daqui a 5 dias
    p.click('#rcCartao [data-rc="trocar"]')
    assert p.evaluate("() => document.activeElement.textContent") == "Transferência de apartamento"
    opcoes = p.locator("#rcNovoApto option").all_inner_texts()
    assert "Chalé A" not in opcoes and "104" not in opcoes and "301" in opcoes
    p.keyboard.press("Escape")                                           # Esc fecha só o painel
    assert p.locator("#rcPainelAcao.oculto").count() == 1 and p.evaluate("() => document.getElementById('dlgResumo').open")
    p.click('#rcCartao [data-rc="trocar"]')
    p.select_option("#rcNovoApto", "301")
    p.click("#rcPainelAcao .primario")
    p.wait_for_selector("#rcTit:text-is('Apartamento 301 · Reserva #6')")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    p.wait_for_selector('#mapa .linha[data-apto="301"] .barra-res[data-id="6"]')
    abrir_pelo_mapa(p, 6)                                                # e volta para o Chalé A
    p.click('#rcCartao [data-rc="trocar"]')
    p.select_option("#rcNovoApto", "Chalé A")
    p.click("#rcPainelAcao .primario")
    p.wait_for_selector("#rcTit:text-is('Apartamento Chalé A · Reserva #6')")


def test_cancelar_com_motivo_e_reativar(admin):
    p = admin.page
    abrir_pelo_mapa(p, 6)
    p.click('#rcCartao [data-rc="cancelar"]')
    p.click("#rcPainelAcao .perigo")
    assert "Informe o motivo" in p.inner_text("#rcPainelAcao")
    p.fill("#rcPainelAcao textarea", "Hóspede desistiu")
    p.click("#rcPainelAcao .perigo")
    p.wait_for_selector("#rcCartao .rc-cancelada")
    assert "Hóspede desistiu" in p.inner_text("#rcCartao .rc-cancelada") and "Cancelada" in p.inner_text("#rcSit")
    assert p.locator("#rcCartao [data-rc]").evaluate_all("els => els.map(e => e.dataset.rc)") == ["reativar", "imprimir", "historico"]
    assert p.locator(".nt-novo:not(.oculto)").count() == 0 or p.locator("#rcPainel .nt-novo:not(.oculto)").count() == 0
    p.click('#rcCartao [data-rc="reativar"]')
    p.wait_for_selector("#rcCartao .rc-cancelada", state="detached")
    assert "Hospedado" not in p.inner_text("#rcSit") and "Cancelada" not in p.inner_text("#rcSit")
    p.keyboard.press("Escape")


def test_cancelada_abre_o_resumo_pela_lista_de_canceladas(admin):
    p = admin.page
    p.evaluate("() => api('GET', '/api/reservas/5').then(r => api('DELETE', '/api/reservas/5', {versao: r.dados.versao, motivo: 'teste de lista'}))")
    p.click('nav button[data-aba="canceladas"]')
    p.click('#tabCanceladas [data-abrir="5"]')
    p.wait_for_selector(RESUMO)
    assert "Cancelada em" in p.inner_text("#rcCartao") and "teste de lista" in p.inner_text("#rcCartao")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    assert p.evaluate("() => document.activeElement.dataset.abrir") == "5"
    p.evaluate("() => api('GET', '/api/reservas/5').then(r => api('POST', '/api/reservas/5/reativar', {versao: r.dados.versao}))")


def test_notas_dentro_do_resumo_e_polling_nao_apaga_nem_fecha(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    p.fill("#rcPainel .nt-novo textarea", "rascunho que não pode sumir")
    p.wait_for_timeout(9500)                                              # mais de um ciclo de 8 s
    assert p.input_value("#rcPainel .nt-novo textarea") == "rascunho que não pode sumir"
    assert p.evaluate("() => document.getElementById('dlgResumo').open") and p.locator("#rcMudou.oculto").count() == 1
    p.click("#rcPainel .nt-add")
    p.wait_for_selector("#rcPainel .nt-nota")
    assert re.search(r"Adicionado por admin em \d\d/\d\d/\d{4} \d\d:\d\d", p.inner_text("#rcPainel"))


def test_reserva_alterada_por_outra_pessoa_mostra_faixa_sem_apagar_o_que_se_digita(admin):
    p = admin.page
    abrir_pelo_mapa(p, 4)
    p.fill("#rcPainel .nt-novo textarea", "texto em andamento")
    p.evaluate("() => api('GET', '/api/reservas/4').then(r => api('PUT', '/api/reservas/4', Object.assign({}, r.dados, {extras: 'Mudou fora'})))")
    p.wait_for_selector("#rcMudou:not(.oculto)", timeout=12000)
    assert p.input_value("#rcPainel .nt-novo textarea") == "texto em andamento"
    assert "Mudou fora" not in p.inner_text("#rcCartao")                  # nada redesenhado por baixo
    p.click("#rcRecarregar")
    p.wait_for_selector("#rcCartao .rc-val:text-is('Mudou fora')")
    assert p.locator("#rcMudou.oculto").count() == 1
    p.keyboard.press("Escape")


def test_atalhos_so_fora_de_campos_e_ficha_imprime_so_o_resumo(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    p.focus("#rcPainel .nt-novo textarea")
    p.keyboard.type("e")                                                  # em campo de texto, "e" só digita
    assert p.evaluate("() => document.getElementById('dlg').open") is False
    p.fill("#rcPainel .nt-novo textarea", "")
    p.focus("#rcTit")
    p.keyboard.press("e")
    p.wait_for_selector("#dlg[open]")
    p.click("#btnCancelar")
    p.wait_for_function("() => !document.getElementById('dlg').open")
    p.evaluate("() => { document.body.classList.add('imp-resumo'); }")
    p.emulate_media(media="print")
    assert p.locator("#dlgResumo").is_visible() and p.locator("#mapa").is_hidden() and p.locator(".rc-obs").is_hidden()
    assert p.locator("#rcCartao .rc-barra").is_hidden() and p.locator(".rc-base").is_hidden() and p.locator(".rc-imp-titulo").is_visible()
    assert p.locator("#aba-camareiras").is_hidden() and p.locator(".rc-ficha-ass").is_visible()
    p.evaluate("() => { document.body.classList.remove('imp-resumo'); }")
    p.emulate_media(media="print")
    assert p.locator("#dlgResumo").is_hidden()                            # as demais impressões não herdam a ficha
    p.emulate_media(media="screen")


def como(navegador, login, rid=1):
    t = Tela(navegador, login)
    abrir_pelo_mapa(t.page, rid)
    return t


def botoes_do_cartao(p):
    return p.locator("#rcCartao .rc-barra [data-rc]").evaluate_all("els => els.map(e => e.dataset.rc)")


def test_atendente_tudo_menos_nada_a_mais(navegador, servidor):
    t = como(navegador, "atend")
    try:
        assert botoes_do_cartao(t.page) == ["editar", "hospedes", "trocar", "liberar", "ficha", "checkin", "cancelar", "imprimir", "historico", "despesas"]
        assert "R$ 450,00" in t.page.inner_text("#rcCartao")
    finally:
        t.fechar()


def test_recepcao_ve_valores_edita_so_pagamento_e_observacoes_sem_trocar_nem_cancelar(navegador, servidor):
    t = como(navegador, "recep")
    p = t.page
    try:
        assert botoes_do_cartao(p) == ["editar", "hospedes", "liberar", "ficha", "checkin", "imprimir", "despesas"]
        assert "R$ 450,00" in p.inner_text("#rcCartao") and p.locator("#rcPainel .nt-novo:not(.oculto)").count() == 1
        for oculto in ("trocar", "cancelar", "reverter", "historico"):
            assert p.locator('#dlgResumo [data-rc="%s"]' % oculto).count() == 0
        p.click('#rcCartao [data-rc="editar"]')
        p.wait_for_selector("#dlg[open]")
        assert p.locator("#fo").is_enabled() and p.locator("#fnome").is_disabled()
        p.click("#btnCancelar")
        assert p.evaluate("() => api('POST', '/api/reservas/1/mover', {versao: 1, a: '301'}).then(r => r.status)") == 403
        assert p.evaluate("() => api('DELETE', '/api/reservas/1', {versao: 1, motivo: 'x'}).then(r => r.status)") == 403
    finally:
        t.fechar()


def test_diretoria_so_leitura_com_valores(navegador, servidor):
    t = como(navegador, "dir")
    p = t.page
    try:
        assert botoes_do_cartao(p) == ["hospedes", "imprimir", "despesas"]
        assert "R$ 450,00" in p.inner_text("#rcCartao") and p.locator("#rcPainel .nt-novo:not(.oculto)").count() == 0
        assert p.locator("#rcPainel .nt-corrigir").count() == 0
        status = p.evaluate("() => Promise.all([api('POST', '/api/reservas/1/despesas', {categoria: 'bar', descricao: 'Agua', quantidade: 1, valor_unit_centavos: 100}), "
                            "api('POST', '/api/reservas/1/notas', {texto: 'x'})]).then(r => r.map(x => x.status))")
        assert status == [403, 403]
    finally:
        t.fechar()


def test_consulta_so_leitura_sem_nenhum_valor_nem_despesas(navegador, servidor):
    t = como(navegador, "consulta")
    p = t.page
    try:
        assert botoes_do_cartao(p) == ["hospedes", "imprimir"]
        dom = p.evaluate("() => document.getElementById('dlgResumo').innerHTML")
        assert "R$" not in dom and "diaria" not in dom.lower() and "Diária" not in dom and "rc-az" not in dom and "Lançamentos" not in dom
        assert p.locator("#rcTotal .pilula").count() == 1 and p.locator("#rcBaseDespesas").is_hidden()      # sem total: mostra o pagamento
        assert "Alergia a amendoim" in p.inner_text("#rcPainel") and "Berço" in p.inner_text("#rcCartao")
        corpo = p.evaluate("() => fetch('/api/reservas/1').then(r => r.text())")
        assert "diaria" not in corpo
        assert p.evaluate("() => fetch('/api/reservas/1/despesas').then(r => r.status)") == 403
    finally:
        t.fechar()


def test_camareira_nunca_abre_o_resumo(navegador, servidor):
    t = Tela(navegador, "cam")
    p = t.page
    try:
        assert p.evaluate("() => fetch('/api/reservas/1').then(r => r.status)") == 403
        assert p.evaluate("() => document.querySelectorAll('.barra-res').length") == 0 and p.locator("#mapa").count() == 1
        assert p.evaluate("() => document.getElementById('dlgResumo').open") is False
    finally:
        t.fechar()


def test_xss_no_nome_e_nas_observacoes_vira_texto(admin):
    p = admin.page
    abrir_pelo_mapa(p, 5)
    assert "onerror" in p.inner_text("#rcTit") + p.inner_text("#rcCartao") and p.locator("#dlgResumo img").count() == 0
    assert "<b>negrito</b>" in p.inner_text("#rcPainel") and p.locator("#dlgResumo b").count() == 0
    assert p.evaluate("() => window.__xss") is None


def test_despesas_do_resumo_abre_o_dialogo_e_atualiza_o_total(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    assert "Lançamentos" in p.inner_text("#rcCartao")
    p.click('#rcCartao [data-rc="despesas"]')
    p.wait_for_selector("#dlgDesp[open]")
    p.check("#dsAvulso")
    p.fill("#dsDesc", "Suco de laranja")
    p.fill("#dsValor", "12,50")
    p.click("#dsLancar")
    p.wait_for_selector("#dsLista tr")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgDesp').open")
    assert p.evaluate("() => document.getElementById('dlgResumo').open") is True
    p.wait_for_selector("#rcCartao .rc-subtotais dd:text-is('R$ 12,50')")
    assert p.evaluate("() => document.activeElement.dataset.rc") == "despesas"
    p.click('#rcCartao [data-rc="despesas"]')
    p.wait_for_selector("#dlgDesp[open]")
    p.keyboard.press("Escape")


def test_historico_abre_a_aba_do_formulario(admin):
    p = admin.page
    abrir_pelo_mapa(p, 2)
    p.click('#rcCartao [data-rc="historico"]')
    p.wait_for_selector("#dlg[open]")
    assert p.get_attribute("#abaHistForm", "class").find("ativo") >= 0
    p.wait_for_function("() => { const t = document.getElementById('tabHistForm').innerText; return t.length > 0 && !t.includes('Carregando'); }")
    p.click("#btnFecharHist")
    p.wait_for_selector("#dlgResumo[open]")


def test_faixa_do_resumo_recolhivel_e_lembrada_por_usuario(navegador, servidor):
    t = Tela(navegador, "atend")
    p = t.page
    try:
        abrir_pelo_mapa(p, 2)
        assert p.evaluate("() => document.getElementById('rcFaixa').open") is True
        p.click("#rcFaixa > summary")
        p.wait_for_function("() => prefs.resumo_recolhido === true")
        assert p.locator("#rcCartao").is_hidden()
        p.keyboard.press("Escape")
        p.reload()
        p.wait_for_selector("#mapa .barra-res")
        p.locator('#mapa .barra-res[data-id="2"]').click()                # guardado no servidor: continua recolhida
        p.wait_for_selector(RESUMO)
        assert p.evaluate("() => document.getElementById('rcFaixa').open") is False
        p.click("#rcFaixa > summary")
        p.wait_for_function("() => prefs.resumo_recolhido === false")
        assert p.locator("#rcCartao").is_visible()
    finally:
        t.fechar()


def test_celular_390_resumo_em_tela_cheia_com_esc_e_foco(navegador, servidor):
    t = Tela(navegador, "admin", 390, 844)
    p = t.page
    try:
        p.click('nav button[data-aba="buscar"]')
        p.fill("#busca", "Ana")
        p.click("#resultados .item-busca")
        p.wait_for_selector(RESUMO)
        c = p.locator("#dlgResumo").bounding_box()
        assert c["width"] >= 388 and c["height"] >= 840
        assert p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        for b in p.locator("#dlgResumo button:visible").all():
            box = b.bounding_box()
            if box and b.get_attribute("aria-controls") is None and b.get_attribute("role") != "tab":
                assert box["height"] >= 43, b.inner_text()
        p.keyboard.press("Escape")
        p.wait_for_function("() => !document.getElementById('dlgResumo').open")
        assert p.evaluate("() => document.activeElement.className") == "item-busca" or p.evaluate("() => document.activeElement.tagName") in ("BODY", "DIV")
    finally:
        t.fechar()
