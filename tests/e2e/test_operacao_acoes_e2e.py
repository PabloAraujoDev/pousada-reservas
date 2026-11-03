"""E2E (Edge): coluna Ações (Despesas desligado, Informações, Observações) nas listas do Mapa e do Calendário. Porta 5067."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, br, erros_graves  # noqa: E402

LINHAS = "#mrTabela tbody tr.cd-linha"


def abrir(p, cat):
    p.click("#mrResumo .cd-cat-" + cat)
    p.wait_for_selector("#mrLista:not(.oculto)")


def botoes(linha):
    return [b.get_attribute("data-acao") for b in linha.locator("button.od-acao").all()]


def test_admin_ve_despesas_info_e_obs(admin):
    p = admin.page
    abrir(p, "ocupados")
    assert p.locator("#mrTabela thead th").first.inner_text() == "Ações"
    for linha in p.locator(LINHAS).all():
        assert botoes(linha) == ["despesas", "info", "obs"]
    b = p.locator('#mrTabela button.od-acao-info[aria-label*="Ana Silva"]')
    assert b.get_attribute("aria-label") == "Informações do apartamento 201, hóspede Ana Silva"
    assert p.locator("button.od-acao-despesas").count() >= 2         # Despesas ligado: uma por reserva ocupada
    assert erros_graves(admin.erros) == []


def test_vaga_so_tem_info_e_obs_somente_com_texto_da_governanca(admin):
    p = admin.page
    abrir(p, "vagos")
    assert botoes(p.locator(LINHAS, has_text="101").first) == ["info"]
    p.wait_for_timeout(300)
    assert botoes(p.locator(LINHAS, has_text="Chalé B").first) == ["info", "obs"]
    assert p.locator('#mrTabela [data-acao="obs"] .od-ponto').count() == 1          # ponto de "há observação"
    abrir(p, "interditados")
    assert botoes(p.locator(LINHAS).first) == ["info"]


def test_dialogo_informacoes_dados_foco_e_esc(admin):
    p = admin.page
    abrir(p, "ins")
    botao = p.locator('#mrTabela button.od-acao-info[aria-label*="Bruno Lima"]')
    botao.focus()
    botao.click()
    p.wait_for_selector("#dlgInfo[open]")
    assert p.inner_text("#infoTit") == "Apartamento 202 - Bruno Lima"
    assert p.evaluate("() => document.activeElement.id") == "infoTit"
    txt = p.inner_text("#infoLista")
    for esperado in ("Turma Azul", "Convidado", "Parcial", "Entrada %s (14h)" % br(0), "3 noites", "Chegando 14h",
                     "Pronta", "Cadastro não preenchido"):
        assert esperado in txt, esperado
    assert "150" not in txt and "R$" not in txt and "iária" not in txt                            # nunca valor
    p.keyboard.press("Escape")
    assert not p.evaluate("() => document.getElementById('dlgInfo').open")
    assert p.evaluate("() => document.activeElement.dataset.foco") == "acao:info:" + botao.get_attribute("data-rid")   # foco volta ao botão


def test_clicar_no_botao_nao_abre_a_reserva_mas_o_numero_abre(admin):
    p = admin.page
    abrir(p, "ins")
    p.click('#mrTabela button.od-acao-obs[aria-label*="Bruno Lima"]')
    p.wait_for_selector("#dlgNotas[open]")
    assert p.evaluate("() => document.getElementById('dlg').open") is False
    p.click("#notasFechar")
    p.click('#mrTabela .cd-apto-btn[aria-label*="Bruno Lima"]')
    p.wait_for_selector("#dlgResumo[open]")                                     # o número do apto abre o Resumo da reserva
    assert p.evaluate("() => document.getElementById('dlg').open") is False
    p.keyboard.press("Escape")


def test_dialogo_observacoes_abas_teclado_e_edicao(admin):
    p = admin.page
    abrir(p, "ocupados")
    p.click('#mrTabela button.od-acao-obs[aria-label*="Ana Silva"]')
    p.wait_for_selector("#dlgNotas[open]")
    assert p.locator("#notasAbas [role=tab]").all_inner_texts() == ["Reserva", "Arrumação", "Apartamento"]
    painel = p.inner_text("#notasPainel")
    assert "Alergia a amendoim" in painel and "Observação padrão" in painel and "Berço" in painel
    p.focus("#notasAbas [role=tab]")
    p.keyboard.press("ArrowRight")
    assert p.get_attribute("#notasAbas [role=tab]:nth-child(2)", "aria-selected") == "true"
    assert "Última atualização" in p.inner_text("#notasPainel") or "Nenhuma observação" in p.inner_text("#notasPainel")
    p.keyboard.press("ArrowRight")
    assert "Notas do apartamento 201" in p.inner_text("#notasPainel")
    p.keyboard.press("ArrowRight")
    assert p.get_attribute("#notasAbas [role=tab]:nth-child(1)", "aria-selected") == "true"        # volta ao início
    assert "telefone, CPF, cartão" in p.inner_text("#dlgNotas")
    assert p.locator(".nt-editar-padrao").is_visible()
    p.click(".nt-editar-padrao")
    assert p.evaluate("() => document.getElementById('dlg').open") and p.evaluate("() => document.activeElement.id") == "fo"
    assert p.input_value("#fo") == "Alergia a amendoim"
    p.click("#btnCancelar")


def test_observacao_da_vaga_mostra_a_arrumacao(admin):
    p = admin.page
    abrir(p, "vagos")
    p.wait_for_timeout(300)
    p.click('#mrTabela [data-un="Chalé B"][data-acao="obs"]')
    p.wait_for_selector("#dlgNotas[open]")
    assert p.locator("#notasAbas [role=tab]").all_inner_texts() == ["Arrumação", "Apartamento"]
    assert "Ar-condicionado barulhento" in p.inner_text("#notasPainel")
    assert p.locator(".nt-editar-padrao").count() == 0
    p.keyboard.press("Escape")


def test_xss_no_nome_vira_texto_nos_dialogos(admin):
    p = admin.page
    abrir(p, "ocupados")
    p.click('#mrTabela [data-un="205"][data-acao="info"]')
    p.wait_for_selector("#dlgInfo[open]")
    assert "onerror" in p.inner_text("#infoTit") and p.locator("#dlgInfo img").count() == 0
    p.keyboard.press("Escape")
    p.click('#mrTabela [data-un="205"][data-acao="obs"]')
    p.wait_for_selector("#dlgNotas[open]")
    assert "<b>negrito</b>" in p.inner_text("#notasPainel") and p.locator("#dlgNotas b").count() == 0
    assert p.evaluate("() => window.__xss") is None


def test_consulta_so_informacoes_e_observacoes_sem_editar(navegador, servidor):
    t = Tela(navegador, "consulta")
    p = t.page
    try:
        p.click("#mrResumo .cd-cat-ocupados")
        for linha in p.locator(LINHAS).all():
            assert botoes(linha) == ["info", "obs"]
        p.click('#mrTabela [data-un="201"][data-acao="obs"]')
        p.wait_for_selector("#dlgNotas[open]")
        assert p.locator(".nt-editar-padrao").count() == 0 and "Alergia a amendoim" in p.inner_text("#notasPainel")
        p.wait_for_selector(".nt-msg:empty")
        assert p.locator(".nt-novo:not(.oculto)").count() == 0 and p.locator(".nt-corrigir").count() == 0
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()


def test_recepcao_edita_a_observacao_pelo_formulario_restrito(navegador, servidor):
    t = Tela(navegador, "recep")
    p = t.page
    try:
        p.click("#mrResumo .cd-cat-ocupados")
        p.click('#mrTabela [data-un="201"][data-acao="obs"]')
        p.wait_for_selector("#dlgNotas[open]")
        p.click(".nt-editar-padrao")
        assert p.locator("#fo").is_enabled() and p.locator("#fnome").is_disabled()          # só pagamento e observações, como sempre
        p.click("#btnCancelar")
    finally:
        t.fechar()


def test_camareira_nunca_ve_listas_nem_acoes(navegador, servidor):
    t = Tela(navegador, "cam")
    p = t.page
    try:
        assert p.locator("#mrLista").is_hidden() and p.locator("button.od-acao").count() == 0
        assert p.evaluate("() => fetch('/api/reservas/1').then(r => r.status)") == 403
    finally:
        t.fechar()


def test_calendario_tem_a_mesma_coluna(admin):
    p = admin.page
    p.click('nav button[data-aba="calendario"]')
    p.click("#cdResumo .cd-cat-ins")
    assert p.locator("#cdTabela button.od-acao-info").count() == p.locator("#cdTabela tbody tr.cd-linha").count() > 0
    p.click("#cdTabela button.od-acao-info >> nth=0")
    p.wait_for_selector("#dlgInfo[open]")
    p.click("#infoFechar")
    assert p.evaluate("() => document.activeElement.dataset.foco").startswith("acao:info:")
    assert erros_graves(admin.erros) == []


def test_dialogo_aberto_pausa_o_redesenho(admin):
    p = admin.page
    abrir(p, "ins")
    p.click('#mrTabela [data-acao="info"] >> nth=0')
    p.wait_for_selector("#dlgInfo[open]")
    assert p.evaluate("() => algumDialogoAberto()") is True
    p.keyboard.press("Escape")
    assert p.evaluate("() => algumDialogoAberto()") is False
