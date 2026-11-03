"""Relatório de ocupação (front): lógica pura no node e conferências estáticas (CSP estrita, sem inline, botões e diálogo)."""
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_logica_pura_no_node():
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", "ocupacao_logica.js")], capture_output=True, text=True,
                       timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_index_tem_botoes_dialogo_e_scripts_externos():
    h = _ler("static", "index.html")
    for i in ("mOcupacao", "fOcupacao", "dlgOcupacao", "ocInicio", "ocFim", "ocOrientacao", "ocImprimir", "ocPdf", "ocCancelar", "ocImpressao"):
        assert 'id="%s"' % i in h, i
    for atalho in ("hoje", "semana", "mes", "proximo", "mapa"):
        assert 'data-atalho="%s"' % atalho in h
    assert h.index("ocupacao_logica.js") < h.index("ocupacao.js") and h.index("app.js") < h.index("ocupacao_logica.js")
    assert 'aria-labelledby="ocTit"' in h and "Imprimir relatório de ocupação" in h


def test_sem_script_nem_estilo_inline():
    h = _ler("static", "index.html")
    assert not re.search(r"<script(?![^>]*\bsrc=)", h) and " style=" not in h and not re.search(r"\son\w+=", h)
    for arq in ("ocupacao.js", "ocupacao_logica.js"):
        js = _ler("static", arq)
        assert "eval(" not in js and "document.write" not in js and ".style.cssText" not in js
        assert "outerHTML" not in js


def test_todo_innerhtml_do_relatorio_vem_de_funcao_que_escapa():
    js = _ler("static", "ocupacao.js")
    usos = re.findall(r"innerHTML\s*=\s*([^;]+);", js)
    assert usos == ["ocHtml(rel, emitido)"]
    logica = _ler("static", "ocupacao_logica.js")
    assert "ocEsc(" in logica and logica.count("ocEsc(") >= 15


def test_css_do_relatorio_tem_pagina_e_quebra():
    css = _ler("static", "app.css")
    for trecho in ("body.imp-ocupacao #ocImpressao", "ocup-retrato{page:retrato}", ".oc-pagina{break-after:page", "dialog.oc-dlg", ":not(.imp-ocupacao):not(.imp-fnrh):not(.imp-rcextrato) #aba-camareiras"):
        assert trecho in css, trecho
    assert "style=" not in css
