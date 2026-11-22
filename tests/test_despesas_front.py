"""Despesas (front): lógica pura no node e verificações estáticas (CSP, ordem dos scripts, sem valor nos arquivos da lista)."""
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVOS = ("despesas_logica.js", "despesas_form.js", "despesas.js", "catalogo_logica.js", "catalogo.js", "consumo.js")


def _ler(*p):
    with open(os.path.join(RAIZ, *p), encoding="utf-8") as f:
        return f.read()


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
@pytest.mark.parametrize("arquivo", ["despesas_logica.js", "catalogo_logica.js"])
def test_logica_pura_no_node(arquivo):
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", arquivo)],
                       capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_sem_estilo_nem_evento_inline_nem_eval(nome):
    js = _ler("static", nome)
    assert not re.search(r"style=[\"'\\]", js) and not re.search(r"\son[a-z]+=\s*[\"'\\]", js)
    assert "eval(" not in js and "document.write" not in js and "innerHTML" not in js    # todo texto por textContent


def test_html_do_dialogo_e_ordem_dos_scripts():
    html = _ler("static", "index.html")
    for ident in ("dlgDesp", "dsTit", "dsForm", "dsCat", "dsDesc", "dsQtd", "dsValor", "dsLancar", "dsMsg", "dsEstorno",
                  "dsMotivo", "dsItem", "dsAvulso", "cgLista", "cnTabela", "dlgCat", "dsLista", "dsTotais", "dsImprimir", "dsFechar", "dsFechar2"):
        assert 'id="%s"' % ident in html
    assert re.search(r'id="dsMsg"[^>]*aria-live="polite"', html)
    ordem = [html.index("/static/" + n) for n in ("operacao_notas.js", "despesas_logica.js", "despesas_form.js", "despesas.js")]
    assert ordem == sorted(ordem)
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)


def test_extrato_so_imprime_o_dialogo():
    css = _ler("static", "app.css")
    assert "body.imp-extrato dialog#dlgDesp" in css and "body.imp-extrato{page:retrato}" in css
    # nenhuma regra de impressão das outras folhas menciona o diálogo de despesas
    assert "imp-folha" not in css[css.index("DESPESAS (conta da reserva)"):]


def test_arquivos_da_lista_continuam_sem_valor():
    for nome in ("operacao_acoes.js", "operacao_dia.js", "operacao_dialogos.js", "operacao_notas.js", "operacao_dia_tela.js"):
        js = _ler("static", nome).lower()
        for proibido in ("centavos", "valores.ver", "r$"):
            assert proibido not in js, (nome, proibido)


def test_aba_do_administrador_e_so_dele():
    html = _ler("static", "index.html")
    assert re.search(r'<button data-aba="despesas" data-cap="catalogo.gerir"', html) and 'id="aba-despesas"' in html
    assert html.index("/static/catalogo_logica.js") < html.index("/static/catalogo.js") < html.index("/static/consumo.js")
    css = _ler("static", "app.css")
    assert "body.imp-consumo" in css and "body.imp-extrato #dlgDesp .ds-hora{display:none" in css
