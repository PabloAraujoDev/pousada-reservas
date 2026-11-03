"""Resumo da conta: verificações estáticas do front (CSP, sem innerHTML, ordem dos scripts), lógica pura em node e o que o
Resumo busca no servidor, perfil por perfil (quem abre, quem recebe valores, quem nunca vê)."""
import os
import re
import shutil
import subprocess
from datetime import datetime

import pytest

from tests import conftest
from tests.conftest import criar_app_teste

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVOS = ("resumo_logica.js", "resumo_conta.js", "resumo_acoes.js", "resumo_ligar.js")
RES = {"a": "302", "nome": "Antonio Teste", "extras": "Berço", "n": 2, "i": "2026-10-27", "f": "2026-10-29", "p": "parcial",
       "o": "Chega tarde", "grupo": "", "tipo": "socio", "diaria_centavos": 35000}
AGORA = datetime(2026, 10, 28, 9, 0, 0)


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_sem_estilo_evento_inline_nem_innerhtml(nome):
    js = _ler("static", nome)
    assert not re.search(r"style=[\"'\\]", js) and not re.search(r"\son[a-z]+=\s*[\"'\\]", js)
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js and "eval(" not in js
    assert "toISOString" not in js


def test_html_do_resumo_e_ordem_dos_scripts():
    html = _ler("static", "index.html")
    for ident in ("dlgResumo", "rcTit", "rcSit", "rcTotal", "rcMudou", "rcRecarregar", "rcFaixa", "rcCartao", "rcAbas", "rcPainel", "rcHospede",
                  "rcFechar", "rcFechar2", "rcBaseDespesas", "rcBaseImprimir", "rcImpEmitido"):
        assert 'id="%s"' % ident in html, ident
    assert re.search(r'<dialog id="dlgResumo"[^>]*aria-labelledby="rcTit"', html) and re.search(r'id="rcTit"[^>]*tabindex="-1"', html)
    assert re.search(r'<details id="rcFaixa"[^>]*\bopen\b', html) and 'role="tablist"' in html
    ordem = [html.index("/static/%s" % n) for n in ("app.js", "notas_abas.js", "despesas.js", "resumo_logica.js", "resumo_conta.js",
                                                    "resumo_acoes.js", "resumo_ligar.js")]
    assert ordem == sorted(ordem)
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)


def test_app_js_so_ganhou_ganchos_minimos():
    """Clicar numa reserva passa por abrirReserva (resumo_ligar.js); o formulário só abre direto para criar uma reserva nova."""
    app = _ler("static", "app.js")
    assert app.count("abrirReserva(") == 3 and "abrirResumo" not in app
    assert "abrirForm(r)" not in app.replace("function abrirForm(r, padrao)", "")
    assert "abrirForm(null, {a: cel.dataset.apto" in app and "abrirForm(null, {i: inicioMapa})" in app
    assert "abrirReserva(r)" in _ler("static", "calendario_dia.js") and "abrirForm(r)" not in _ler("static", "calendario_dia.js")
    assert len(app.splitlines()) < 1010           # app.js não cresceu além dos ganchos (era 988 linhas)


def test_resumo_nunca_hospeda_o_formulario_de_dinheiro_nas_listas():
    for nome in ("operacao_dia.js", "operacao_dia_tela.js", "operacao_acoes.js"):
        assert "abrirResumo" not in _ler("static", nome)          # as listas continuam sem valores; só o Resumo (por capacidade) os mostra


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_logica_pura_no_node():
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", "resumo_logica.js")], capture_output=True, text=True,
                       timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_arquivos_do_resumo_so_para_quem_esta_logado(tmp_path):
    app = criar_app_teste(tmp_path)
    logado = conftest.cliente_como(app, "consulta")
    for nome in ARQUIVOS:
        assert app.test_client().get("/static/" + nome).status_code in (302, 401)
        assert logado.get("/static/" + nome).status_code == 200


# ---------------------------------------------------------------- o que o Resumo busca, por perfil

@pytest.fixture
def app(tmp_path):
    return criar_app_teste(tmp_path, AGORA=AGORA)


def _cli(app, papel):
    cache = app.__dict__.setdefault("_cl", {})
    if papel not in cache:
        cache[papel] = conftest.cliente_como(app, papel)
    return cache[papel]


def _reserva(app):
    rid = _cli(app, "admin").post("/api/reservas", json=RES).get_json()["id"]
    assert _cli(app, "admin").post("/api/reservas/%d/despesas" % rid, json={"categoria": "bar", "descricao": "Agua", "quantidade": 1,
                                                                            "valor_unit_centavos": 8750, "chave": "chave-resumo-1"}).status_code == 201
    return rid


# papel: (abre o detalhe, vê diária, vê despesas, edita reserva, cancela, histórico da reserva)
MATRIZ = {"admin": (200, True, 200, True, True, 200), "atendente": (200, True, 200, True, True, 200),
          "recepcao": (200, True, 200, False, False, 403), "diretoria": (200, True, 200, False, False, 403),
          "consulta": (200, False, 403, False, False, 403), "camareira": (403, False, 403, False, False, 403)}


@pytest.mark.parametrize("papel", sorted(MATRIZ))
def test_o_que_o_resumo_recebe_por_perfil(app, papel):
    rid = _reserva(app)
    abre, diaria, despesas, edita, cancela, historico = MATRIZ[papel]
    c = _cli(app, papel)
    d = c.get("/api/reservas/%d" % rid)
    assert d.status_code == abre
    if abre == 200:
        assert ("diaria_centavos" in d.get_json()) is diaria
    r = c.get("/api/reservas/%d/despesas" % rid)
    assert r.status_code == despesas
    if despesas == 200:
        t = r.get_json()["totais"]
        assert t["despesas_centavos"] == 8750 and t["estadia_centavos"] == 35000 * 2 + 8750       # 2 noites x 350,00 + 87,50
    else:
        assert "centavos" not in r.get_data(as_text=True)
    assert c.get("/api/reservas/%d/historico" % rid).status_code == historico
    assert c.post("/api/reservas/%d/mover" % rid, json={"versao": 1, "a": "301"}).status_code == (200 if edita else 403)
    assert c.get("/api/reservas/%d/notas" % rid).status_code == (403 if papel == "camareira" else 200)


def test_cancelar_so_quem_pode_e_cancelada_so_quem_ve_canceladas(app):
    rid = _cli(app, "admin").post("/api/reservas", json=dict(RES, a="303")).get_json()["id"]
    for papel in ("recepcao", "diretoria", "consulta", "camareira"):
        assert _cli(app, papel).delete("/api/reservas/%d" % rid, json={"versao": 1, "motivo": "x"}).status_code == 403
    assert _cli(app, "atendente").delete("/api/reservas/%d" % rid, json={"versao": 1, "motivo": "desistiu"}).status_code == 200
    for papel in ("recepcao", "diretoria", "consulta"):
        assert _cli(app, papel).get("/api/reservas/%d" % rid).status_code == 404             # cancelada: o Resumo não abre para eles
    corpo = _cli(app, "atendente").get("/api/reservas/%d" % rid).get_json()
    assert corpo["status"] == "cancelada" and corpo["motivo_cancelamento"] == "desistiu" and corpo["cancelado_por"] == "atendente"
