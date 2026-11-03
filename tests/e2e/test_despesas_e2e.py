"""E2E (Edge): diálogo de Despesas (lançar, estornar, totais, duplo clique, XSS, teclado). Porta 5068."""
from base_despesas import *  # noqa: F401,F403
from base_despesas import (XSS_DESC, abrir_despesas, botao_despesas, erros_graves, lancar_pela_tela, linhas_texto, preencher)


def test_lancar_total_estornar(admin):
    p = admin.page
    abrir_despesas(p, "ocupados", "Ana Silva")
    assert p.inner_text("#dsTit") == "Despesas: Apartamento 201 - Ana Silva"
    assert p.is_visible("#dsVazio") and "Nenhuma despesa lançada." in p.inner_text("#dsVazio")
    assert "Conta aberta" in p.inner_text("#dsSituacao")
    assert "R$ 150,00 x 3 noites = R$ 450,00" in p.inner_text("#dsTotais")      # diária 150,00 x 3 noites (valores.ver)
    preencher(p, "Água 500ml", "2", "8,00", "bar")
    assert p.inner_text("#dsTotalVivo") == "R$ 16,00"
    p.click("#dsLancar")
    p.wait_for_selector("#dsLista tr")
    assert "Lançado: 2 x Água 500ml R$ 8,00." in p.inner_text("#dsMsg")
    assert "Bar / frigobar" in linhas_texto(p)[0] and "R$ 16,00" in linhas_texto(p)[0]
    totais = p.inner_text("#dsTotais").replace("\n", " ")
    assert "Despesas R$ 16,00" in totais and "Total da estadia R$ 466,00" in totais
    assert p.input_value("#dsDesc") == "" and p.input_value("#dsQtd") == "1"
    admin.foto("despesas_01_lancado_claro")
    p.click("#dsLista .ds-estornar")          # estorno: motivo curto é recusado; motivo bom estorna e mantém a linha riscada
    assert p.is_visible("#dsEstorno") and p.evaluate("() => document.activeElement.id") == "dsMotivo"
    p.fill("#dsMotivo", "erro")
    p.press("#dsMotivo", "Enter")
    assert "pelo menos 5" in p.inner_text("#dsMsg") and p.is_visible("#dsEstorno")
    p.fill("#dsMotivo", "digitado errado")
    p.press("#dsMotivo", "Enter")
    p.wait_for_function("() => document.querySelectorAll('#dsLista tr').length === 2")
    assert not p.is_visible("#dsEstorno")
    assert p.locator("#dsLista tr.ds-s-estornado").count() == 1 and p.locator("#dsLista tr.ds-s-estorno").count() == 1
    assert "Estornado por admin" in p.inner_text("#dsLista") and "digitado errado" in p.inner_text("#dsLista")
    assert "Despesas R$ 0,00" in p.inner_text("#dsTotais").replace("\n", " ")
    assert p.locator("#dsLista .ds-estornar").count() == 0
    admin.foto("despesas_02_estornado_claro")
    assert erros_graves(admin.erros) == []


def test_ponto_no_botao_so_com_saldo(admin):
    p = admin.page
    abrir_despesas(p, "ocupados", "Ana Silva")
    lancar_pela_tela(p, "Suco de laranja", "1", "12,50")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.querySelector('#dlgDesp[open]')")
    p.wait_for_function("() => document.querySelector('button.od-acao-despesas .od-ponto') !== null")
    assert p.evaluate("() => document.activeElement.className").startswith("od-acao")      # foco volta ao botão de origem
    assert "(há lançamentos)" in botao_despesas(p, "Ana Silva").get_attribute("aria-label")
    assert erros_graves(admin.erros) == []


def test_duplo_clique_cria_um_so(admin):
    p = admin.page
    abrir_despesas(p, "ocupados", "img src=x")
    preencher(p, "Cafe duplo", "1", "5,00")
    p.evaluate("() => { const b = document.getElementById('dsLancar'); b.click(); b.click(); }")
    p.wait_for_selector("#dsLista tr")
    p.wait_for_timeout(800)
    assert p.locator("#dsLista tr").count() == 1
    r = p.evaluate("""() => { const u = '/api/reservas/' + ds.rid + '/despesas';
        const c = {categoria: 'bar', descricao: 'Chave igual', quantidade: 1, valor_unit_centavos: 700, chave: 'chave-e2e-0001'};
        return Promise.all([api('POST', u, c), api('POST', u, c)]).then(x => x.map(y => y.status).sort()); }""")
    assert r == [200, 201]
    p.wait_for_function("() => document.querySelectorAll('#dsLista tr').length === 2", timeout=12000)     # a atualização de 8 s traz a linha
    assert erros_graves(admin.erros) == []


def test_descricao_com_html_vira_texto(admin):
    p = admin.page
    abrir_despesas(p, "outs", "Carla")
    lancar_pela_tela(p, XSS_DESC, "1", "3,00")
    assert XSS_DESC in p.inner_text("#dsLista")
    assert p.evaluate("() => window.__xss") is None and p.locator("#dsLista img").count() == 0
    assert erros_graves(admin.erros) == []


def test_validacoes_na_tela_e_cartao(admin):
    p = admin.page
    abrir_despesas(p, "ins", "Davi")
    for desc, qtd, valor, trecho in [("a", "1", "5", "descrição"), ("Suco", "0", "5", "quantidade"), ("Suco", "1", "", "valor"),
                                     ("Suco", "1", "10.000,01", "máximo")]:
        preencher(p, desc, qtd, valor)
        p.click("#dsLancar")
        assert trecho in p.inner_text("#dsMsg").lower(), trecho
    assert p.locator("#dsLista tr").count() == 0
    preencher(p, "cartao 4111 1111 1111 1111", "1", "5")
    assert p.is_visible("#dsAvisoCartao")
    p.click("#dsLancar")
    p.wait_for_function("() => document.getElementById('dsMsg').textContent.includes('cartão')")
    assert "4111" not in p.inner_text("#dsMsg") and p.locator("#dsLista tr").count() == 0
    assert erros_graves(admin.erros) == []


def test_esc_fecha_confirmacao_primeiro(admin):
    p = admin.page
    abrir_despesas(p, "ins", "Davi")
    lancar_pela_tela(p, "Item de teclado", "1", "4,00")
    p.click("#dsLista .ds-estornar")
    p.keyboard.press("Escape")
    assert not p.is_visible("#dsEstorno") and p.is_visible("#dlgDesp")
    assert p.evaluate("() => document.activeElement.classList.contains('ds-estornar')")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.querySelector('#dlgDesp[open]')")
    assert erros_graves(admin.erros) == []
