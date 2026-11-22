"""E2E no navegador real (Edge via Playwright): "Personalizar o sistema" (menus visíveis, aba ao abrir, período do mapa).

Fora da suíte padrão: só roda com  POUSADA_E2E=1 python -m pytest tests/e2e -q  (e se o playwright estiver instalado).
Sobe uma instância PRÓPRIA (porta 5059, banco/backup/instância em pasta temporária); nunca toca no banco real.
Screenshots vão para a pasta indicada em POUSADA_E2E_SHOTS (se definida).
"""
import os
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
PORTA = 5059
URL = "http://127.0.0.1:%d" % PORTA
SENHA = "senha-e2e-segura-123"
HOJE = date.today()
SHOTS = os.environ.get("POUSADA_E2E_SHOTS")


def dia(n):
    return (HOJE + timedelta(days=n)).isoformat()


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("e2e_pref")
    env = dict(os.environ, POUSADA_DB=str(pasta / "e2e.db"), POUSADA_INSTANCIA=str(pasta / "inst"),
               POUSADA_BACKUP_DIR=str(pasta / "bk"), POUSADA_PORTA=str(PORTA), POUSADA_HOST="127.0.0.1")
    from pousada import config
    from pousada.db import conectar, iniciar_banco
    from pousada.regras import agora
    from pousada.usuarios import criar_usuario
    iniciar_banco(env["POUSADA_DB"], config.PASTA_MIGRACOES)
    con = conectar(env["POUSADA_DB"])
    for login, papel in (("admin", "admin"), ("cam", "camareira"), ("consulta", "consulta")):
        criar_usuario(con, login, login.capitalize(), SENHA, papel)
    con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao) "
                "VALUES ('201','Ana Silva','',2,?,?,'pago','','',?,?,1)", (dia(2), dia(5), agora(), agora()))
    con.close()
    proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, "app.py")], env=env, cwd=RAIZ,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


@pytest.fixture(autouse=True)
def preferencias_zeradas(servidor):
    """Cada teste começa com todo mundo no padrão (direto no banco temporário desta instância)."""
    from pousada.db import conectar
    con = conectar(servidor["POUSADA_DB"])
    con.execute("UPDATE usuarios SET preferencias='{}'")
    con.close()


class Tela:
    def __init__(self, navegador, login, largura=1400, altura=1000, esperar=True):
        self.ctx = navegador.new_context(viewport={"width": largura, "height": altura})
        self.page = self.ctx.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.erros.append("pageerror: %s" % e))
        self.page.goto(URL + "/login")
        self.page.fill("#login", login)
        self.page.fill("#senha", SENHA)
        self.page.click("#btnEntrar")
        if esperar:
            self.pronta()

    def pronta(self):
        self.page.wait_for_function("() => document.getElementById('quem') && document.getElementById('quem').textContent !== '' && "
                                    "document.querySelector('.aba.ativa') !== null")
        self.page.wait_for_timeout(500)      # deixa a primeira carga de reservas terminar

    def recarregar(self):
        self.page.reload()
        self.pronta()

    def abrir_dialogo(self):
        self.page.click("#btnPersonalizar")
        self.page.wait_for_selector("#dlgPref[open]")

    def marcar(self, menu, sim):
        self.page.locator('#prefMenus .prefMenu[data-menu="%s"]' % menu).set_checked(sim)

    def salvar(self):
        self.page.click("#prefSalvar")
        self.page.wait_for_selector("#dlgPref", state="hidden")

    def visivel(self, seletor):
        return self.page.locator(seletor).is_visible()

    def aba_ativa(self):
        return self.page.evaluate("() => document.querySelector('.aba.ativa').id")

    def foto(self, nome):
        if SHOTS:
            self.page.screenshot(path=os.path.join(SHOTS, nome + ".png"))

    def fechar(self):
        self.ctx.close()


@pytest.fixture
def admin(servidor, navegador):
    t = Tela(navegador, "admin")
    yield t
    t.fechar()


def erros_graves(erros):
    return [e for e in erros if "Content Security Policy" in e or "pageerror" in e or "Refused" in e]


