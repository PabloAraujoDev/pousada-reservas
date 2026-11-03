"""QA final: toda ação que o servidor grava no histórico tem rótulo em português na tela (nada de 'nota_adicionada' cru)."""
import glob
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def acoes_do_servidor():
    achadas = set()
    for f in glob.glob(os.path.join(RAIZ, "pousada", "*.py")):
        txt = open(f, encoding="utf-8").read()
        achadas |= set(re.findall(r'registrar\(con, "([a-z_]+)"', txt))
    txt = open(os.path.join(RAIZ, "pousada", "rotas_notas.py"), encoding="utf-8").read()
    achadas |= set(re.findall(r'"(nota_[a-z]+)"', txt))
    txt = open(os.path.join(RAIZ, "pousada", "rotas_despesas.py"), encoding="utf-8").read()
    achadas |= set(re.findall(r'"(despesa_[a-z]+)"', txt))
    txt = open(os.path.join(RAIZ, "pousada", "rotas_governanca.py"), encoding="utf-8").read()
    achadas |= {"manutencao_abrir", "manutencao_fechar"}
    return achadas


def test_todas_as_acoes_do_historico_tem_rotulo_na_tela():
    js = open(os.path.join(RAIZ, "static", "app.js"), encoding="utf-8").read()
    bloco = js[js.index("var ROTULO_ACAO"):js.index("var ORDEM_CAMPO")]
    sem_rotulo = sorted(a for a in acoes_do_servidor() if not re.search(r"\b%s:" % a, bloco))
    assert sem_rotulo == [], "faltam rótulos em ROTULO_ACAO (static/app.js): %s" % sem_rotulo


def test_campos_do_historico_das_despesas_e_governanca_tem_rotulo():
    js = open(os.path.join(RAIZ, "static", "app.js"), encoding="utf-8").read()
    bloco = js[js.index("var ROTULO_CAMPO"):js.index("var ORDEM_CAMPO")]
    for campo in ("categoria", "itens", "situacao"):
        assert re.search(r"\b%s:" % campo, bloco), campo
