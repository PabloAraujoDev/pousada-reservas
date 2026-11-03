"""Operação do dia (listas dos cartões, coluna Ações, diálogos): o que dá para conferir sem navegador.

Estático (CSP, esc(), nada de dinheiro nas listas), lógica pura em node e permissões do servidor que os diálogos usam.
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import cliente_como  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVOS_LISTA = ("operacao_dia.js", "operacao_dia_tela.js")             # listas: nunca dinheiro, contato nem texto livre
ARQUIVOS_NOTAS = ("notas_logica.js", "notas_painel.js", "notas_editor.js", "notas_abas.js")
ARQUIVOS_OPERACAO = ARQUIVOS_LISTA + ("operacao_acoes.js", "operacao_dialogos.js", "operacao_notas.js") + ARQUIVOS_NOTAS
_LITERAL = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")
_CONSTRUTOR = re.compile(r"(?:esc|cdHtml\w+|odHtml\w+)\(")


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


def _colapsar(texto):
    """Troca cada esc(...) / cdHtml...(...) / odHtml...(...) (parênteses balanceados) por E: o que está dentro já é protegido."""
    saida, k = "", 0
    while k < len(texto):
        m = _CONSTRUTOR.match(texto, k)
        if not m:
            saida += texto[k]
            k += 1
            continue
        nivel, j = 1, m.end()
        while j < len(texto) and nivel:
            nivel += (texto[j] == "(") - (texto[j] == ")")
            j += 1
        saida += "E"
        k = j
    return saida


@pytest.mark.parametrize("nome", ARQUIVOS_OPERACAO)
def test_nenhum_arquivo_da_operacao_toca_em_valores(nome):
    """Valor da diária e de despesas só entram na PARTE 2, em módulo próprio e por capacidade: aqui não existe nem a palavra."""
    js = _ler("static", nome).lower()
    for proibido in ("centavos", "diaria_", "valores.ver", "r$"):
        assert proibido not in js, proibido


def test_despesas_ligado_com_ponto_de_extensao():
    js = _ler("static", "operacao_acoes.js")
    assert "var OD_DESPESAS_LIGADO = true;" in js and "odAbrirDespesas" in js
    assert "function odAbrirDespesas" in _ler("static", "despesas.js")


def test_html_tem_painel_do_mapa_e_scripts_na_ordem():
    html = _ler("static", "index.html")
    for ident in ("mrLista", "mrListaTit", "mrBusca", "mrTabela", "mrListaFechar", "mrListaImp", "mrListaCal", "cdListaTit", "cdListaResumo"):
        assert 'id="%s"' % ident in html
    assert re.search(r'<section id="mrLista"[^>]*role="region"[^>]*aria-labelledby="mrListaTit"', html)
    assert re.search(r'id="mrListaTit"[^>]*tabindex="-1"', html)
    ordem = [html.index('/static/%s' % n) for n in ("app.js", "calendario_dia.js", "operacao_dia.js", "operacao_acoes.js",
                                                    "operacao_dialogos.js", "operacao_notas.js", "operacao_dia_tela.js")]
    assert html.index("/static/cartao.js") < html.index("/static/notas_painel.js") < html.index("/static/notas_abas.js") < html.index("/static/operacao_notas.js")
    for ident in ("dlgInfo", "dlgNotas", "infoLista", "notasAbas", "notasPainel", "infoAbrir"):
        assert 'id="%s"' % ident in html
    assert ordem == sorted(ordem)
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)


@pytest.mark.parametrize("nome", ARQUIVOS_OPERACAO)
def test_sem_estilo_nem_evento_inline(nome):
    js = _ler("static", nome)
    assert not re.search(r"style=[\"'\\]", js) and not re.search(r"\son[a-z]+=\s*[\"'\\]", js)
    assert "toISOString" not in js and "eval(" not in js and "document.write" not in js


@pytest.mark.parametrize("nome", ARQUIVOS_LISTA)
def test_listas_nao_tocam_em_dinheiro_nem_texto_livre(nome):
    js = _ler("static", nome).lower()
    for proibido in ("diaria", "valor", "telefone", "centavos", "extras", ".o)", "r.o,", "r.o "):
        assert proibido not in js, proibido


@pytest.mark.parametrize("nome", ARQUIVOS_OPERACAO)
def test_todo_html_montado_passa_por_esc(nome):
    """Em cada linha que monta HTML (tag dentro de uma string), todo operando de + é texto fixo, esc()/odHtml*() ou o acumulador h."""
    for n, linha in enumerate(_ler("static", nome).splitlines(), 1):
        if not any(re.search(r"</?[a-z]", lit) for lit in _LITERAL.findall(linha)):
            continue
        s = _colapsar(_LITERAL.sub("S", linha))
        s = re.sub(r"\([^()]*\?\s*[SE]\s*:\s*[SE]\)", "S", s)
        pedacos = re.split(r"(?<![+=])\+(?![+=])", s)
        for k, p in enumerate(pedacos):
            tokens = re.findall(r"[^\s;,(){}=]+", p) or [""]
            token = tokens[-1] if k == 0 else (tokens[0] if k == len(pedacos) - 1 else p.strip())
            if token and len(pedacos) > 1 and token not in ("S", "E", "h"):
                pytest.fail("%s linha %d monta HTML com operando sem esc(): %r em %r" % (nome, n, token, linha.strip()))
    js = _ler("static", nome)
    for m in re.finditer(r"\.innerHTML\s*=\s*([^;]+);", js):
        assert m.group(1).strip() == "html" or m.group(1).startswith(("cdHtml", "odHtml")), m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
@pytest.mark.parametrize("arquivo", ("operacao_logica.js", "notas_logica.js"))
def test_logica_pura_no_node(arquivo):
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", arquivo)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


def test_app_js_tem_a_guarda_unica_de_dialogos():
    js = _ler("static", "app.js")
    assert "function algumDialogoAberto()" in js and 'dialog[open]' in js
    assert '$("dlg").open' not in js and '$("dlg").open' not in _ler("static", "calendario_dia.js")


def test_arquivos_novos_so_para_quem_esta_logado(app):
    for nome in ("operacao_dia.js", "operacao_dia_tela.js", "cartao.js"):
        assert app.test_client().get("/static/" + nome).status_code in (302, 401)
    assert cliente_como(app, "consulta").get("/static/operacao_dia.js").status_code == 200


# ---------------------------------------------------------------- o que os diálogos Informações/Observações recebem, por perfil

RESERVA = {"a": "201", "nome": "Luciana Teste", "extras": "Berço", "n": 2, "i": "2026-11-10", "f": "2026-11-12", "p": "parcial",
           "o": "Chega tarde, ligar 11 98765-4321", "grupo": "Turma A", "tipo": "socio", "diaria_centavos": 35000}


def _criar(app):
    return cliente_como(app, "admin", "criador").post("/api/reservas", json=RESERVA).get_json()["id"]


def test_lista_de_reservas_por_perfil(app):
    _criar(app)
    lista = cliente_como(app, "camareira").get("/api/reservas").get_json()
    assert lista and set(lista[0]) == {"id", "a", "n", "i", "f"}                      # nunca nome, observações, extras, pagamento
    for papel in ("consulta", "recepcao", "diretoria", "atendente", "admin"):
        corpo = cliente_como(app, papel, papel).get("/api/reservas").get_json()
        assert "diaria_centavos" not in corpo[0] and corpo[0]["nome"] == "Luciana Teste", papel   # a lista nunca traz valor


def test_detalhe_que_o_dialogo_de_observacoes_busca(app):
    rid = _criar(app)
    assert cliente_como(app, "camareira").get("/api/reservas/%d" % rid).status_code == 403
    assert app.test_client().get("/api/reservas/%d" % rid).status_code in (401, 302)
    consulta = cliente_como(app, "consulta").get("/api/reservas/%d" % rid).get_json()
    assert consulta["o"].startswith("Chega tarde") and consulta["extras"] == "Berço" and "diaria_centavos" not in consulta
    for papel in ("recepcao", "diretoria", "atendente", "admin"):
        assert cliente_como(app, papel, papel).get("/api/reservas/%d" % rid).status_code == 200, papel


def test_governanca_para_o_dialogo_so_com_dados_permitidos(app):
    rid = _criar(app)
    cam = cliente_como(app, "camareira").get("/api/governanca").get_json()
    item = next(u for u in cam["unidades"] if u["u"] == "201")
    assert "hospede" not in item and "grupo_reserva" not in item and "nome" not in str(item).lower().replace("hospede", "")
    adm = cliente_como(app, "admin", "admin2").get("/api/governanca").get_json()
    assert next(u for u in adm["unidades"] if u["u"] == "201")["versao"] >= 1
    assert rid > 0


def test_perfis_sem_reservas_ver_nao_recebem_a_coluna_acoes():
    """Quem não tem reservas.ver (camareira) não tem as capacidades que o front exige para os botões."""
    from pousada.permissoes import capacidades
    assert "reservas.ver" not in capacidades("camareira")
    for papel in ("admin", "atendente", "recepcao", "diretoria", "consulta"):
        assert "reservas.ver" in capacidades(papel)
    for papel in ("consulta", "camareira"):                 # Despesas (valores): consulta e camareira sem acesso
        assert not any(c.startswith("despesas.") for c in capacidades(papel))
