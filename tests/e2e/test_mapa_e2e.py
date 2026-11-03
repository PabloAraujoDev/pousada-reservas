"""E2E no navegador real (Edge via Playwright): arrastar para mover, alças, criar arrastando, formulário e diária.

Fora da suíte padrão: só roda com  POUSADA_E2E=1 python -m pytest tests/e2e -q  (e se o playwright estiver instalado).
Sobe uma instância PRÓPRIA (porta 5057, banco/backup/instância em pasta temporária); nunca toca no banco real.
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
PORTA = 5057
URL = "http://127.0.0.1:%d" % PORTA
SENHA = "senha-e2e-segura-123"
HOJE = date.today()
SHOTS = os.environ.get("POUSADA_E2E_SHOTS")


def dia(n):
    return (HOJE + timedelta(days=n)).isoformat()


def br(n):
    d = HOJE + timedelta(days=n)
    return "%02d/%02d" % (d.day, d.month)


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("e2e")
    env = dict(os.environ, POUSADA_DB=str(pasta / "e2e.db"), POUSADA_INSTANCIA=str(pasta / "inst"),
               POUSADA_BACKUP_DIR=str(pasta / "bk"), POUSADA_PORTA=str(PORTA), POUSADA_HOST="127.0.0.1")
    from pousada import config
    from pousada.db import conectar, iniciar_banco
    from pousada.regras import agora
    from pousada.usuarios import criar_usuario
    iniciar_banco(env["POUSADA_DB"], config.PASTA_MIGRACOES)
    con = conectar(env["POUSADA_DB"])
    for login, papel in (("admin", "admin"), ("consulta", "consulta"), ("diretor", "diretoria"), ("recep", "recepcao")):
        criar_usuario(con, login, login.capitalize(), SENHA, papel)
    semente = [("201", "Ana Silva", dia(2), dia(5), "pago", "socio", 15000),
               ("203", "Bruno Lima", dia(3), dia(6), "parcial", "convidado", 9900),
               ("205", "Carla Souza", dia(8), dia(10), "pendente", None, None)]
    for a, nome, i, f, p, tipo, dc in semente:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,tipo,diaria_centavos) "
                    "VALUES (?,?,'',2,?,?,?,'','',?,?,1,?,?)", (a, nome, i, f, p, agora(), agora(), tipo, dc))
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


class Sessao:
    def __init__(self, navegador, login):
        self.ctx = navegador.new_context(viewport={"width": 1400, "height": 1000})
        self.page = self.ctx.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.erros.append("pageerror: %s" % e))
        self.page.goto(URL + "/login")
        self.page.fill("#login", login)
        self.page.fill("#senha", SENHA)
        self.page.click("#btnEntrar")
        self.page.wait_for_selector("#mapa .barra-res", timeout=10000)

    def api(self, caminho):
        return self.page.evaluate("(u) => fetch(u, {credentials:'same-origin'}).then(r => r.json())", caminho)

    def reservas(self):
        return {r["nome"]: r for r in self.api("/api/reservas")}

    def barra(self, nome):
        return self.page.locator('.barra-res:has-text("%s")' % nome)

    def centro(self, loc):
        b = loc.bounding_box()
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    def celula(self, apto, n):
        return self.page.locator('.d[data-apto="%s"][data-dia="%s"]' % (apto, dia(n)))

    def largura_dia(self):
        return self.celula("205", 0).bounding_box()["width"]

    def arrastar(self, x0, y0, x1, y1, soltar=True, passos=12):
        m = self.page.mouse
        m.move(x0, y0)
        m.down()
        m.move(x1, y1, steps=passos)
        if soltar:
            m.up()

    def esperar_toast(self, texto):
        self.page.wait_for_function("t => document.getElementById('toast').textContent.includes(t)", arg=texto)

    def foto(self, nome):
        if SHOTS:
            self.page.screenshot(path=os.path.join(SHOTS, nome + ".png"))

    def fechar(self):
        self.ctx.close()


@pytest.fixture
def admin(servidor, navegador):
    s = Sessao(navegador, "admin")
    yield s
    s.fechar()


def erros_graves(erros):
    return [e for e in erros if "Content Security Policy" in e or "pageerror" in e or "Refused" in e]


def test_clique_simples_abre_a_reserva_com_a_diaria_so_no_formulario(admin):
    p = admin.page
    assert "15000" not in p.content() and "150,00" not in p.content()       # nada de valor no mapa
    admin.barra("Ana Silva").click()
    p.wait_for_selector("#dlgResumo[open]")                                  # clicar na reserva abre o Resumo; o formulário vem por "Editar dados"
    assert p.evaluate("() => document.getElementById('dlg').open") is False
    p.click('#rcCartao [data-rc="editar"]')
    p.wait_for_selector("#dlg[open]")
    assert p.locator("#dlgTitulo").inner_text() == "Editar reserva"
    p.wait_for_function("() => document.getElementById('fdiaria').value === '150,00'")
    assert p.locator("#fdiariaTotal").inner_text() == "3 diárias x R$ 150,00 = R$ 450,00"
    assert p.locator("#ftipo").input_value() == "socio"
    admin.foto("01_formulario_com_diaria")
    p.click("#btnCancelar")
    assert not erros_graves(admin.erros), admin.erros


def test_tooltip_mostra_tipo_e_nao_o_valor(admin):
    t = admin.barra("Ana Silva").get_attribute("title")
    assert "Sócio do clube" in t and "150" not in t


def test_arrastar_barra_para_outra_unidade(admin):
    x, y = admin.centro(admin.barra("Carla Souza"))
    yd = admin.centro(admin.celula("207", 9))[1]
    admin.arrastar(x, y, x, yd, soltar=False)
    assert admin.page.locator(".fantasma").count() == 1
    assert "207" in admin.page.locator(".fantasma").inner_text()
    admin.foto("02_arrastando_para_outra_unidade")
    admin.page.mouse.up()
    admin.esperar_toast("Reserva movida para 207")
    assert admin.reservas()["Carla Souza"]["a"] == "207"
    assert admin.page.locator("#dlg[open]").count() == 0
    x, y = admin.centro(admin.barra("Carla Souza"))             # volta para a 205
    admin.arrastar(x, y, x, admin.centro(admin.celula("205", 9))[1])
    admin.esperar_toast("205")
    assert admin.reservas()["Carla Souza"]["a"] == "205"


def test_arrastar_barra_para_outra_data_mantendo_noites(admin):
    x, y = admin.centro(admin.barra("Carla Souza"))
    w = admin.largura_dia()
    admin.arrastar(x, y, x + 2 * w, y)
    admin.esperar_toast("Reserva movida")
    r = admin.reservas()["Carla Souza"]
    assert (r["i"], r["f"], r["a"]) == (dia(10), dia(12), "205")
    x, y = admin.centro(admin.barra("Carla Souza"))
    admin.arrastar(x, y, x - 2 * w, y)
    admin.esperar_toast(br(8))
    assert admin.reservas()["Carla Souza"]["i"] == dia(8)


def test_alcas_alteram_saida_e_entrada(admin):
    w = admin.largura_dia()
    b = admin.barra("Carla Souza").bounding_box()
    ym = b["y"] + b["height"] / 2
    admin.arrastar(b["x"] + b["width"] - 3, ym, b["x"] + b["width"] - 3 + w, ym)
    admin.esperar_toast(br(11))
    r = admin.reservas()["Carla Souza"]
    assert (r["i"], r["f"]) == (dia(8), dia(11))
    b = admin.barra("Carla Souza").bounding_box()
    admin.arrastar(b["x"] + 3, ym, b["x"] + 3 + w, ym)
    admin.esperar_toast(br(9))
    r = admin.reservas()["Carla Souza"]
    assert (r["i"], r["f"]) == (dia(9), dia(11))
    b = admin.barra("Carla Souza").bounding_box()               # mínimo de 1 noite
    admin.arrastar(b["x"] + 3, ym, b["x"] + 3 + 3 * w, ym)      # 3 dias a mais que o limite (os dias agora se alargam: sem folga à direita)
    admin.esperar_toast(br(10))
    r = admin.reservas()["Carla Souza"]
    assert (r["i"], r["f"]) == (dia(10), dia(11))
    assert admin.page.locator(".alca[title]").first.get_attribute("aria-label")


def test_conflito_fica_vermelho_avisa_e_nao_grava(admin):
    antes = admin.reservas()["Ana Silva"]
    x, y = admin.centro(admin.barra("Ana Silva"))
    admin.arrastar(x, y, x, admin.centro(admin.celula("203", 3))[1], soltar=False)
    assert "ruim" in admin.page.locator(".fantasma").get_attribute("class")
    admin.foto("03_conflito_vermelho")
    admin.page.mouse.up()
    admin.esperar_toast("Conflito")
    assert admin.reservas()["Ana Silva"] == antes
    assert admin.page.locator(".fantasma").count() == 0


def test_unidade_ocupada_104_fica_vermelha(admin):
    x, y = admin.centro(admin.barra("Ana Silva"))
    admin.arrastar(x, y, x, admin.centro(admin.celula("104", 2))[1], soltar=False)
    assert "ruim" in admin.page.locator(".fantasma").get_attribute("class")
    admin.page.mouse.up()
    admin.esperar_toast("ocupada")
    assert admin.reservas()["Ana Silva"]["a"] == "201"


def test_esc_cancela_o_arraste_e_nao_abre_a_reserva(admin):
    antes = admin.reservas()["Ana Silva"]
    x, y = admin.centro(admin.barra("Ana Silva"))
    admin.arrastar(x, y, x, admin.centro(admin.celula("207", 2))[1], soltar=False)
    admin.page.keyboard.press("Escape")
    assert admin.page.locator(".fantasma").count() == 0
    admin.page.mouse.up()
    admin.page.wait_for_timeout(300)
    assert admin.page.locator("#dlg[open]").count() == 0
    assert admin.reservas()["Ana Silva"] == antes


def test_soltar_fora_do_mapa_cancela(admin):
    antes = admin.reservas()["Ana Silva"]
    x, y = admin.centro(admin.barra("Ana Silva"))
    admin.arrastar(x, y, x, 40)       # acima do mapa (no cabeçalho da página)
    admin.page.wait_for_timeout(300)
    assert admin.reservas()["Ana Silva"] == antes
    assert admin.page.locator("#dlg[open]").count() == 0


def test_criar_arrastando_abre_o_formulario_preenchido_e_salva(admin):
    p = admin.page
    x0, y0 = admin.centro(admin.celula("207", 1))
    x1 = admin.centro(admin.celula("207", 4))[0]
    admin.arrastar(x0, y0, x1, y0, soltar=False)
    assert p.locator(".fantasma").inner_text() == "207 · %s → %s" % (br(1), br(4))
    admin.foto("04_criando_arrastando")
    p.mouse.up()
    p.wait_for_selector("#dlg[open]")
    assert p.locator("#dlgTitulo").inner_text() == "Nova reserva"
    assert (p.locator("#fa").input_value(), p.locator("#fi").input_value(), p.locator("#ff").input_value()) == ("207", dia(1), dia(4))
    assert p.evaluate("document.activeElement.id") == "fnome"
    admin.foto("05_formulario_novo_preenchido")
    p.fill("#fnome", "Daniel Teste")
    p.select_option("#ftipo", "convidado")
    p.fill("#fdiaria", "1.234,50")
    assert p.locator("#fdiariaTotal").inner_text() == "3 diárias x R$ 1.234,50 = R$ 3.703,50"
    p.click("#btnSalvar")
    p.wait_for_function("() => !document.getElementById('dlg').open")
    r = admin.reservas()["Daniel Teste"]
    assert (r["a"], r["i"], r["f"], r["tipo"]) == ("207", dia(1), dia(4), "convidado")
    assert "diaria_centavos" not in r
    assert admin.api("/api/reservas/%d" % r["id"])["diaria_centavos"] == 123450


def test_criar_arrastando_para_tras_inverte_e_conflito_nao_abre(admin):
    p = admin.page
    x0, y0 = admin.centro(admin.celula("208", 6))
    admin.arrastar(x0, y0, admin.centro(admin.celula("208", 4))[0], y0, soltar=False)
    assert p.locator(".fantasma").inner_text() == "208 · %s → %s" % (br(4), br(6))
    p.keyboard.press("Escape")
    p.mouse.up()
    x0, y0 = admin.centro(admin.celula("203", 1))                # faixa sobre a reserva de Bruno (203, dias 3..6)
    admin.arrastar(x0, y0, admin.centro(admin.celula("203", 4))[0], y0, soltar=False)
    assert "ruim" in p.locator(".fantasma").get_attribute("class")
    p.mouse.up()
    admin.esperar_toast("Conflito")
    assert p.locator("#dlg[open]").count() == 0


def test_clique_simples_em_celula_vazia_continua_abrindo_o_formulario(admin):
    admin.celula("206", 3).click()
    admin.page.wait_for_selector("#dlg[open]")
    assert admin.page.locator("#fa").input_value() == "206" and admin.page.locator("#fi").input_value() == dia(3)
    admin.page.click("#btnCancelar")


def test_polling_nao_quebra_o_arraste(admin):
    p = admin.page
    nome = "Carla Souza"
    x, y = admin.centro(admin.barra(nome))
    yd = admin.centro(admin.celula("206", 9))[1]
    p.evaluate("window.__barra = document.querySelector('.barra-res.em-arraste, .barra-res[data-id=\"3\"]')")
    admin.arrastar(x, y, x, yd, soltar=False)
    p.wait_for_timeout(9500)           # passa pelo menos um ciclo de 8 s do polling
    assert p.evaluate("window.__barra.isConnected") is True
    assert p.locator(".fantasma").count() == 1
    p.mouse.up()
    admin.esperar_toast("Reserva movida para 206")
    assert admin.reservas()[nome]["a"] == "206"
    x, y = admin.centro(admin.barra(nome))
    admin.arrastar(x, y, x, admin.centro(admin.celula("205", 9))[1])
    admin.esperar_toast("205")
    assert not erros_graves(admin.erros), admin.erros


def test_consulta_nao_arrasta_e_nao_ve_a_diaria(servidor, navegador):
    s = Sessao(navegador, "consulta")
    try:
        p = s.page
        assert p.locator(".alca").count() == 0
        antes = s.reservas()["Ana Silva"]
        x, y = s.centro(s.barra("Ana Silva"))
        s.arrastar(x, y, x, s.centro(s.celula("207", 2))[1])
        p.wait_for_timeout(300)
        assert p.locator(".fantasma").count() == 0 and s.reservas()["Ana Silva"] == antes
        x0, y0 = s.centro(s.celula("207", 1))
        s.arrastar(x0, y0, s.centro(s.celula("207", 4))[0], y0)
        p.wait_for_timeout(300)
        assert p.locator("#dlg[open]").count() == 0
        s.barra("Ana Silva").click()
        p.wait_for_selector("#dlgResumo[open]")                              # consulta: Resumo só leitura, sem "Editar dados" e sem valores
        assert p.locator('#dlgResumo [data-rc="editar"]').count() == 0 and p.evaluate("() => document.getElementById('dlg').open") is False
        p.wait_for_timeout(500)
        assert "150,00" not in p.content()
        assert "diaria" not in p.evaluate("document.getElementById('dlgResumo').innerText").lower()
        assert "diaria_centavos" not in str(s.api("/api/reservas/1"))
        s.foto("06_consulta_sem_diaria")
        assert not erros_graves(s.erros), s.erros
    finally:
        s.fechar()


def test_recepcao_e_diretoria_veem_a_diaria_desabilitada(servidor, navegador):
    for login in ("recep", "diretor"):
        s = Sessao(navegador, login)
        try:
            s.barra("Ana Silva").click()
            s.page.wait_for_selector("#dlgResumo[open]")
            assert "R$ 450,00 (3 x R$ 150,00)" in s.page.inner_text("#rcCartao")             # o Resumo mostra a diária para quem pode ver valores
            assert s.page.locator(".alca").count() == 0
            if login == "recep":                                                              # recepção: o formulário traz a diária desabilitada
                s.page.click('#rcCartao [data-rc="editar"]')
                s.page.wait_for_function("() => document.getElementById('fdiaria').value === '150,00'")
                assert s.page.locator("#fdiaria").is_disabled()
            else:
                assert s.page.locator('#dlgResumo [data-rc="editar"]').count() == 0
        finally:
            s.fechar()


def test_nao_envia_diaria_se_o_detalhe_falhou(admin):
    """Se o GET do detalhe falha, o campo fica vazio/desabilitado e o PUT não leva diaria_centavos (não apaga)."""
    p = admin.page
    enviados = []

    def tratar(rota):
        if rota.request.method == "GET":
            rota.abort()
        else:
            enviados.append(rota.request.post_data)
            rota.continue_()

    admin.barra("Ana Silva").click()
    p.wait_for_selector("#dlgResumo[open]")                                  # o Resumo carrega o detalhe antes de a rede "falhar"
    p.route("**/api/reservas/1", tratar)
    p.click('#rcCartao [data-rc="editar"]')
    p.wait_for_selector("#dlg[open]")
    p.wait_for_timeout(500)
    assert p.locator("#fdiaria").is_disabled() and p.locator("#fdiaria").input_value() == ""
    p.fill("#fnome", "Ana Silva")
    p.click("#btnSalvar")
    p.wait_for_function("() => !document.getElementById('dlg').open")
    assert enviados and "diaria_centavos" not in enviados[0]
    p.unroute("**/api/reservas/1")
    p.evaluate("() => document.getElementById('dlgResumo').close()")
    assert admin.api("/api/reservas/1")["diaria_centavos"] == 15000


def test_sem_violacoes_de_csp_nem_erros_js(admin):
    admin.page.reload()
    admin.page.wait_for_selector("#mapa .barra-res")
    for aba in ("buscar", "folha", "historico"):
        admin.page.click('nav button[data-aba="%s"]' % aba)
    admin.page.wait_for_timeout(500)
    ruins = [e for e in admin.erros if "favicon" not in e.lower()]
    assert not ruins, ruins


def test_polling_sem_mudanca_nao_refaz_o_mapa_nem_tira_o_foco_do_teclado(admin):
    """Regressão: o polling de 8 s refazia o mapa inteiro e o foco de quem navega por teclado voltava ao início da página."""
    p = admin.page
    admin.barra("Ana Silva").focus()
    p.evaluate("() => { window.__redesenhos = 0; new MutationObserver(m => { window.__redesenhos++; })"
               ".observe(document.getElementById('mapa'), {childList: true}); }")
    with p.expect_response(lambda r: r.url.endswith("/api/reservas") and r.request.method == "GET", timeout=15000):
        pass                                                   # espera o próximo polling
    p.wait_for_timeout(300)
    assert p.evaluate("() => window.__redesenhos") == 0
    assert p.evaluate("() => document.activeElement.classList.contains('barra-res')")


def test_mapa_sem_linha_aptos_livres_duplicada_e_com_disponibilidade(admin):
    """Regressão de UX: 'Aptos livres' (rodapé) repetia a linha Disponibilidade (topo). Fica só a do topo."""
    p = admin.page
    rotulos = p.locator("#mapa .linha .lab").all_inner_texts()
    assert "Disponibilidade" in rotulos and "Aptos livres" not in rotulos
    assert rotulos[-4:] == ["Entradas", "Saídas", "Hóspedes na noite", "Café da manhã"]


def test_mapa_dias_ocupam_a_largura_da_tela_sem_rolagem(admin):
    """Regressão: os dias tinham largura fixa (42 px) e o mapa de 2 semanas usava menos da metade de uma tela de 1400 px."""
    p = admin.page
    m = p.evaluate("() => { const w = document.querySelector('.mapa-wrap'); const d = document.getElementById('mapa'); return [w.clientWidth, w.scrollWidth, +d.dataset.w, +d.dataset.dias]; }")
    assert m[1] <= m[0] + 1                       # sem barra de rolagem horizontal
    assert m[2] > 42 and m[2] * m[3] + 102 >= m[0] - m[3]        # os dias se alargaram até quase preencher a largura
    admin.page.set_viewport_size({"width": 700, "height": 900})
    p.wait_for_function("() => +document.getElementById('mapa').dataset.w === 42")       # tela estreita: volta ao mínimo e rola
    admin.page.set_viewport_size({"width": 1400, "height": 1000})
    p.wait_for_function("() => +document.getElementById('mapa').dataset.w > 42")


def test_foco_do_teclado_visivel_nos_botoes_do_cabecalho(admin):
    p = admin.page
    cores = p.evaluate("() => { const b = document.querySelector('nav button[data-aba=folha]'); b.focus(); "
                       "return [getComputedStyle(document.querySelector('header')).backgroundColor, getComputedStyle(b).outlineColor]; }")
    assert cores[0] != cores[1]


def test_importar_nao_mostra_desfazer_antes_de_importar(admin):
    """Regressão: o botão 'Desfazer importação' aparecia antes de qualquer importação (atributo class duplicado no HTML)."""
    p = admin.page
    p.click("#btnImpLista")
    p.wait_for_selector("#dlgImp[open]")
    assert not p.is_visible("#impDesfazer")
    p.click("#impFechar")


def test_historico_da_reserva_com_datas_em_dia_mes_ano_e_ordem_natural(admin):
    """Regressão de UX: o histórico mostrava AAAA-MM-DD e 'saída' antes de 'entrada'."""
    p = admin.page
    admin.celula("206", 4).click()
    p.wait_for_selector("#dlg[open]")
    p.fill("#fnome", "Historico Legivel")
    p.click("#btnSalvar")
    p.wait_for_function("() => !document.getElementById('dlg').open")
    admin.barra("Historico Legivel").click()
    p.wait_for_selector("#dlgResumo[open]")
    p.click('#rcCartao [data-rc="historico"]')                               # o botão Histórico do Resumo abre a aba Histórico do formulário
    p.wait_for_selector("#dlg[open]")
    p.click("#abaHistForm")
    p.wait_for_function("() => document.getElementById('tabHistForm').innerText.includes('Criou')")
    t = p.locator("#tabHistForm").inner_text()
    d = HOJE + timedelta(days=4)
    assert "entrada: %02d/%02d/%d" % (d.day, d.month, d.year) in t and "pagamento: Pendente" in t
    assert t.index("unidade:") < t.index("entrada:") < t.index("saída:") < t.index("pessoas:")
    p.click("#btnFecharHist")
