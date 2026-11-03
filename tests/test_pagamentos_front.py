"""Etapa 3B, front: CSP estrita, ordem dos scripts, lógica pura em node, ausência de campo de cartão e envio de versão/chave."""
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOVOS = ("resumo_pag_logica.js", "resumo_barra.js", "resumo_pagamento.js", "resumo_estornar.js")


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("nome", NOVOS)
def test_arquivos_novos_sem_html_montado_como_texto(nome):
    js = _ler("static", nome)
    assert not re.search(r"style=[\"'\\]", js) and not re.search(r"\son[a-z]+=\s*[\"'\\]", js)
    for proibido in ("innerHTML", "insertAdjacentHTML", "document.write", "eval(", "outerHTML", "toISOString", "localStorage", "sessionStorage"):
        assert proibido not in js, proibido
    assert len(js.splitlines()) <= 150


def test_html_ordem_dos_scripts_e_area_do_extrato():
    html = _ler("static", "index.html")
    ordem = [html.index("/static/%s" % n) for n in ("resumo_logica.js", "resumo_itens.js", "resumo_estado.js", "resumo_pag_logica.js",
                                                    "resumo_barra.js", "resumo_pagamento.js", "resumo_estornar.js", "resumo_ligar.js")]
    assert ordem == sorted(ordem) and 'id="rcExtratoImp"' in html
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)


def test_nunca_existe_campo_de_numero_de_cartao():
    js = _ler("static", "resumo_pagamento.js") + _ler("static", "resumo_pag_logica.js")
    for proibido in ("cvv", "cvc", "validade", "numero_cartao", "pan\"", "card_number"):
        assert proibido not in js.lower(), proibido
    assert "Nunca digite o número do cartão" in js and "ctContemNumeroCartao" in js


def test_mutacoes_levam_versao_chave_e_motivo():
    pag, est, barra = _ler("static", "resumo_pagamento.js"), _ler("static", "resumo_estornar.js"), _ler("static", "resumo_barra.js")
    assert "conta_versao: rc.conta.versao" in pag and "chave: chave" in pag and 'rcUrl("pagamentos")' in pag
    assert "conta_versao: rc.conta.versao" in est and "chave: chave" in est and 'rcUrl("transferir")' in est
    assert "/estorno" in est and "motivo" in est and "rcPedirMotivo(" in est and 'rcUrl("diaria/zerar")' in est
    assert "conta_versao: rc.conta.versao" in barra and "motivo: motivo" in barra


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_logica_pura_no_node():
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", "resumo_pag_logica.js")], capture_output=True, text=True,
                       timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
