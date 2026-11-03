"""Hospedagem (etapa 3A), front: CSP estrita nos arquivos novos, ordem dos scripts, ganchos para a etapa 3B e a lógica pura em node."""
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOVOS = ("resumo_itens.js", "resumo_estado.js", "resumo_hospedes.js", "fnrh.js")


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("nome", NOVOS)
def test_arquivos_novos_sem_html_montado_como_texto(nome):
    js = _ler("static", nome)
    assert not re.search(r"style=[\"'\\]", js) and not re.search(r"\son[a-z]+=\s*[\"'\\]", js)
    for proibido in ("innerHTML", "insertAdjacentHTML", "document.write", "eval(", "outerHTML", "toISOString", "localStorage", "sessionStorage"):
        assert proibido not in js, proibido
    assert "<script" not in js and "<img" not in js


def test_html_ordem_dos_scripts_e_ganchos():
    html = _ler("static", "index.html")
    ordem = [html.index("/static/%s" % n) for n in ("resumo_logica.js", "resumo_conta.js", "resumo_itens.js", "fnrh.js", "resumo_acoes.js",
                                                    "resumo_estado.js", "resumo_hospedes.js", "resumo_ligar.js")]
    assert ordem == sorted(ordem)
    for ident in ("fnrhImpressao", "rcContas", "rcContasBtn", "rcContasLista"):
        assert 'id="%s"' % ident in html, ident
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)


def test_mutacoes_do_front_levam_a_versao_e_so_usam_rotas_json():
    estado, hosp = _ler("static", "resumo_estado.js"), _ler("static", "resumo_hospedes.js")
    for rota in ("liberar", "liberar/reverter", "checkin", "checkin/reverter"):
        assert ('rcUrl("%s")' % rota in estado) or ('"%s"' % rota in estado)
    assert "motivo: motivo" in estado and "rcPedirMotivo(" in estado          # liberar, desfazer a liberação e reverter check-in exigem motivo
    assert estado.count("versao: rc.det.versao") >= 2 and "versao: r.versao" in estado and "versao: rcHp.dados.versao" in hosp
    assert "fetch(" not in estado + hosp                     # tudo passa por api(): CSRF e JSON-only em um lugar só


def test_ganchos_da_barra_de_itens_continuam_existindo():
    itens, estado = _ler("static", "resumo_itens.js"), _ler("static", "resumo_estado.js")
    assert "rc.marcados" in itens and "rcItensDaConta" in itens and 'id = "rcBarraItens"' in itens and "function rcConfirmar" in estado
    css = _ler("static", "app.css")
    assert ".rc-az-caixa" in css and ".rc-barra-itens" in css and "body.imp-fnrh" in css


def test_historico_conhece_as_novas_acoes():
    app = _ler("static", "app.js")
    for acao in ("hospedes_alterados", "checkin", "checkin_revertido", "conta_liberada", "conta_reaberta", "placa_alterada"):
        assert re.search(r"\b%s:" % acao, app), acao


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
@pytest.mark.parametrize("script", ("resumo_logica.js", "fnrh.js"))
def test_logica_pura_no_node(script):
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
