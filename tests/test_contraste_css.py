"""Contraste mínimo (WCAG AA, 4,5:1) das cores de situação do pagamento e dos textos de aviso, nos dois temas.

Lê os valores direto do static/app.css: se alguém clarear uma cor e o texto ficar ilegível, o teste acusa.
"""
import os
import re

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "app.css")
BRANCO, ESCURO = "#ffffff", "#1d2a2c"      # o texto das barras/pílulas: branco, ou escuro nos fundos claros (parcial, pendente)


def _blocos():
    css = open(CSS, encoding="utf-8").read()
    claro = re.search(r":root\{(.*?)\n\}", css, re.S).group(1)
    escuro = re.search(r"prefers-color-scheme: dark\)\{\s*:root\{(.*?)\}", css, re.S).group(1)
    return claro, escuro


def _var(bloco, nome):
    cor = re.search(r"--%s:\s*(#[0-9a-fA-F]{3,6})" % nome, bloco).group(1)
    return cor if len(cor) == 7 else "#" + "".join(c * 2 for c in cor[1:])      # #fff -> #ffffff


def _lum(hexa):
    r, g, b = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_texto_branco_nas_cores_escuras_de_situacao():
    claro, _ = _blocos()
    for nome in ("pago", "pousada", "gratis", "conflito"):
        assert contraste(_var(claro, nome), BRANCO) >= 4.5, nome


def test_texto_escuro_nas_cores_claras_de_situacao():
    claro, _ = _blocos()
    for nome in ("parcial", "pendente"):
        assert contraste(_var(claro, nome), ESCURO) >= 4.5, nome
    css = open(CSS, encoding="utf-8").read()
    assert ".barra-res.parcial,.barra-res.pendente,.pilula.parcial,.pilula.pendente{color:#1d2a2c}" in css


def test_texto_de_aviso_legivel_nos_dois_temas():
    claro, escuro = _blocos()
    assert contraste(_var(claro, "conflito"), _var(claro, "painel")) >= 4.5
    assert contraste(_var(claro, "pago"), _var(claro, "painel")) >= 4.5
    for nome in ("pago-txt", "conflito-txt"):
        for fundo in ("painel", "fundo"):
            assert contraste(_var(escuro, nome), _var(escuro, fundo)) >= 4.5, (nome, fundo)


def test_foco_do_teclado_visivel_no_cabecalho():
    """Regressão: o contorno de foco usava a cor de destaque, igual ao fundo do cabeçalho (foco invisível nos dois temas)."""
    css = open(CSS, encoding="utf-8").read()
    assert "header button:focus-visible" in css and "outline-color:var(--accent-contraste)" in css
    claro, escuro = _blocos()
    for bloco in (claro, escuro):
        assert contraste(_var(bloco, "accent"), _var(bloco, "accent-contraste")) >= 3      # contorno x fundo do cabeçalho (WCAG 1.4.11)
