"""E2E (Edge): notas da reserva e do apartamento no diálogo Observações. Porta via POUSADA_E2E_PORTA (5069)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, erros_graves  # noqa: E402

META = re.compile(r"Adicionado por \w+ em \d\d/\d\d/\d{4} \d\d:\d\d")


def abrir_notas(p, apto, cat="ocupados"):
    if p.locator("#mrLista.oculto").count() == 0:
        p.click("#mrListaFechar")
    p.click("#mrResumo .cd-cat-" + cat)
    p.wait_for_selector("#mrLista:not(.oculto)")
    p.click('#mrTabela [data-un="%s"][data-acao="obs"]' % apto)
    p.wait_for_selector("#dlgNotas[open]")
    p.wait_for_selector(".nt-msg:empty")


def anotar(p, texto):
    p.fill(".nt-novo textarea", texto)
    p.click(".nt-add")
    p.wait_for_function("(t) => [...document.querySelectorAll('.nt-nota .nt-texto')].some(e => e.textContent === t)", arg=texto)


def test_adicionar_corrigir_e_ocultar_com_autor_e_data(admin):
    p = admin.page
    abrir_notas(p, "201")
    assert "Nenhuma nota." in p.inner_text("#notasPainel")
    anotar(p, "Cliente chega tarde")
    assert META.search(p.inner_text(".nt-nota .nt-meta")) and "Modificado" not in p.inner_text(".nt-nota .nt-meta")
    assert p.input_value(".nt-novo textarea") == "" and p.evaluate("() => document.activeElement.tagName") == "TEXTAREA"
    p.click(".nt-corrigir")
    assert p.evaluate("() => document.activeElement.value") == "Cliente chega tarde"
    p.fill(".nt-editor textarea", "Cliente chega às 22h")
    p.click(".nt-editor .primario")
    p.wait_for_selector(".nt-meta >> text=Modificado por admin")
    assert "Cliente chega às 22h" in p.inner_text(".nt-nota") and p.evaluate("() => document.activeElement.className") == "nt-corrigir"
    p.click(".nt-ocultar")
    p.fill(".nt-editor input", "ab")
    p.click(".nt-editor .perigo")
    assert "pelo menos 3" in p.inner_text(".nt-msg")                      # motivo curto demais
    p.fill(".nt-editor input", "lançada por engano")
    p.click(".nt-editor .perigo")
    p.wait_for_selector(".nt-nota", state="detached")
    assert "Nenhuma nota." in p.inner_text("#notasPainel")
    p.check(".nt-ver-ocultas input")                                       # o administrador vê as ocultas e as versões anteriores
    p.wait_for_selector(".nt-nota.nt-oculta")
    assert "lançada por engano" in p.inner_text(".nt-nota") and "Versões anteriores (1)" in p.inner_text(".nt-nota")
    assert erros_graves(admin.erros) == []


def test_aviso_de_cartao_e_recusa_do_servidor(admin):
    p = admin.page
    abrir_notas(p, "203", "ins")
    p.fill(".nt-novo textarea", "Cartão 4111 1111 1111 1111")
    assert p.locator(".nt-novo .aviso-cartao").is_visible()
    p.click(".nt-add")
    p.wait_for_selector(".nt-msg.nt-erro")
    assert "número de cartão" in p.inner_text(".nt-msg") and "4111" not in p.inner_text(".nt-msg")
    assert p.locator(".nt-nota").count() == 0 and p.input_value(".nt-novo textarea").startswith("Cartão")      # o texto digitado fica
    p.fill(".nt-novo textarea", "pago no cartão (final 1234)")
    assert not p.locator(".nt-novo .aviso-cartao").is_visible()


def test_xss_na_nota_vira_texto(admin):
    p = admin.page
    abrir_notas(p, "205")
    anotar(p, '<img src=x onerror="window.__xss=1"> <b>negrito</b>')
    assert p.locator("#dlgNotas img").count() == 0 and p.locator("#dlgNotas .nt-texto b").count() == 0
    assert p.evaluate("() => window.__xss") is None


def test_nota_do_apartamento_na_aba_propria(admin):
    p = admin.page
    abrir_notas(p, "202", "ins")
    p.click("#notasAbas [role=tab] >> text=Apartamento")
    p.wait_for_selector(".nt-msg:empty")
    assert "todas as reservas deste apartamento" in p.inner_text("#notasPainel")
    anotar(p, "Ar-condicionado barulhento")
    p.click("#notasFechar")
    abrir_notas(p, "202", "ins")           # outra reserva ou a mesma: a nota persiste no apartamento
    p.click("#notasAbas [role=tab] >> text=Apartamento")
    p.wait_for_selector(".nt-nota")
    assert "Ar-condicionado barulhento" in p.inner_text("#notasPainel")


def test_texto_digitado_sobrevive_ao_polling_e_esc_fecha_so_o_editor(admin):
    p = admin.page
    abrir_notas(p, "201")
    p.fill(".nt-novo textarea", "rascunho em andamento")
    p.wait_for_timeout(9000)                                 # passa mais de um ciclo de 8 s
    assert p.input_value(".nt-novo textarea") == "rascunho em andamento" and p.evaluate("() => document.getElementById('dlgNotas').open")
    p.fill(".nt-novo textarea", "")
    if p.locator(".nt-corrigir").count() == 0:
        anotar(p, "para o teste de Esc")
    p.click(".nt-corrigir >> nth=0")
    p.keyboard.press("Escape")
    assert p.locator(".nt-editor").count() == 0 and p.evaluate("() => document.getElementById('dlgNotas').open")
    p.keyboard.press("Escape")
    assert not p.evaluate("() => document.getElementById('dlgNotas').open")


def test_recepcao_anota_na_reserva_mas_nao_no_apartamento(navegador, servidor):
    t = Tela(navegador, "recep")
    p = t.page
    try:
        abrir_notas(p, "202", "ins")
        assert p.locator(".nt-novo:not(.oculto)").count() == 1          # reserva: pode anotar
        p.click("#notasAbas [role=tab] >> text=Apartamento")
        p.wait_for_selector(".nt-lista")
        p.wait_for_timeout(300)
        assert p.locator(".nt-novo:not(.oculto)").count() == 0 and p.locator(".nt-corrigir").count() == 0   # apartamento: só leitura
        assert p.locator(".nt-ver-ocultas").count() == 0
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()


def test_consulta_e_diretoria_so_leem(admin, navegador, servidor):
    abrir_notas(admin.page, "201")
    if admin.page.locator(".nt-nota:not(.nt-oculta)").count() == 0:
        anotar(admin.page, "nota para leitura")
    for login in ("consulta", "dir"):
        t = Tela(navegador, login)
        p = t.page
        try:
            abrir_notas(p, "201")
            assert p.locator(".nt-novo:not(.oculto)").count() == 0 and p.locator(".nt-corrigir, .nt-ocultar").count() == 0
            assert p.locator(".nt-nota").count() >= 1
            assert erros_graves(t.erros) == []
        finally:
            t.fechar()


def test_correcao_com_versao_antiga_mostra_aviso_e_recarrega_a_lista(admin):
    p = admin.page
    abrir_notas(p, "205")
    anotar(p, "nota que outra pessoa vai corrigir")
    nid = p.get_attribute(".nt-nota >> nth=-1", "data-id")
    p.click(".nt-corrigir >> nth=-1")
    p.evaluate("(id) => api('POST', '/api/notas/' + id + '/corrigir', {texto: 'corrigida por outra pessoa', versao: 1})", nid)
    p.fill(".nt-editor textarea", "minha correção")
    p.click(".nt-editor .primario")
    p.wait_for_selector(".nt-msg.nt-erro")
    assert "alterada por outra pessoa" in p.inner_text(".nt-msg")
    p.wait_for_selector('.nt-nota[data-id="%s"] .nt-texto:text-is("corrigida por outra pessoa")' % nid)
    assert "alterada por outra pessoa" in p.inner_text(".nt-msg")          # o aviso não some com o recarregamento
