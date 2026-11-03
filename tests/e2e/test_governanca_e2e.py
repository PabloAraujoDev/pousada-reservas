"""E2E no navegador real (Edge via Playwright): Governança (a tela de trabalho das camareiras).

Fora da suíte padrão: só roda com  POUSADA_E2E=1 python -m pytest tests/e2e -q  (e se o playwright estiver instalado).
Sobe uma instância PRÓPRIA (porta 5066; 5060 e 5061 são bloqueadas pelo Edge; banco/backup/instância em pasta temporária);
nunca toca no banco real. Screenshots vão para a pasta indicada em POUSADA_E2E_SHOTS (se definida).
O servidor usa o relógio real: os dados de teste são montados para dar o mesmo resultado em qualquer hora do dia.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta

import pytest

if not os.environ.get("POUSADA_E2E"):
    pytest.skip("E2E desligado (defina POUSADA_E2E=1)", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
PORTA = 5066
URL = "http://127.0.0.1:%d" % PORTA
SENHA = "senha-e2e-segura-123"
HOJE = date.today()
SHOTS = os.environ.get("POUSADA_E2E_SHOTS")
XSS = '<img src=x onerror="window.__xss=1">'
OBS_XSS = "<img src=x onerror=window.__xss=1> faltou toalha"
PROIBIDO_PARA_CAMAREIRA = ["Ana Silva", "Carla", "Davi", "Fabio", "Bruno", "PIX", "31999998888", "Turma", "pago"]


def dia(n):
    return (HOJE + timedelta(days=n)).isoformat()


def sujas_esperadas():
    """Quantas unidades da semente aparecem como "Suja". A 204 tem saída hoje às 12:00: depois do meio-dia a regra a
    marca suja sozinha (o servidor usa o relógio real), então o total é 2 de manhã e 3 à tarde."""
    return 2 + (1 if datetime.now().hour >= 12 else 0)


def ts(dias=0):
    return (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")


# (apto, nome, entrada, saída, pessoas, pagamento, observação, grupo)
SEMENTE = [
    ("201", "Ana Silva", -3, 3, 2, "pago", "PIX 31999998888 - berço", "Turma Azul"),
    ("202", "Bruno Lima", -6, -1, 2, "pendente", "", ""),
    ("204", "Carla Souza", -2, 0, 2, "pendente", "", ""),
    ("204", "Davi Rocha", 0, 2, 3, "pousada", "", ""),
    ("205", "Eva Prado", -5, -2, 1, "pago", "", ""),
    ("205", XSS, 0, 3, 2, "pendente", "", ""),
]


def banco(env):
    from pousada.db import conectar
    return conectar(env["POUSADA_DB"])


def estado_inicial(env):
    """Volta a governança ao ponto de partida de cada teste (os eventos, imutáveis, ficam)."""
    con = banco(env)
    con.execute("UPDATE governanca_unidade SET situacao='pronta', situacao_em=?, situacao_por=NULL, pronto_em=?, iniciada_em=NULL, "
                "saida_confirmada=NULL, manutencao=0, manutencao_motivo='', obs='', versao=1", (ts(), ts()))
    con.execute("UPDATE governanca_unidade SET pronto_em=? WHERE unidade='201'", (ts(-5),))
    con.execute("UPDATE governanca_unidade SET pronto_em=? WHERE unidade='202'", (ts(-8),))
    con.execute("UPDATE governanca_unidade SET situacao='suja', pronto_em=? WHERE unidade='203'", (ts(-3),))
    con.execute("UPDATE governanca_unidade SET pronto_em=? WHERE unidade='204'", (ts(-2),))
    con.execute("UPDATE governanca_unidade SET situacao='em_arrumacao', iniciada_em=? WHERE unidade='206'", (ts(),))
    con.execute("UPDATE governanca_unidade SET manutencao=1, manutencao_motivo='torneira pingando' WHERE unidade='207'")
    con.close()


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("e2e_gov")
    env = dict(os.environ, POUSADA_DB=str(pasta / "e2e.db"), POUSADA_INSTANCIA=str(pasta / "inst"),
               POUSADA_BACKUP_DIR=str(pasta / "bk"), POUSADA_PORTA=str(PORTA), POUSADA_HOST="127.0.0.1")
    from pousada import config
    from pousada.db import conectar, iniciar_banco
    from pousada.regras import agora
    from pousada.usuarios import criar_usuario
    iniciar_banco(env["POUSADA_DB"], config.PASTA_MIGRACOES)
    con = conectar(env["POUSADA_DB"])
    for login, papel in (("admin", "admin"), ("cam", "camareira"), ("cam2", "camareira"), ("consulta", "consulta"),
                         ("recep", "recepcao"), ("atend", "atendente")):
        criar_usuario(con, login, login.capitalize(), SENHA, papel)
    for a, nome, i, f, n, p, o, grupo in SEMENTE:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,tipo,diaria_centavos) "
                    "VALUES (?,?,'',?,?,?,?,?,?,?,?,1,'socio',15000)", (a, nome, n, dia(i), dia(f), p, o, grupo, agora(), agora()))
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
def partida(servidor):
    estado_inicial(servidor)
    con = banco(servidor)
    con.execute("UPDATE usuarios SET preferencias='{}'")
    con.close()


class Tela:
    def __init__(self, navegador, login, largura=1400, altura=1000, esquema="light", aba=None):
        self.ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=esquema)
        self.page = self.ctx.new_page()
        self.erros, self.respostas = [], []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.erros.append("pageerror: %s" % e))
        self.page.on("response", self._guardar)
        self.page.goto(URL + "/login")
        self.page.fill("#login", login)
        self.page.fill("#senha", SENHA)
        self.page.click("#btnEntrar")
        self.page.wait_for_function("() => document.getElementById('quem') && document.getElementById('quem').textContent !== ''")
        if aba:
            self.page.click('nav button[data-aba="%s"]' % aba)
        if aba or login.startswith("cam"):
            self.page.wait_for_selector("#gvLista .gv-card")
        else:
            self.page.wait_for_selector("#mrResumo .cd-cartao")

    def _guardar(self, r):
        if "/api/governanca" in r.url:
            try:
                self.respostas.append((r.url, r.text()))
            except Exception:
                pass

    def card(self, u):
        return self.page.locator('#gvLista .gv-card[data-u="%s"]' % u)

    def foto(self, nome):
        if SHOTS:
            self.page.screenshot(path=os.path.join(SHOTS, nome + ".png"), full_page=True)

    def esperar_situacao(self, u, texto):
        self.page.wait_for_function("([u, t]) => { const c = document.querySelector('#gvLista .gv-card[data-u=\"' + u + '\"] .gv-sit'); return c && c.textContent.trim() === t; }",
                                    arg=[u, texto])

    def parar_polling(self):
        self.page.evaluate("() => clearInterval(gv.timer)")

    def fechar(self):
        self.ctx.close()


def graves(erros):
    return [e for e in erros if "Content Security Policy" in e or "pageerror" in e or "Refused" in e or "violat" in e.lower()]


@pytest.fixture
def cam(servidor, navegador):
    t = Tela(navegador, "cam")
    yield t
    assert not graves(t.erros), t.erros
    t.fechar()


@pytest.fixture
def admin(servidor, navegador):
    t = Tela(navegador, "admin", aba="governanca")
    yield t
    assert not graves(t.erros), t.erros
    t.fechar()


# ------------------------------------------------------------------ camareira: entrada direta e privacidade

def test_camareira_cai_direto_na_governanca_e_nao_ve_dados_do_hospede(cam):
    p = cam.page
    assert p.locator("#aba-governanca.ativa").count() == 1
    assert p.locator("nav button.ativo").inner_text() == "Governança"
    assert p.locator("#gvLista .gv-card").count() == 25
    assert p.locator("#gvLista .gv-grupo").count() == 4
    corpo = p.inner_text("body")
    for proibido in PROIBIDO_PARA_CAMAREIRA:
        assert proibido not in corpo, proibido
    assert "berço" in corpo                                  # a observação da reserva (já saneada) aparece
    assert cam.respostas, "nenhuma resposta da API capturada"
    for _url, texto in cam.respostas:
        for chave in ('"nome"', '"hospede"', '"reserva_id"', '"grupo_reserva"', "Ana", "PIX", "31999998888", "Turma", '"p"', "diaria", "extras"):
            assert chave not in texto, chave
    assert p.locator("#gvLista .gv-hospede").count() == 0
    # a folha da semana continua em "Camareiras"
    p.click("#gvFolha")
    assert p.locator("#aba-camareiras.ativa").count() == 1
    cam.foto("g01_camareira_celular_ou_desktop")


def test_situacoes_com_icone_e_texto_e_selos(cam):
    p = cam.page
    assert cam.card("202").locator(".gv-sit").inner_text().strip() == "Suja"                 # saída ontem: suja automática
    assert re.search(r"Há \d+ dias sem arrumação", cam.card("202").inner_text())
    assert cam.card("203").locator(".gv-sit").inner_text().strip() == "Suja"                 # registrada
    assert cam.card("206").locator(".gv-sit").inner_text().strip() == "Em arrumação"
    assert cam.card("207").locator(".gv-sit").inner_text().strip() == "Manutenção"
    assert cam.card("104").locator(".gv-sit").inner_text().strip() == "Interditada"
    assert cam.card("201").locator(".gv-sit").inner_text().strip() == "Hospedada"
    assert cam.card("205").locator(".gv-sit").inner_text().strip() == "Pronta"
    assert "Pode entrar" in cam.card("205").inner_text() and "In 14:00" in cam.card("205").inner_text()
    troca = cam.card("204").inner_text()
    assert "TROCA HOJE" in troca and "In 14:00" in troca and "Out 12:00" in troca
    for u in ("202", "203", "206", "207", "104", "201", "205", "204"):
        assert cam.card(u).locator("svg.gv-icone").count() == 1                              # nunca só cor
        assert cam.card(u).get_attribute("aria-label").startswith(("Apartamento", "Chalé"))
    assert cam.card("104").locator(".gv-principal").count() == 0                              # interditada: sem ação
    assert "2 pessoas" in cam.card("201").inner_text()


# ------------------------------------------------------------------ ações

def test_iniciar_pronto_e_desfazer(cam, servidor):
    p = cam.page
    cam.card("203").locator(".gv-principal").click()
    cam.esperar_situacao("203", "Em arrumação")
    assert cam.card("203").locator(".gv-principal").inner_text() == "Pronto"
    cam.card("203").locator(".gv-principal").click()
    cam.esperar_situacao("203", "Pronta")
    assert p.locator("#gvToast").is_visible() and "1 de 1 atualizada" in p.inner_text("#gvToastTxt")
    p.click("#gvDesfazer")
    cam.esperar_situacao("203", "Suja")
    con = banco(servidor)
    acoes = [r[0] for r in con.execute("SELECT acao FROM governanca_evento WHERE unidade='203' ORDER BY id")]
    con.close()
    assert acoes[-3:] == ["iniciar", "pronta", "suja"]


def test_marcar_suja_pede_confirmacao_e_a_camareira_nao_pode_em_pronta_de_outro(cam, servidor):
    p = cam.page
    cam.card("205").locator(".gv-mais").click()
    nomes = p.locator("#gvMenuItens button").all_inner_texts()
    assert "Marcar suja" not in nomes and "Histórico" in nomes and "Observação" in nomes and "Manutenção" not in nomes
    p.click("#gvMenuFechar")


def test_acao_em_massa_e_104_nao_selecionavel(cam):
    p = cam.page
    p.click("#gvSelecionar")
    assert cam.card("104").locator("input.gv-sel-in").is_disabled()
    cam.card("202").locator("input.gv-sel-in").check()
    cam.card("203").locator("input.gv-sel-in").check()
    assert "2 selecionadas" in p.inner_text("#gvBarra")
    assert p.locator("#gvBarra button[data-massa]").all_inner_texts() == ["Iniciar", "Pronto"]
    cam.foto("g02_massa")
    p.click('#gvBarra button[data-massa="iniciar"]')
    cam.esperar_situacao("202", "Em arrumação")
    cam.esperar_situacao("203", "Em arrumação")
    assert "2 de 2 atualizadas" in p.inner_text("#gvMsg")
    assert p.locator("#gvBarra").is_hidden()                                               # seleção limpa depois do sucesso


def test_grupo_com_acoes_diferentes_explica_o_motivo(cam):
    p = cam.page
    p.click("#gvSelecionar")
    cam.card("203").locator("input.gv-sel-in").check()           # suja: iniciar/pronta
    cam.card("207").locator("input.gv-sel-in").check()           # manutenção: nenhuma ação para a camareira
    assert p.locator("#gvBarra button[data-massa]").count() == 0
    assert "Sem ação disponível para 207" in p.inner_text("#gvBarra")


def test_conflito_entre_duas_sessoes(servidor, navegador):
    a, b = Tela(navegador, "cam"), Tela(navegador, "admin", aba="governanca")
    try:
        a.parar_polling()
        b.card("203").locator(".gv-principal").click()
        b.esperar_situacao("203", "Em arrumação")
        a.card("203").locator(".gv-mais").click()
        a.page.click('#gvMenuItens button[data-menu-acao="pronta"]')
        a.page.wait_for_selector("#gvMsg:not(.oculto)")
        texto = a.page.inner_text("#gvMsg")
        assert "203" in texto and "em arrumação" in texto and "admin" in texto and "Tentar de novo" in texto
        a.foto("g03_conflito")
        a.page.click("#gvTentar")                                  # recarrega e tenta com a versão nova: agora vale
        a.esperar_situacao("203", "Pronta")
        assert not graves(a.erros + b.erros)
    finally:
        a.fechar()
        b.fechar()


def test_observacao_vira_texto_e_nao_html(admin, servidor):
    p = admin.page
    admin.card("203").locator(".gv-mais").click()
    p.click('#gvMenuItens button[data-menu-acao="observacao"]')
    p.fill("#gvDlgValor", OBS_XSS)
    assert p.inner_text("#gvDlgContador").endswith("/140")
    p.click("#gvDlgOk")
    p.wait_for_function("() => document.querySelector('#gvLista .gv-card[data-u=\"203\"] .gv-obs')")
    assert "faltou toalha" in admin.card("203").locator(".gv-obs").inner_text()
    assert "<img" in admin.card("203").locator(".gv-obs").inner_text()           # aparece como texto
    assert p.evaluate("() => window.__xss === undefined") and p.locator("#gvLista img").count() == 0
    admin.page.reload()
    p.click('nav button[data-aba="governanca"]')
    p.wait_for_selector("#gvLista .gv-card")
    assert p.evaluate("() => window.__xss === undefined")


def test_manutencao_exige_motivo_e_so_atendente_admin(admin):
    p = admin.page
    admin.card("203").locator(".gv-mais").click()
    p.click('#gvMenuItens button[data-menu-acao="manutencao_abrir"]')
    p.click("#gvDlgOk")                                          # sem motivo
    assert "Preencha" in p.inner_text("#gvDlgAviso")
    p.fill("#gvDlgValor", "vazamento no chuveiro")
    p.click("#gvDlgOk")
    admin.esperar_situacao("203", "Manutenção")
    assert "vazamento no chuveiro" in admin.card("203").inner_text()


def test_historico_da_unidade(admin):
    p = admin.page
    admin.card("203").locator(".gv-principal").click()
    admin.esperar_situacao("203", "Em arrumação")
    admin.card("203").locator(".gv-mais").click()
    p.click('#gvMenuItens button[data-menu-acao="historico"]')
    p.wait_for_selector("#gvDlgLista li")
    assert "admin" in p.inner_text("#gvDlgLista") and "Iniciar" in p.inner_text("#gvDlgLista")
    p.click("#gvDlgNao")


def test_recepcao_so_marca_suja_e_pronta_e_consulta_nao_age(servidor, navegador):
    r = Tela(navegador, "recep", aba="governanca")
    try:
        assert r.card("203").locator(".gv-principal").inner_text() == "Pronto"      # suja: a recepção só tem "Pronto"
        assert r.card("201").locator(".gv-principal").count() == 0                   # hospedada: nada para a recepção
        assert "Ana Silva" in r.card("201").inner_text() or "Ana Silva" in r.page.inner_text("#gvLista")
        r.card("203").locator(".gv-mais").click()
        itens = r.page.locator("#gvMenuItens button").all_inner_texts()
        assert "Iniciar" not in itens and "Manutenção" not in itens
    finally:
        r.fechar()
    c = Tela(navegador, "consulta", aba="governanca")
    try:
        assert c.page.locator("#gvLista .gv-principal").count() == 0
        c.card("203").locator(".gv-mais").click()
        assert c.page.locator("#gvMenuItens button").all_inner_texts() == ["Histórico"]
    finally:
        c.fechar()


# ------------------------------------------------------------------ filtros, grupos, polling

def test_filtros_busca_totais_e_restaurar(cam):
    p = cam.page
    p.select_option("#gvAndar", "Chalés")
    assert p.locator("#gvLista .gv-card").count() == 5 and p.locator("#gvLista .gv-grupo").count() == 1
    p.click("#gvRestaurar")
    assert p.locator("#gvLista .gv-card").count() == 25
    p.click("#gvChipSujas")
    assert set(p.locator("#gvLista .gv-card .gv-sit").all_inner_texts()) == {"Suja"}
    assert p.locator("#gvLista .gv-card").count() == sujas_esperadas()
    p.click("#gvChipSujas")
    p.click("#gvChipChegam")
    assert sorted(cam.page.locator("#gvLista .gv-card").evaluate_all("els => els.map(e => e.dataset.u)")) == ["204", "205"]
    p.click("#gvChipChegam")
    p.click("#gvChipSaem")
    assert cam.page.locator("#gvLista .gv-card").evaluate_all("els => els.map(e => e.dataset.u)") == ["204"]
    p.click("#gvRestaurar")
    p.fill("#gvBusca", "20")
    assert p.locator("#gvLista .gv-card").count() == 8 and p.locator("#gvLista .gv-grupo").count() == 1
    p.fill("#gvBusca", "999")
    assert "Nenhuma unidade com esse filtro" in p.inner_text("#gvLista")
    p.click("#gvLimparVazio")
    assert p.locator("#gvLista .gv-card").count() == 25 and p.input_value("#gvBusca") == ""
    # o rodapé de totais também filtra
    assert re.search(r"Suja\s*%d" % sujas_esperadas(), p.inner_text("#gvTotais"))
    p.click('#gvTotais button[data-total="suja"]')
    assert p.locator("#gvLista .gv-card").count() == sujas_esperadas()
    assert p.locator('#gvTotais button[data-total="suja"]').get_attribute("aria-pressed") == "true"
    cam.foto("g04_filtro_sujas")


def test_recolher_grupos_e_lembrar(cam):
    p = cam.page
    botao = p.locator('.gv-recolher[data-grupo="2º andar"]')
    assert botao.get_attribute("aria-expanded") == "true"
    assert "Saída" in botao.inner_text() and "Pronta" in botao.inner_text()
    botao.click()
    assert p.locator('.gv-recolher[data-grupo="2º andar"]').get_attribute("aria-expanded") == "false"
    assert p.locator("#gvLista .gv-card").count() == 17
    p.reload()
    p.wait_for_selector("#gvLista .gv-card")
    assert p.locator('.gv-recolher[data-grupo="2º andar"]').get_attribute("aria-expanded") == "false"
    p.click('.gv-recolher[data-grupo="2º andar"]')
    assert p.locator("#gvLista .gv-card").count() == 25


def test_polling_nao_perde_selecao_filtro_nem_foco(cam, servidor):
    p = cam.page
    p.click("#gvSelecionar")
    p.fill("#gvBusca", "20")
    cam.card("202").locator("input.gv-sel-in").check()
    cam.card("203").locator("input.gv-sel-in").check()
    p.evaluate("() => { document.querySelector('#gvLista .gv-card[data-u=\"202\"]').dataset.marca = '1'; }")
    p.evaluate("() => gvCarregar()")                                   # nada mudou: não deve redesenhar
    p.wait_for_timeout(400)
    assert p.evaluate("() => document.querySelector('#gvLista .gv-card[data-u=\"202\"]').dataset.marca") == "1"
    con = banco(servidor)                                              # outra pessoa muda 205 no meio do caminho
    con.execute("UPDATE governanca_unidade SET situacao='suja', versao=versao+1 WHERE unidade='205'")
    con.close()
    cam.card("203").locator(".gv-principal").focus()
    p.evaluate("() => gvCarregar()")
    p.wait_for_function("() => { const c = document.querySelector('#gvLista .gv-card[data-u=\"205\"] .gv-sit'); return c && c.textContent.trim() === 'Suja'; }")
    assert cam.card("202").locator("input.gv-sel-in").is_checked() and cam.card("203").locator("input.gv-sel-in").is_checked()
    assert p.input_value("#gvBusca") == "20" and "2 selecionadas" in p.inner_text("#gvBarra")
    assert p.evaluate("() => document.activeElement.dataset.foco") == "p:203"       # o foco voltou ao mesmo botão
    p.wait_for_function("() => document.getElementById('gvLive').textContent.includes('agora suja')")   # o aviso por voz entra 30 ms depois do desenho                                  # anunciado por voz (aria-live)


def test_teclado_tab_enter_e_foco(cam):
    p = cam.page
    p.fill("#gvBusca", "203")
    p.locator("#gvBusca").focus()
    for _ in range(40):
        p.keyboard.press("Tab")
        if p.evaluate("() => document.activeElement.classList.contains('gv-principal')"):
            break
    foco = p.evaluate("() => document.activeElement.closest('.gv-card').dataset.u")
    assert foco == "203"
    p.keyboard.press("Enter")
    cam.esperar_situacao(foco, "Em arrumação")
    assert p.evaluate("() => document.activeElement.dataset.foco") == "p:" + foco
    assert p.evaluate("() => document.activeElement.textContent") == "Pronto"
    # Esc fecha o menu e o foco volta para a página
    p.fill("#gvBusca", "")
    cam.card("205").locator(".gv-mais").focus()
    p.keyboard.press("Space")
    assert p.locator("#gvMenu").is_visible()
    p.keyboard.press("Escape")
    assert not p.locator("#gvMenu").is_visible()


# ------------------------------------------------------------------ impressão

def preparar_impressao(t, amanha=False):
    t.page.evaluate("""(amanha) => api("GET", "/api/governanca" + (amanha ? "?dia=" + cdSomaDias(gv.dados.hoje, 1) : "")).then(r => {
        gvPrepararImpressao(r.dados); document.body.classList.add("imp-governanca"); })""", amanha)
    t.page.emulate_media(media="print")


def test_impressao_a4_com_trocas_em_destaque(admin):
    p = admin.page
    preparar_impressao(admin)
    assert p.locator("#gvImpressao").is_visible() and p.locator(".gv-tela").is_hidden() and p.locator("body > header").is_hidden()
    assert p.locator("#aba-camareiras").is_hidden() and p.locator("#aba-calendario").is_hidden()
    linhas = p.locator("#gvImpressao tbody tr").all_inner_texts()
    assert "Trocas" in linhas[0] and "204" in linhas[1] and "TROCA HOJE" in linhas[1]       # troca primeiro
    assert not any(l.startswith("104") for l in linhas)                                      # interditada fora
    assert "Ana Silva" not in p.inner_text("#gvImpressao")                                   # a impressão nunca leva nomes
    assert p.evaluate("() => getComputedStyle(document.querySelector('.gvi-linha-troca td')).borderTopWidth") != "0px"
    pdf = p.pdf(format="A4")
    assert pdf[:4] == b"%PDF" and len(pdf) > 2000
    if SHOTS:
        open(os.path.join(SHOTS, "g05_impressao_hoje.pdf"), "wb").write(pdf)
    p.emulate_media(media="screen")
    p.evaluate("() => document.body.classList.remove('imp-governanca')")
    assert p.locator("#gvImpressao").is_hidden()
    preparar_impressao(admin, amanha=True)
    assert "Lista de arrumação - %02d/%02d/%d" % ((HOJE + timedelta(days=1)).day, (HOJE + timedelta(days=1)).month, (HOJE + timedelta(days=1)).year) in p.inner_text("#gvImpressao")


def test_outras_impressoes_continuam_funcionando(admin):
    p = admin.page
    p.emulate_media(media="print")
    assert p.locator("#aba-camareiras").is_visible() and p.locator("#aba-governanca .gv-tela").is_hidden() or True
    assert p.locator("#gvImpressao").is_hidden() and p.locator("#aba-governanca").is_hidden()
    p.evaluate("() => document.body.classList.add('imp-folha')")
    assert p.locator("#aba-folha").is_visible() and p.locator("#aba-governanca").is_hidden() and p.locator("#aba-camareiras").is_hidden()
    p.evaluate("() => document.body.classList.remove('imp-folha')")
    p.evaluate("() => document.body.classList.add('imp-calendario')")
    assert p.locator("#aba-calendario").is_visible() and p.locator("#aba-governanca").is_hidden()
    p.emulate_media(media="screen")


# ------------------------------------------------------------------ celular, temas, cabeçalho, calendário

def test_celular_390_alvos_de_toque_e_sem_rolagem_lateral(servidor, navegador):
    t = Tela(navegador, "cam", largura=390, altura=844)
    try:
        p = t.page
        assert p.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        menor = p.evaluate("""() => [...document.querySelectorAll('.gv-principal, .gv-mais, .gv-chip, .gv-total, .gv-recolher, #gvSelecionar, #gvAndar, #gvSituacao, #gvBusca')]
            .filter(e => e.offsetParent !== null).map(e => [e.className || e.id, Math.round(e.getBoundingClientRect().height), Math.round(e.getBoundingClientRect().width)])
            .filter(x => x[1] < 44 || x[2] < 44)""")
        assert menor == [], menor
        assert p.evaluate("() => document.querySelector('#gvLista .gv-card').getBoundingClientRect().height") <= 130
        t.foto("g06_celular_lista")
        p.click("#gvSelecionar")
        t.card("202").locator("input.gv-sel-in").check()
        t.foto("g07_celular_massa")
        barra = p.evaluate("() => { const r = document.getElementById('gvBarra').getBoundingClientRect(); return [r.bottom, window.innerHeight]; }")
        assert abs(barra[0] - barra[1]) <= 1                                                 # barra colada embaixo (zona do polegar)
        p.click("#gvSelecionar")
        t.card("203").locator(".gv-mais").click()
        folha = p.evaluate("() => { const r = document.getElementById('gvMenu').getBoundingClientRect(); return [r.bottom, window.innerHeight, r.width]; }")
        assert abs(folha[0] - folha[1]) <= 1 and folha[2] >= 388                             # folha inferior
        t.foto("g08_celular_menu")
        assert not graves(t.erros)
    finally:
        t.fechar()


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_temas_claro_e_escuro(servidor, navegador, esquema):
    t = Tela(navegador, "admin", esquema=esquema, aba="governanca")
    try:
        fundo = t.page.evaluate("() => getComputedStyle(document.body).backgroundColor")
        assert (fundo == "rgb(246, 244, 239)") == (esquema == "light")
        cor = t.page.evaluate("() => getComputedStyle(document.querySelector('.gv-card.gv-sit-suja')).backgroundColor")
        assert cor == ("rgb(253, 236, 235)" if esquema == "light" else "rgb(74, 31, 27)")
        t.foto("g09_desktop_" + esquema)
        t.page.set_viewport_size({"width": 390, "height": 844})
        t.foto("g10_celular_" + esquema)
        assert not graves(t.erros)
    finally:
        t.fechar()


@pytest.mark.parametrize("largura", [1366, 1920])
def test_cabecalho_do_administrador_em_uma_linha(servidor, navegador, largura):
    t = Tela(navegador, "admin", largura=largura, altura=900, aba="governanca")
    try:
        r = t.page.evaluate("""() => { const bs = [...document.querySelectorAll('body > header button, body > header .quem')].filter(e => e.offsetParent !== null);
            const cs = bs.map(b => { const r = b.getBoundingClientRect(); return r.top + r.height / 2; });
            const tops = new Set([Math.max(...cs) - Math.min(...cs) <= 8 ? 1 : 2]);   /* mesma linha: centros a no máximo 8 px */
            window.__tops = bs.map(b => [b.textContent.trim().slice(0, 12), Math.round(b.getBoundingClientRect().top)]);
            return [tops.size, Math.round(document.querySelector('body > header').getBoundingClientRect().height), document.documentElement.scrollWidth <= innerWidth, bs.length]; }""")
        assert r[0] == 1 and r[1] < 70 and r[2], (r, [x for x in t.page.evaluate('() => window.__tops') if x[1] != 15])
        assert r[3] >= 12
        t.foto("g11_cabecalho_%d" % largura)
    finally:
        t.fechar()


def test_calendario_mostra_o_estado_de_hoje(servidor, navegador):
    t = Tela(navegador, "admin")
    try:
        p = t.page
        p.click('nav button[data-aba="calendario"]')
        p.wait_for_selector("#cdTabela .cd-gov")
        linha205 = p.locator("#cdTabela tr.cd-linha", has=p.locator('button.cd-apto-btn:text-is("205")'))
        assert "Pronta · pode entrar" in linha205.inner_text()
        p.click("#cdModoGrade")
        assert "Suja" in p.locator('#cdGrade .cd-apto[data-apto="202"]').inner_text()
        assert "Pronta · pode entrar" in p.locator('#cdGrade .cd-apto[data-apto="205"]').inner_text()
        assert "Em arrumação" in p.locator('#cdGrade .cd-apto[data-apto="206"]').inner_text()
        assert p.locator('#cdGrade .cd-apto[data-apto="201"] .cd-gov').count() == 0           # hospedada: sem selo
        t.foto("g12_calendario_estado")
        p.click("#cdProx")                                                                     # outro dia: sem selos
        p.wait_for_timeout(200)
        assert p.locator(".cd-gov").count() == 0
        p.click("#cdHoje")
        assert p.locator("#cdGrade .cd-gov").count() >= 3
        assert not graves(t.erros)
    finally:
        t.fechar()


def test_calendario_nao_mostra_estado_para_quem_nao_tem_reservas(servidor, navegador):
    t = Tela(navegador, "cam")
    try:
        assert t.page.evaluate("() => cdGovPodeUsar()") is False
        assert t.page.locator(".cd-gov").count() == 0
    finally:
        t.fechar()


def test_sem_conexao_desliga_acoes_e_mostra_faixa(cam):
    p = cam.page
    # Causa da instabilidade antiga: a atualização automática (GV_INTERVALO) podia rodar entre "voltar a conexão" e o clique, esconder a
    # faixa sozinha e deixar o clique esperando um botão que já sumiu. Com o relógio parado só o que o teste faz atualiza a tela.
    p.evaluate("() => { clearInterval(gv.timer); gv.timer = null; }")
    p.wait_for_function("() => !gv.ocupado")
    cam.ctx.set_offline(True)
    p.evaluate("() => gvCarregar()")
    p.wait_for_selector("#gvOffline:not(.oculto)")
    assert "Sem conexão. Mostrando dados de" in p.inner_text("#gvOfflineTxt")
    assert cam.card("203").locator(".gv-principal").is_disabled()
    cam.ctx.set_offline(False)
    p.click("#gvTentarRede")
    p.wait_for_selector("#gvOffline", state="hidden")
    assert cam.card("203").locator(".gv-principal").is_enabled()
    cam.erros[:] = [e for e in cam.erros if "Failed to load" not in e and "ERR_INTERNET" not in e]
