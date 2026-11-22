"""E2E (Edge): admin cadastra item -> recepção lança por quantidade (sem ver a hora) -> admin vê a hora no relatório. Porta 5068."""
import re

from base_despesas import *  # noqa: F401,F403
from base_despesas import abrir_despesas, com_perfil, erros_graves

HORA = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")


def escolher_item(p, trecho):
    valor = p.evaluate("(t) => [...document.querySelectorAll('#dsItem option')].find(o => o.textContent.includes(t)).value", trecho)
    p.select_option("#dsItem", valor)


def test_fluxo_admin_cadastra_recepcao_lanca_admin_confere_hora(servidor, navegador, admin):
    a = admin.page
    a.click('nav button[data-aba="despesas"]')
    a.wait_for_function("() => document.querySelectorAll('#cgLista tr').length >= 28")
    assert a.locator("#cgLista tr").first.inner_text().startswith("Bebidas")      # ordem alfabética: Bebidas primeiro
    a.click("#cgNovo")
    a.select_option("#cgCategoria", "porcoes")
    a.fill("#cgDescricao", "Pastel E2E")
    a.fill("#cgPreco", "18,00")
    a.click("#cgSalvar")
    a.wait_for_function("() => [...document.querySelectorAll('#cgLista tr')].some(t => t.textContent.includes('Pastel E2E'))")
    assert "R$ 18,00" in a.locator("#cgLista tr", has_text="Pastel E2E").inner_text()

    r = com_perfil(navegador, "recep")
    try:
        p = r.page
        abrir_despesas(p, "ocupados", "Ana Silva")
        p.wait_for_function("() => document.querySelectorAll('#dsItem option').length >= 29")
        assert not p.is_visible("#dsModoRot") and not p.is_visible("#dsValor") and not p.is_visible("#dsDesc")   # sem avulso, sem digitar preço
        escolher_item(p, "Pastel E2E")
        p.fill("#dsQtd", "2")
        assert p.inner_text("#dsTotalVivo") == "R$ 36,00" and p.inner_text("#dsUnitVivo") == "R$ 18,00"
        p.click("#dsLancar")
        p.wait_for_selector("#dsLista tr")
        assert "Lançado: 2 x Pastel E2E R$ 18,00." in p.inner_text("#dsMsg")
        assert "R$ 36,00" in p.inner_text("#dsLista") and p.locator(".ds-hora").count() == 0
        assert not HORA.search(p.inner_text("#dlgDesp"))
        assert not HORA.search(p.content())            # nenhuma hora exata em lugar nenhum da página da recepção
        assert p.locator('nav button[data-aba="despesas"]:visible').count() == 0
        assert erros_graves(r.erros) == []
    finally:
        r.fechar()

    a.click('nav button[data-aba="despesas"]')
    a.click("#cnGerar")
    a.wait_for_function("() => document.querySelectorAll('#cnLista tr').length >= 1")
    linha = a.locator("#cnLista tr", has_text="Pastel E2E")
    texto = linha.inner_text()
    assert HORA.search(texto) and "201" in texto and "Ana Silva" in texto and "recep" in texto and "R$ 36,00" in texto
    assert "Total líquido do período" in a.inner_text("#cnTotal")
    admin.foto("catalogo_relatorio_claro")
    a.click('nav button[data-aba="mapa"]')
    abrir_despesas(a, "ocupados", "Ana Silva")                       # o administrador vê a hora também na conta da reserva
    assert HORA.search(a.inner_text("#dsLista"))
    assert erros_graves(admin.erros) == []
