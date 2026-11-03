"""Governança: contraste AA (texto 4,5:1; faixa lateral 3:1) das cores de situação nos dois temas, lido do app.css."""
import os
import re

import pytest

from tests.test_contraste_css import _blocos, _lum, _var, contraste

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "app.css")
SITUACOES = ["suja", "arrum", "pronta", "hosp", "aguard", "manut", "interd"]


def _temas():
    css = open(CSS, encoding="utf-8").read()
    secao = css[css.index("Governança (menu"):]
    claro = re.search(r":root\{(.*?)\n\}", secao, re.S).group(1)
    escuro = re.search(r"prefers-color-scheme: dark\)\{\s*:root\{(.*?)\n  \}", secao, re.S).group(1)
    return {"claro": claro, "escuro": escuro}


@pytest.mark.parametrize("tema", ["claro", "escuro"])
@pytest.mark.parametrize("sit", SITUACOES)
def test_texto_da_situacao_tem_contraste_aa(tema, sit):
    b = _temas()[tema]
    assert contraste(_var(b, "gv-%s-fg" % sit), _var(b, "gv-%s-bg" % sit)) >= 4.5


@pytest.mark.parametrize("tema", ["claro", "escuro"])
@pytest.mark.parametrize("sit", SITUACOES)
def test_faixa_lateral_distingue_do_fundo_da_pagina(tema, sit):
    b = _temas()[tema]
    pagina = _blocos()[0 if tema == "claro" else 1]
    assert contraste(_var(b, "gv-" + sit), _var(pagina, "fundo")) >= 3


@pytest.mark.parametrize("tema", ["claro", "escuro"])
def test_selo_atrasada_e_botao_principal(tema):
    b = _temas()[tema]
    assert contraste(_var(b, "gv-suja"), _var(b, "gv-suja-bg")) >= 4.5            # ATRASADA: texto no fundo claro, sobre a cor viva
    pagina = _blocos()[0 if tema == "claro" else 1]
    assert contraste(_var(pagina, "accent"), _var(pagina, "accent-contraste")) >= 4.5   # botão principal do cartão


def test_situacao_nunca_so_cor():
    css = open(CSS, encoding="utf-8").read()
    js = open(os.path.join(os.path.dirname(CSS), "governanca.js"), encoding="utf-8").read()
    assert "gvIcone(i.situacao)" in js and "GV_ROTULO[i.situacao]" in js        # ícone + texto em todo cartão
    assert ".cd-gov::before" in css                                             # Calendário: forma + texto