def test_ocultar_somem_na_hora_persistem_e_restaurar_traz_de_volta(admin):
    p = admin.page
    assert admin.visivel('nav button[data-menu="canceladas"]') and admin.visivel("#btnImpLista")
    admin.abrir_dialogo()
    admin.foto("10_dialogo_personalizar")
    rotulos = p.locator("#prefMenus label").all_inner_texts()
    assert [r.strip() for r in rotulos] == ["Mapa da reserva", "Calendário", "Folha da semana", "Buscar", "Governança", "Camareiras", "Canceladas", "Histórico",
                                            "Despesas", "Usuários", "Importar lista", "+ Nova reserva"]
    admin.marcar("canceladas", False)
    admin.marcar("importar", False)
    admin.salvar()
    p.wait_for_function("() => document.getElementById('toast').textContent.includes('salvas')")
    assert not admin.visivel('nav button[data-menu="canceladas"]') and not admin.visivel("#btnImpLista")   # sem recarregar
    assert admin.visivel('nav button[data-menu="folha"]') and admin.visivel("#btnNova")
    admin.foto("11_cabecalho_com_menus_ocultos")
    admin.recarregar()                                                      # persistência no servidor
    assert not admin.visivel('nav button[data-menu="canceladas"]') and not admin.visivel("#btnImpLista")
    # a classe de preferência é distinta da de permissão
    assert "oculto-pref" in p.get_attribute('nav button[data-menu="canceladas"]', "class")
    assert "oculto" not in p.get_attribute('nav button[data-menu="canceladas"]', "class").split()
    admin.abrir_dialogo()
    assert not p.locator('.prefMenu[data-menu="canceladas"]').is_checked()
    p.click("#prefRestaurar")
    p.wait_for_selector("#dlgPref", state="hidden")
    assert admin.visivel('nav button[data-menu="canceladas"]') and admin.visivel("#btnImpLista")
    admin.recarregar()
    assert admin.visivel('nav button[data-menu="canceladas"]') and admin.visivel("#btnImpLista")
    assert not erros_graves(admin.erros), admin.erros


def test_aba_inicial_folha_e_mapa_em_4_semanas_ao_recarregar(admin):
    p = admin.page
    assert admin.aba_ativa() == "aba-mapa" and p.input_value("#mSemanas") == "14"
    admin.abrir_dialogo()
    opcoes = p.locator("#prefAba option").all_inner_texts()
    assert opcoes[0].startswith("Automática") and "Folha da semana" in opcoes
    p.select_option("#prefAba", "folha")
    p.select_option("#prefSemanas", "28")
    admin.salvar()
    assert p.input_value("#mSemanas") == "28"                               # aplicado na hora
    admin.recarregar()
    assert admin.aba_ativa() == "aba-folha"
    assert p.input_value("#mSemanas") == "28"
    p.click('nav button[data-aba="mapa"]')
    assert p.locator("#mapa .linha.cab .d").count() == 28
    p.select_option("#mSemanas", "7")                                       # trocar na hora continua livre (sem gravar)
    assert p.locator("#mapa .linha.cab .d").count() == 7
    admin.recarregar()
    assert p.input_value("#mSemanas") == "28"
    assert not erros_graves(admin.erros), admin.erros


def test_esconder_a_aba_ativa_troca_de_aba_sem_erro(admin):
    p = admin.page
    assert admin.aba_ativa() == "aba-mapa"
    admin.abrir_dialogo()
    admin.marcar("mapa", False)
    admin.salvar()
    assert not admin.visivel('nav button[data-menu="mapa"]')
    assert admin.aba_ativa() == "aba-calendario"                            # primeira visível
    assert p.locator('nav button[data-aba="calendario"]').get_attribute("class").count("ativo") == 1
    p.wait_for_timeout(9500)                                                # passa um ciclo do polling (8 s) com o mapa oculto
    p.click('nav button[data-aba="buscar"]')
    admin.abrir_dialogo()                                                   # e o mapa volta quando marcado de novo
    admin.marcar("mapa", True)
    admin.salvar()
    p.click('nav button[data-aba="mapa"]')
    assert p.locator("#mapa .barra-res").count() >= 1
    assert not erros_graves(admin.erros), admin.erros


def test_aba_inicial_oculta_nao_aparece_na_lista_e_abre_na_primeira_visivel(admin):
    p = admin.page
    admin.abrir_dialogo()
    p.select_option("#prefAba", "buscar")
    admin.marcar("buscar", False)                                           # desmarcar a escolhida volta para "Automática"
    assert p.input_value("#prefAba") == ""
    assert "Buscar" not in p.locator("#prefAba option").all_inner_texts()
    admin.marcar("mapa", False)
    admin.salvar()
    admin.recarregar()
    assert admin.aba_ativa() == "aba-calendario"


def test_nao_deixa_salvar_sem_nenhuma_aba(admin):
    p = admin.page
    admin.abrir_dialogo()
    for aba in ("mapa", "calendario", "folha", "buscar", "governanca", "camareiras", "canceladas", "historico", "usuarios"):
        admin.marcar(aba, False)
    p.click("#prefSalvar")
    assert "pelo menos uma aba" in p.locator("#prefAviso").inner_text()
    assert p.locator("#dlgPref[open]").count() == 1
    admin.foto("12_erro_sem_aba")
    assert admin.visivel('nav button[data-menu="mapa"]')                    # nada mudou
    admin.marcar("folha", True)
    p.click("#prefSalvar")
    p.wait_for_selector("#dlgPref", state="hidden")
    assert admin.visivel('nav button[data-menu="folha"]') and not admin.visivel('nav button[data-menu="mapa"]')


def test_esc_fecha_e_foco_vai_para_o_dialogo(admin):
    p = admin.page
    admin.abrir_dialogo()
    assert p.evaluate("() => document.activeElement.closest('#dlgPref') !== null")
    p.keyboard.press("Escape")
    p.wait_for_selector("#dlgPref", state="hidden")


