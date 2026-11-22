"""Ajudantes dos E2E de Despesas (Edge via Playwright, porta 5068 por POUSADA_E2E_PORTA). Reaproveita base_operacao."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5068")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import SHOTS, Tela, erros_graves  # noqa: F401,E402

LINHAS = "#mrTabela tbody tr.cd-linha"
XSS_DESC = '<img src=x onerror="window.__xss=1">'


def abrir_lista(p, cat):
    p.click("#mrResumo .cd-cat-" + cat)
    p.wait_for_selector("#mrLista:not(.oculto)")


def botao_despesas(p, nome):
    return p.locator('#mrTabela button.od-acao-despesas[aria-label*="%s"]' % nome)


def abrir_despesas(p, cat, nome):
    abrir_lista(p, cat)
    botao_despesas(p, nome).click()
    p.wait_for_selector("#dlgDesp[open]")
    p.wait_for_function("() => document.getElementById('dsSituacao').textContent !== ''")


def preencher(p, desc, qtd="1", valor="8,00", cat=None):
    p.check("#dsAvulso")             # lançamento avulso (valor digitado): só o administrador; os demais escolhem o item do catálogo
    if cat:
        p.select_option("#dsCat", cat)
    p.fill("#dsDesc", desc)
    p.fill("#dsQtd", qtd)
    p.fill("#dsValor", valor)


def lancar_pela_tela(p, desc, qtd="1", valor="8,00", cat=None):
    n = p.locator("#dsLista tr").count()
    preencher(p, desc, qtd, valor, cat)
    p.click("#dsLancar")
    p.wait_for_function("n => document.querySelectorAll('#dsLista tr').length > n", arg=n, timeout=8000)


def linhas_texto(p):
    return [t.replace("\n", " ") for t in p.locator("#dsLista tr").all_inner_texts()]
