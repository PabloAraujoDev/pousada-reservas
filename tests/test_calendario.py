"""Menus "Mapa da reserva" (faixa de resumo + disponibilidade) e "Calendário": testes estáticos e da lógica pura (node)."""
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import cliente_como

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as fh:
        return fh.read()


def test_index_tem_os_menus_e_as_secoes():
    html = _ler("static", "index.html")
    assert re.search(r'<button data-aba="mapa"[^>]*data-cap="reservas.ver"[^>]*data-menu="mapa"[^>]*>Mapa da reserva</button>', html) or \
        re.search(r'<button data-aba="mapa"[^>]*>Mapa da reserva</button>', html)
    m = re.search(r'<button data-aba="calendario" data-cap="reservas.ver" data-menu="calendario"[^>]*>Calendário</button>', html)
    assert m
    assert html.index('data-aba="mapa"') < html.index('data-aba="calendario"') < html.index('data-aba="folha"')
    for ident in ("aba-calendario", "aba-mapa", "mrResumo", "cdResumo", "cdTabela", "cdGrade", "cdImprimir", "cdMes", "cdBusca"):
        assert 'id="%s"' % ident in html
    assert '<script src="/static/calendario_dia.js"></script>' in html
    assert html.index("/static/app.js") < html.index("/static/calendario_dia.js")
    assert "painel" not in re.findall(r'data-menu="(\w+)"', html)


def test_html_e_js_sem_estilo_nem_evento_inline():
    html = _ler("static", "index.html")
    assert not re.search(r"\sstyle=", html) and not re.search(r"\son[a-z]+=", html)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    js = _ler("static", "calendario_dia.js")
    assert not re.search(r"style=[\"'\\]", js) and not re.search(r"\son[a-z]+=", js)
    assert "toISOString" not in js and "toISOString" not in _ler("static", "app.js")


def test_js_novo_nao_toca_em_dinheiro_nem_em_dados_sensiveis():
    js = _ler("static", "calendario_dia.js").lower()
    for proibido in ("diaria", "valor", "telefone", "extras", ".o)", "r.o,"):
        assert proibido not in js, proibido


_LITERAL = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")


def _sem_literais(linha):
    return _LITERAL.sub("S", linha)


def _colapsar_chamadas(texto):
    """Troca cada esc(...) / cdHtml...(...) (com parênteses balanceados) por E: o que está dentro já é protegido."""
    saida, k = "", 0
    while k < len(texto):
        m = re.match(r"(?:esc|cdHtml\w+)\(", texto[k:])
        if not m:
            saida += texto[k]
            k += 1
            continue
        nivel, j = 1, k + m.end()
        while j < len(texto) and nivel:
            nivel += (texto[j] == "(") - (texto[j] == ")")
            j += 1
        saida += "E"
        k = j
    return saida


def test_todo_html_montado_no_js_novo_passa_por_esc():
    """Em cada linha que monta HTML (tem uma tag dentro de uma string), todo operando de + é texto fixo (S), esc()/cdHtml*() (E) ou o acumulador h."""
    verificadas = 0
    for n, linha in enumerate(_ler("static", "calendario_dia.js").splitlines(), 1):
        if not any(re.search(r"</?[a-z]", lit) for lit in _LITERAL.findall(linha)):
            continue
        verificadas += 1
        s = _colapsar_chamadas(_sem_literais(linha))
        s = re.sub(r"\([^()]*\?\s*[SE]\s*:\s*[SE]\)", "S", s)           # (cond ? texto : texto)
        pedacos = re.split(r"(?<![+=])\+(?![+=])", s)
        for k, p in enumerate(pedacos):
            tokens = re.findall(r"[^\s;,(){}=]+", p) or [""]
            token = tokens[-1] if k == 0 else (tokens[0] if k == len(pedacos) - 1 else p.strip())
            if token and len(pedacos) > 1 and token not in ("S", "E", "h"):
                pytest.fail("linha %d monta HTML com operando sem esc(): %r em %r" % (n, token, linha.strip()))
    assert verificadas > 20
    js = _ler("static", "calendario_dia.js")
    for m in re.finditer(r"\.innerHTML\s*=\s*([^;]+);", js):
        assert m.group(1).strip() == "html" or m.group(1).startswith("cdHtml"), m.group(0)    # HTML só de cdTrocar ou dos construtores


def test_js_novo_nao_aparece_para_quem_nao_esta_logado(app):
    assert app.test_client().get("/static/calendario_dia.js").status_code in (302, 401)
    assert cliente_como(app, "consulta").get("/static/calendario_dia.js").status_code == 200


def test_camareira_nao_recebe_nomes_pela_lista(app):
    """O painel só usa a lista que já existe: a camareira recebe o resumo (sem nome, tipo, pagamento)."""
    cliente_como(app, "admin").post("/api/reservas", json={"a": "201", "nome": "Fulano", "extras": "", "n": 2, "i": "2026-10-10", "f": "2026-10-12",
                                                          "p": "pendente", "o": "", "grupo": "", "tipo": "socio"})
    lista = cliente_como(app, "camareira").get("/api/reservas").get_json()
    assert lista and all("nome" not in r and "tipo" not in r and "p" not in r for r in lista)
    nomes = cliente_como(app, "consulta").get("/api/reservas").get_json()
    assert all("diaria_centavos" not in r for r in nomes)


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_logica_pura_no_node():
    r = subprocess.run([shutil.which("node"), os.path.join(RAIZ, "tests", "js", "calendario_logica.js")], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")
def test_todos_os_js_passam_no_node_check():
    for nome in os.listdir(os.path.join(RAIZ, "static")):
        if nome.endswith(".js"):
            r = subprocess.run([shutil.which("node"), "--check", os.path.join(RAIZ, "static", nome)], capture_output=True, text=True)
            assert r.returncode == 0, nome + r.stderr