def test_camareira_so_ve_governanca_e_camareiras_na_lista(servidor, navegador):
    t = Tela(navegador, "cam")
    try:
        assert t.aba_ativa() == "aba-governanca"          # a camareira abre direto na Governança
        t.abrir_dialogo()
        assert [r.strip() for r in t.page.locator("#prefMenus label").all_inner_texts()] == ["Governança", "Camareiras"]
        assert t.page.locator("#prefCampoMapa").is_hidden()                 # sem mapa, sem período do mapa
        t.page.click("#prefSalvar")                                         # a única aba está marcada: salva sem problema
        t.page.wait_for_selector("#dlgPref", state="hidden")
        t.abrir_dialogo()
        t.marcar("governanca", False)
        t.marcar("camareiras", False)
        t.page.click("#prefSalvar")
        assert "pelo menos uma aba" in t.page.locator("#prefAviso").inner_text()
        t.foto("13_camareira")
        assert not erros_graves(t.erros), t.erros
    finally:
        t.fechar()


@pytest.mark.parametrize("largura", [1366, 1920])
def test_botao_cabe_na_mesma_linha_do_nome_com_todos_os_botoes_do_admin(servidor, navegador, largura):
    t = Tela(navegador, "admin", largura=largura, altura=900)
    try:
        medidas = t.page.evaluate("""() => {
            const h1 = document.querySelector('header h1').getBoundingClientRect();
            const cy = h1.top + h1.height / 2;
            const itens = [...document.querySelectorAll('header nav > *')].filter(e => e.offsetParent !== null).map(e => {
                const r = e.getBoundingClientRect();
                return {id: e.id || e.dataset.aba || e.className, desvio: Math.abs(r.top + r.height / 2 - cy), dir: r.right};
            });
            const cab = document.querySelector('header').getBoundingClientRect();
            return {itens, altura: cab.height, largura: document.documentElement.clientWidth,
                    rolagem: document.documentElement.scrollWidth};
        }""")
        assert any(i["id"] == "btnPersonalizar" for i in medidas["itens"])
        assert len(medidas["itens"]) >= 13                                  # 8 abas + importar + nova + nome + personalizar + senha + sair
        assert all(i["desvio"] < 14 for i in medidas["itens"]), medidas     # todos na mesma linha do nome
        assert medidas["altura"] < 70, medidas                              # cabeçalho de uma linha só
        assert medidas["rolagem"] <= medidas["largura"]
        t.foto("14_cabecalho_%d" % largura)
    finally:
        t.fechar()


def test_celular_botao_e_dialogo_cabem_na_tela(servidor, navegador):
    t = Tela(navegador, "admin", largura=390, altura=800)
    try:
        t.page.wait_for_selector("#btnPersonalizar")
        b = t.page.locator("#btnPersonalizar").bounding_box()
        assert 0 <= b["x"] and b["x"] + b["width"] <= 390
        t.abrir_dialogo()
        d = t.page.locator("#dlgPref").bounding_box()
        assert d["x"] >= 0 and d["x"] + d["width"] <= 390 and d["y"] >= 0 and d["y"] + d["height"] <= 800
        assert t.page.locator("#prefSalvar").is_visible()
        t.page.locator("#prefFechar").scroll_into_view_if_needed()
        t.foto("15_dialogo_celular")
        assert t.page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:
        t.fechar()


def test_arrastar_no_mapa_continua_funcionando_depois_de_ocultar_e_mostrar(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.marcar("mapa", False)
    admin.marcar("canceladas", False)
    admin.salvar()
    admin.abrir_dialogo()
    admin.marcar("mapa", True)
    admin.salvar()
    p.click('nav button[data-aba="mapa"]')
    p.wait_for_selector("#mapa .barra-res")
    barra = p.locator('.barra-res:has-text("Ana Silva")')
    b = barra.bounding_box()
    x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    celula = p.locator('.d[data-apto="203"][data-dia="%s"]' % dia(3)).bounding_box()
    p.mouse.move(x, y)
    p.mouse.down()
    p.mouse.move(x, celula["y"] + celula["height"] / 2, steps=12)
    p.mouse.up()
    p.wait_for_function("() => document.getElementById('toast').textContent.includes('movida')")
    movida = p.evaluate("() => fetch('/api/reservas', {credentials:'same-origin'}).then(r => r.json())")
    assert [r["a"] for r in movida if r["nome"] == "Ana Silva"] == ["203"]
    assert not erros_graves(admin.erros), admin.erros


def test_menu_oculto_nao_tira_a_permissao_do_servidor(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.marcar("usuarios", False)
    admin.salvar()
    assert not admin.visivel('nav button[data-menu="usuarios"]')
    assert p.evaluate("() => fetch('/api/usuarios', {credentials:'same-origin'}).then(r => r.status)") == 200


def test_sem_violacoes_de_csp_nem_erros_js(admin):
    p = admin.page
    admin.abrir_dialogo()
    admin.marcar("historico", False)
    p.select_option("#prefAba", "camareiras")
    admin.salvar()
    admin.recarregar()
    assert not erros_graves(admin.erros), admin.erros
    assert admin.erros == [], admin.erros
