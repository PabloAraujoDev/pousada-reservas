"""E2E (Edge via Playwright): relatório de ocupação com período escolhido (diálogo, impressão, PDF, celular 390 px, tema escuro). Porta 5091.

Só roda com POUSADA_E2E=1. Sobe uma instância PRÓPRIA (banco/instância/backup em pasta temporária); nunca toca no banco real.
Não depende da hora do dia (o relatório usa só datas). Screenshots em POUSADA_E2E_SHOTS (se definida).
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, timedelta

import pytest

if not os.environ.get("POUSADA_E2E"):
    pytest.skip("E2E desligado (defina POUSADA_E2E=1)", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
PORTA = int(os.environ.get("POUSADA_E2E_PORTA_OCUP", "5091"))
URL = "http://127.0.0.1:%d" % PORTA
SENHA = "senha-e2e-segura-123"
HOJE = date.today()
SHOTS = os.environ.get("POUSADA_E2E_SHOTS")
XSS = '<img src=x onerror="window.__xss=1">'
PERFIS = (("admin", "admin"), ("cam", "camareira"), ("consulta", "consulta"), ("recep", "recepcao"), ("atend", "atendente"), ("dir", "diretoria"))
# (apto, nome, entrada, saída, pessoas, grupo, status): relativo a hoje
SEMENTE = [("201", "Ana Silva", -2, 3, 2, "", "ativa"), ("202", "Bruno Lima", 0, 3, 2, "Turma Azul", "ativa"),
           ("203", "Carla Souza", -3, 0, 2, "", "ativa"), ("203", "Davi Rocha", 0, 2, 4, "", "ativa"),
           ("205", XSS, -1, 2, 3, "", "ativa"), ("Chalé A", "José Pereira", 5, 7, 2, "", "ativa"),
           ("301", "Cancelada Nunca", 0, 4, 2, "", "cancelada"), ("302", "Longa Estadia", -40, 60, 2, "", "ativa")]


def dia(n):
    return (HOJE + timedelta(days=n)).isoformat()


def br(iso):
    return "%s/%s/%s" % (iso[8:], iso[5:7], iso[:4])


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("e2e_ocup")
    env = dict(os.environ, POUSADA_DB=str(pasta / "e2e.db"), POUSADA_INSTANCIA=str(pasta / "inst"),
               POUSADA_BACKUP_DIR=str(pasta / "bk"), POUSADA_PORTA=str(PORTA), POUSADA_HOST="127.0.0.1")
    from pousada import config
    from pousada.db import conectar, iniciar_banco
    from pousada.regras import agora
    from pousada.usuarios import criar_usuario
    iniciar_banco(env["POUSADA_DB"], config.PASTA_MIGRACOES)
    con = conectar(env["POUSADA_DB"])
    for login, papel in PERFIS:
        criar_usuario(con, login, login.capitalize(), SENHA, papel)
    for a, nome, i, f, n, grupo, status in SEMENTE:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,status,diaria_centavos) "
                    "VALUES (?,?,'',?,?,?,'pendente','',?,?,?,1,?,15000)", (a, nome, n, dia(i), dia(f), grupo, agora(), agora(), status))
    con.close()
    proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, "app.py")], env=env, cwd=RAIZ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + "/login", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("servidor E2E não subiu")
    yield env
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def navegador(servidor):
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        yield b
        b.close()


class Tela:
    def __init__(self, navegador, login, largura=1400, altura=1000, esquema="light"):
        self.ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=esquema, accept_downloads=True)
        self.page = self.ctx.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.erros.append("pageerror: %s" % e))
        self.page.goto(URL + "/login")
        self.page.fill("#login", login)
        self.page.fill("#senha", SENHA)
        self.page.click("#btnEntrar")
        self.page.wait_for_function("() => document.getElementById('quem') && document.getElementById('quem').textContent !== '' && "
                                    "document.querySelector('.aba.ativa') !== null")
        self.page.wait_for_timeout(400)
        # window.print() fica trancado em teste: o stub guarda o que seria impresso (o conteúdo, as classes do body, se há <img>)
        self.page.evaluate("""() => { window.print = () => { window.__imp = {html: document.getElementById('ocImpressao').innerHTML,
            classes: document.body.className, imgs: document.querySelectorAll('#ocImpressao img').length,
            paginas: document.querySelectorAll('#ocImpressao .oc-pagina').length, texto: document.getElementById('ocImpressao').textContent,
            totais: [...document.querySelectorAll('#ocImpressao .oc-tot')].map(tr => [...tr.children].map(c => c.textContent))}; }; }""")

    def abrir_dialogo(self, botao="#mOcupacao"):
        self.page.click(botao)
        self.page.wait_for_selector("#dlgOcupacao[open]")

    def preencher(self, ini, fim):
        self.page.fill("#ocInicio", ini)
        self.page.fill("#ocFim", fim)

    def fechar(self):
        self.ctx.close()


def graves(erros):
    return [e for e in erros if "Content Security Policy" in e or "pageerror" in e or "Refused" in e]


@pytest.fixture
def admin(servidor, navegador):
    t = Tela(navegador, "admin")
    yield t
    t.fechar()


def pdf_de_impressao(page, html, papel):
    """Renderiza o HTML que seria impresso com o CSS de impressão e devolve (bytes do PDF, nº de páginas)."""
    page.evaluate("(h) => { document.getElementById('ocImpressao').innerHTML = h; }", html)
    page.evaluate("(p) => document.body.classList.add('imp-ocupacao', 'ocup-' + p)", papel)
    page.emulate_media(media="print")
    pdf = page.pdf(prefer_css_page_size=True, print_background=True)
    page.emulate_media(media="screen")
    if SHOTS:
        with open(os.path.join(SHOTS, "ocupacao_impresso_%s.pdf" % papel), "wb") as f:
            f.write(pdf)
    page.evaluate("() => { document.body.classList.remove('imp-ocupacao', 'ocup-paisagem', 'ocup-retrato'); document.getElementById('ocImpressao').textContent = ''; }")
    return pdf, len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


def tamanho_pagina(pdf):
    m = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", pdf)
    return float(m.group(1)), float(m.group(2))


def test_dialogo_abre_com_o_periodo_do_mapa_e_atalhos(admin):
    p = admin.page
    esperado_ini = p.evaluate("inicioMapa")
    assert p.is_visible("#mOcupacao") and p.inner_text("#mOcupacao") == "Imprimir relatório de ocupação"
    admin.abrir_dialogo()
    assert p.input_value("#ocInicio") == esperado_ini == dia(0)
    assert p.input_value("#ocFim") == dia(13) and "14 dias" in p.inner_text("#ocInfo")
    assert p.evaluate("document.activeElement.id") == "ocTit" and p.input_value("#ocOrientacao") == "paisagem"
    p.click('[data-atalho="hoje"]')
    assert (p.input_value("#ocInicio"), p.input_value("#ocFim")) == (dia(0), dia(0)) and "1 dia" in p.inner_text("#ocInfo")
    p.click('[data-atalho="semana"]')
    seg = HOJE - timedelta(days=HOJE.weekday())
    assert (p.input_value("#ocInicio"), p.input_value("#ocFim")) == (seg.isoformat(), (seg + timedelta(days=6)).isoformat())
    p.click('[data-atalho="mes"]')
    assert p.input_value("#ocInicio") == HOJE.replace(day=1).isoformat()
    p.click('[data-atalho="proximo"]')
    prox = (HOJE.replace(day=28) + timedelta(days=4)).replace(day=1)
    assert p.input_value("#ocInicio") == prox.isoformat()
    p.click('[data-atalho="mapa"]')
    assert (p.input_value("#ocInicio"), p.input_value("#ocFim")) == (dia(0), dia(13))
    p.click("#ocCancelar")
    assert not p.is_visible("#dlgOcupacao") and p.evaluate("document.activeElement.id") == "mOcupacao"
    assert graves(admin.erros) == []


def test_validacao_no_dialogo(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.preencher(dia(0), dia(92))                        # 93 dias
    assert "máximo de 92" in p.inner_text("#ocMsg") and p.is_disabled("#ocImprimir") and p.is_disabled("#ocPdf")
    admin.preencher(dia(0), dia(91))                        # 92 dias
    assert p.inner_text("#ocMsg") == "" and not p.is_disabled("#ocImprimir")
    admin.preencher(dia(5), dia(1))
    assert "igual ou depois" in p.inner_text("#ocMsg") and p.is_disabled("#ocPdf")
    p.fill("#ocFim", "")
    assert "Informe as duas datas" in p.inner_text("#ocMsg") and p.get_attribute("#ocFim", "aria-invalid") == "true"
    admin.preencher(dia(0), dia(0))
    assert p.inner_text("#ocMsg") == "" and not p.is_disabled("#ocPdf")


def test_imprimir_um_dia_conteudo_e_totais(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.preencher(dia(0), dia(0))
    p.click("#ocImprimir")
    p.wait_for_function("() => window.__imp !== undefined")
    imp = p.evaluate("window.__imp")
    assert "imp-ocupacao" in imp["classes"] and "ocup-paisagem" in imp["classes"] and imp["paginas"] == 1
    t = imp["texto"]
    assert "Pousada Boa Esperança" in t and "Relatório de ocupação - %s a %s" % (br(dia(0)), br(dia(0))) in t
    assert re.search(r"Emitido em \d\d/\d\d/\d{4} \d\d:\d\d por Admin", t)
    assert "Ana Silva" in t and "Turma Azul" in t and "Bruno Lima" not in t           # o grupo aparece no lugar do nome
    assert "Cancelada Nunca" not in t and "Interditada" in t and "Legenda" in t and "Resumo do período" in t
    linhas = {l[0]: l[1:] for l in imp["totais"]}
    assert linhas["Ocupadas"] == ["5"] and linhas["Livres"] == ["19"] and linhas["Ocupação %"] == ["20,8%"]
    assert linhas["Check-ins"] == ["2"] and linhas["Check-outs"] == ["1"] and linhas["Pessoas"] == ["13"]
    assert "ocupação média 20,8%" in t and "pico 5 unidades (20,8%)" in t
    assert p.evaluate("document.body.className") .count("imp-ocupacao") == 0                       # depois de imprimir, tudo volta
    assert p.evaluate("document.getElementById('ocImpressao').textContent") == "" and not p.is_visible("#dlgOcupacao")
    assert graves(admin.erros) == []


def test_xss_no_nome_nao_executa_na_impressao(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.preencher(dia(-1), dia(1))
    p.click("#ocImprimir")
    p.wait_for_function("() => window.__imp !== undefined")
    imp = p.evaluate("window.__imp")
    assert imp["imgs"] == 0 and p.evaluate("window.__xss") is None
    assert "<img src=x" in imp["texto"] and "&lt;img src=x" in imp["html"]
    assert graves(admin.erros) == []


def test_layout_impresso_paginas_e_orientacao(admin):
    p = admin.page
    for papel, dias, paginas in (("paisagem", 30, 3), ("retrato", 30, 5), ("paisagem", 14, 1), ("retrato", 7, 1)):
        admin.abrir_dialogo()
        admin.preencher(dia(0), dia(dias - 1))
        p.select_option("#ocOrientacao", papel)
        p.evaluate("window.__imp = undefined")
        p.click("#ocImprimir")
        p.wait_for_function("() => window.__imp !== undefined")
        imp = p.evaluate("window.__imp")
        assert imp["paginas"] == paginas
        pdf, n = pdf_de_impressao(p, imp["html"], papel)
        assert n == paginas, (papel, dias, n)
        larg, alt = tamanho_pagina(pdf)
        assert (larg > alt) == (papel == "paisagem")


def test_baixar_pdf_tem_paginas_e_nome(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.preencher(dia(0), dia(29))
    with p.expect_download() as d:
        p.click("#ocPdf")
    arq = d.value
    assert arq.suggested_filename == "ocupacao_%s_a_%s.pdf" % (dia(0), dia(29))
    dados = open(arq.path(), "rb").read()
    assert dados.startswith(b"%PDF") and len(re.findall(rb"/Type\s*/Page\b(?!s)", dados)) == 3          # 30 dias em paisagem = 3 páginas
    p.wait_for_function("() => !document.getElementById('dlgOcupacao').open")
    admin.abrir_dialogo()
    admin.preencher(dia(0), dia(29))
    p.select_option("#ocOrientacao", "retrato")
    with p.expect_download() as d2:
        p.click("#ocPdf")
    assert len(re.findall(rb"/Type\s*/Page\b(?!s)", open(d2.value.path(), "rb").read())) == 5            # 30 dias em retrato = 5 páginas


def test_erro_do_servidor_aparece_no_dialogo_sem_travar(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.preencher(dia(0), dia(3))
    p.route("**/api/ocupacao?*", lambda rota: rota.fulfill(status=500, content_type="application/json", body='{"erro":"Falha de teste"}'))
    p.click("#ocImprimir")
    p.wait_for_function("() => document.getElementById('ocMsg').textContent.length > 0")
    assert "Falha de teste" in p.inner_text("#ocMsg") and p.evaluate("window.__imp") is None
    assert not p.is_disabled("#ocImprimir") and p.is_visible("#dlgOcupacao")


def test_folha_da_semana_abre_com_a_semana(servidor, navegador):
    t = Tela(navegador, "consulta")
    try:
        t.page.click('nav button[data-aba="folha"]')
        t.abrir_dialogo("#fOcupacao")
        ini = t.page.evaluate("inicioFolha")
        assert t.page.input_value("#ocInicio") == ini and t.page.input_value("#ocFim") == (date.fromisoformat(ini) + timedelta(days=6)).isoformat()
        assert "7 dias" in t.page.inner_text("#ocInfo")
        t.page.click("#ocImprimir")
        t.page.wait_for_function("() => window.__imp !== undefined")
        assert t.page.evaluate("window.__imp.paginas") == 1
    finally:
        t.fechar()


@pytest.mark.parametrize("login,papel", PERFIS)
def test_matriz_de_perfis_na_tela_e_na_api(servidor, navegador, login, papel):
    t = Tela(navegador, login)
    try:
        p = t.page
        pode_mapa = papel != "camareira"
        assert p.is_visible("#mOcupacao") == pode_mapa                         # a camareira nem vê o Mapa
        r = p.evaluate("""async (u) => { const r = await fetch(u, {credentials: 'same-origin'}); return {s: r.status, c: r.headers.get('cache-control'),
            t: await r.text()}; }""", "/api/ocupacao?inicio=%s&fim=%s" % (dia(0), dia(1)))
        assert r["s"] == 200 and r["c"] == "no-store"
        assert ("Turma Azul" in r["t"]) == (papel != "camareira") and "15000" not in r["t"] and "diaria" not in r["t"]
        if pode_mapa:
            t.abrir_dialogo()
            p.click("#ocImprimir")
            p.wait_for_function("() => window.__imp !== undefined")
            assert p.evaluate("window.__imp.html").count("Turma Azul") == 1
        assert graves(t.erros) == []
    finally:
        t.fechar()


def test_celular_390_dialogo_cabe_e_botoes_grandes(servidor, navegador):
    t = Tela(navegador, "admin", largura=390, altura=844)
    try:
        p = t.page
        t.abrir_dialogo()
        cx = p.evaluate("""() => { const d = document.getElementById('dlgOcupacao').getBoundingClientRect();
            return {l: d.left, r: d.right, w: d.width, h: d.height, rolagem: document.documentElement.scrollWidth,
            menores: [...document.querySelectorAll('#dlgOcupacao button, #dlgOcupacao input, #dlgOcupacao select')].filter(e => e.getBoundingClientRect().height < 43).map(e => e.id || e.textContent)}; }""")
        assert cx["w"] <= 390 and cx["l"] >= 0 and cx["r"] <= 390 and cx["rolagem"] <= 390 and cx["menores"] == []
        for alvo in ("#ocImprimir", "#ocPdf", "#ocCancelar", '[data-atalho="mapa"]'):
            assert p.is_visible(alvo)
        if SHOTS:
            p.screenshot(path=os.path.join(SHOTS, "ocupacao_celular.png"))
        p.click("#ocImprimir")
        p.wait_for_function("() => window.__imp !== undefined")
        assert p.evaluate("document.documentElement.scrollWidth") <= 390
        assert graves(t.erros) == []
    finally:
        t.fechar()


def contraste(rgb1, rgb2):
    def lum(c):
        c = [v / 255 for v in c]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = sorted((lum(rgb1), lum(rgb2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def test_tema_escuro_dialogo_legivel(servidor, navegador):
    t = Tela(navegador, "admin", esquema="dark")
    try:
        p = t.page
        t.abrir_dialogo()
        cores = p.evaluate(r"""() => { const num = (s) => s.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number);
            const f = (id, prop) => num(getComputedStyle(document.getElementById(id) || document.querySelector(id))[prop]);
            return {fundo: f('dlgOcupacao', 'backgroundColor'), texto: f('ocTit', 'color'), campo: f('ocInicio', 'color'), campoFundo: f('ocInicio', 'backgroundColor'),
              botao: f('ocCancelar', 'color'), botaoFundo: f('ocCancelar', 'backgroundColor'), prim: f('ocImprimir', 'color'), primFundo: f('ocImprimir', 'backgroundColor')}; }""")
        assert sum(cores["fundo"]) < 300, cores                                   # fundo realmente escuro
        for texto, fundo in (("texto", "fundo"), ("campo", "campoFundo"), ("botao", "botaoFundo"), ("prim", "primFundo")):
            assert contraste(cores[texto], cores[fundo]) >= 4.5, (texto, cores)
        if SHOTS:
            p.screenshot(path=os.path.join(SHOTS, "ocupacao_escuro.png"))
    finally:
        t.fechar()
