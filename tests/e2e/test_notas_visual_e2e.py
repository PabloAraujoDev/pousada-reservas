"""E2E (Edge): aparência das notas em claro/escuro, desktop e celular (390 px). Screenshots em POUSADA_E2E_SHOTS."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import Tela, erros_graves  # noqa: E402
from test_notas_e2e import abrir_notas, anotar  # noqa: E402


def foto_dialogo(t, p, nome, seletor="#dlgNotas"):
    if SHOTS:
        p.locator(seletor).screenshot(path=os.path.join(SHOTS, nome + ".png"))


@pytest.mark.parametrize("esquema,largura,altura", [("light", 1400, 1000), ("dark", 1400, 1000), ("light", 390, 844), ("dark", 390, 844)])
def test_dialogo_de_notas(navegador, servidor, esquema, largura, altura):
    t = Tela(navegador, "admin", largura, altura, esquema)
    p = t.page
    try:
        abrir_notas(p, "201")
        anotar(p, "Cliente chega tarde, jantar já combinado.")
        p.wait_for_selector(".nt-msg:empty")
        p.click(".nt-corrigir >> nth=0")
        p.fill(".nt-editor textarea", "Cliente chega às 22h, jantar já combinado.")
        p.click(".nt-editor .primario")
        p.wait_for_selector(".nt-meta >> text=Modificado")
        p.fill(".nt-novo textarea", "Rascunho da próxima nota")
        foto_dialogo(t, p, "notas_%s_%d" % (esquema, largura))
        assert p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert erros_graves(t.erros) == []
    finally:
        t.fechar()
