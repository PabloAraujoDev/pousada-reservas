"""E2E no navegador real (Edge via Playwright): "Mapa da reserva" (faixa de resumo, meses, disponibilidade) e "Calendário" (dia).

Fora da suíte padrão: só roda com  POUSADA_E2E=1 python -m pytest tests/e2e -q  (e se o playwright estiver instalado).
Sobe uma instância PRÓPRIA (porta 5062 (5060 e 5061 são bloqueadas pelo Edge como portas inseguras), banco/backup/instância em pasta temporária); nunca toca no banco real.
Screenshots vão para a pasta indicada em POUSADA_E2E_SHOTS (se definida).
"""
import os
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
PORTA = 5062
URL = "http://127.0.0.1:%d" % PORTA
SENHA = "senha-e2e-segura-123"
HOJE = date.today()
SHOTS = os.environ.get("POUSADA_E2E_SHOTS")
XSS = '<img src=x onerror="window.__xss=1">'


def dia(n):
    return (HOJE + timedelta(days=n)).isoformat()


def br(n):
    d = HOJE + timedelta(days=n)
    return "%02d/%02d/%d" % (d.day, d.month, d.year)


# (apto, nome, entrada, saída, pessoas, pagamento, tipo, grupo)
SEMENTE = [
    ("201", "Ana Silva", -2, 1, 2, "pago", "socio", ""),
    ("202", "Bruno Lima", 0, 3, 2, "parcial", "convidado", "Turma Azul"),
    ("203", "Carla Souza", -3, 0, 2, "pendente", None, ""),
    ("203", "Davi Rocha", 0, 2, 2, "pousada", "socio", ""),
    ("205", XSS, -1, 2, 3, "pendente", None, ""),
    ("Chalé A", "José Pereira", 5, 7, 2, "gratis", None, ""),
]


def ocupa_agora(i, f, hora):
    """Mesma regra da tela para HOJE: dorme, ou sai hoje antes das 12h, ou entra hoje depois das 14h."""
    return (i < 0 < f) or (f == 0 and hora < 12) or (i == 0 and hora >= 14)


def esperado(hora):
    por_apto = {}
    for a, _n, i, f, n, *_ in SEMENTE:
        if ocupa_agora(i, f, hora):
            por_apto[a] = n
    noite = {a for a, _n, i, f, *_ in SEMENTE if i <= 0 < f}
    return {"ins": sum(1 for s in SEMENTE if s[2] == 0), "outs": sum(1 for s in SEMENTE if s[3] == 0), "interditados": 1,
            "ocupados": len(por_apto), "vagos": 24 - len(por_apto), "noite": len(noite), "livres_noite": 24 - len(noite)}


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("e2e_cal")
    env = dict(os.environ, POUSADA_DB=str(pasta / "e2e.db"), POUSADA_INSTANCIA=str(pasta / "inst"),
               POUSADA_BACKUP_DIR=str(pasta / "bk"), POUSADA_PORTA=str(PORTA), POUSADA_HOST="127.0.0.1")
    from pousada import config
    from pousada.db import conectar, iniciar_banco
    from pousada.regras import agora
    from pousada.usuarios import criar_usuario
    iniciar_banco(env["POUSADA_DB"], config.PASTA_MIGRACOES)
    con = conectar(env["POUSADA_DB"])
    for login, papel in (("admin", "admin"), ("cam", "camareira"), ("consulta", "consulta"), ("recep", "recepcao")):
        criar_usuario(con, login, login.capitalize(), SENHA, papel)
    for a, nome, i, f, n, p, tipo, grupo in SEMENTE:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,tipo,diaria_centavos) "
                    "VALUES (?,?,'',?,?,?,?,'',?,?,?,1,?,?)", (a, nome, n, dia(i), dia(f), p, grupo, agora(), agora(), tipo, 15000))
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
    from pousada.db import conectar
    con = conectar(servidor["POUSADA_DB"])
    con.execute("UPDATE usuarios SET preferencias='{}'")
    con.close()


class Tela:
    def __init__(self, navegador, login, largura=1400, altura=1000, esquema="light"):
        self.ctx = navegador.new_context(viewport={"width": largura, "height": altura}, color_scheme=esquema)
        self.page = self.ctx.new_page()
        self.erros = []
        self.page.on("console", lambda m: self.erros.append(m.text) if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.erros.append("pageerror: %s" % e))
        self.page.goto(URL + "/login")
        self.page.fill("#login", login)
        self.page.fill("#senha", SENHA)
        self.page.click("#btnEntrar")
        self.pronta()

    def pronta(self):
        self.page.wait_for_function("() => document.getElementById('quem') && document.getElementById('quem').textContent !== '' && "
                                    "document.querySelector('.aba.ativa') !== null")
        self.page.wait_for_function("() => document.querySelector('#mrResumo .cd-cartao') !== null || "
                                    "document.querySelector('nav button[data-aba=\"governanca\"].ativo') !== null")
        self.page.wait_for_timeout(300)

    def recarregar(self):
        self.page.reload()
        self.pronta()

    def ir(self, aba):
        self.page.click('nav button[data-aba="%s"]' % aba)

    def numeros(self, container):
        """{categoria: número no centro da rosca} lido do texto do SVG (e o rótulo acessível)."""
        return self.page.evaluate("""(c) => Object.fromEntries([...document.querySelectorAll(c + ' .cd-cartao')].map(b =>
            [b.dataset.cat, +b.querySelector('.cd-num').textContent]))""", container)

    def foto(self, nome):
        if SHOTS:
            self.page.screenshot(path=os.path.join(SHOTS, nome + ".png"), full_page=True)

    def fechar(self):
        self.ctx.close()


def erros_graves(erros):
    return [e for e in erros if "Content Security Policy" in e or "pageerror" in e or "Refused" in e]


@pytest.fixture
def admin(servidor, navegador):
    t = Tela(navegador, "admin")
    yield t
    t.fechar()


def hora_agora():
    return datetime.now().hour


# ------------------------------------------------------------------ Mapa da reserva (linha do tempo + faixa)

def test_mapa_da_reserva_tem_faixa_meses_e_disponibilidade(admin):
    p = admin.page
    hora = hora_agora()
    assert p.inner_text('nav button[data-aba="mapa"]') == "Mapa da reserva"
    assert p.inner_text('nav button[data-aba="calendario"]') == "Calendário"
    e = esperado(hora)
    assert admin.numeros("#mrResumo") == {"ins": e["ins"], "outs": e["outs"], "interditados": 1, "ocupados": e["ocupados"], "vagos": e["vagos"]}
    assert p.input_value("#mrData") == HOJE.isoformat()
    textos = p.locator("#mrResumo .cd-ocup").inner_text()
    assert "Ocupação momentânea" in textos and "Ocupação prevista" in textos
    assert ("%d,%d%%" % divmod(round(e["noite"] / 24 * 1000), 10)).replace(",0%", "%") in textos          # prevista (noite)
    assert "Previstos: %d" % e["noite"] in p.locator("#mrResumo .cd-cat-ocupados").inner_text()
    # rótulos acessíveis das roscas
    assert p.get_attribute("#mrResumo .cd-cat-vagos svg", "aria-label") == "Vagos: %d de 24 apartamentos" % e["vagos"]
    assert p.get_attribute("#mrResumo .cd-cat-interditados svg", "aria-label") == "Interditados: 1 de 25 apartamentos"
    # linha de meses e disponibilidade (número escrito em todos os dias; hoje = 24 - noite)
    assert p.locator("#mapa .linha.mes .mes-seg").count() >= 1
    assert p.locator("#mapa .linha.disp .d").count() == 14
    primeiro = p.locator("#mapa .linha.disp .d b").first.inner_text()
    assert int(primeiro) == e["livres_noite"]
    assert p.locator("#mapa .linha.disp .d b").all_inner_texts() == [x for x in p.locator("#mapa .linha.disp .d b").all_inner_texts() if x.isdigit()]
    classes = p.locator("#mapa .linha.disp .d").first.get_attribute("class")
    assert "disp-alta" in classes
    admin.foto("20_mapa_da_reserva_claro")
    assert not erros_graves(admin.erros), admin.erros


def test_resumo_do_mapa_troca_de_dia_e_cartao_leva_ao_calendario(admin):
    p = admin.page
    p.click("#mrProx")
    assert p.input_value("#mrData") == dia(1)
    assert "só existe para hoje" in p.locator("#mrResumo .cd-ocup").inner_text()      # momentânea só para hoje
    n = admin.numeros("#mrResumo")
    assert n["ocupados"] == 3 and n["vagos"] == 21               # noite de amanhã: 202, 203 (Davi), 205 (201 sai)
    assert n["outs"] == 1 and n["ins"] == 0                      # 201 sai amanhã
    p.click("#mrHoje")
    assert p.input_value("#mrData") == HOJE.isoformat()
    p.click("#mrResumo .cd-cat-outs")
    assert p.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-mapa"          # a lista abre no lugar (painel embutido)
    assert p.locator("#mrLista").is_visible()
    p.click("#mrListaCal")                                                                    # e o link leva ao Calendário
    assert p.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-calendario"
    assert p.get_attribute('#cdResumo .cd-cat-outs', "aria-pressed") == "true"
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 1


def test_mapa_continua_arrastavel_com_as_linhas_novas(admin):
    p = admin.page
    barra = p.locator('.barra-res:has-text("Turma Azul")')
    b = barra.bounding_box()
    x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    celula = p.locator('.d[data-apto="204"][data-dia="%s"]' % dia(1)).bounding_box()
    p.mouse.move(x, y)
    p.mouse.down()
    p.mouse.move(x, celula["y"] + celula["height"] / 2, steps=12)
    p.mouse.up()
    p.wait_for_function("() => document.getElementById('toast').textContent.includes('movida')")
    movida = p.evaluate("() => fetch('/api/reservas', {credentials:'same-origin'}).then(r => r.json())")
    assert [r["a"] for r in movida if r["nome"] == "Bruno Lima"] == ["204"]
    # desfaz para os outros testes
    r = [x for x in movida if x["nome"] == "Bruno Lima"][0]
    csrf = p.evaluate("() => sessao.csrf")
    p.evaluate("""([r, csrf]) => fetch('/api/reservas/' + r.id, {method:'PUT', credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body: JSON.stringify({a:'202', nome:r.nome, extras:r.extras||'', n:r.n,
        i:r.i, f:r.f, p:r.p, o:r.o||'', grupo:r.grupo||'', tipo:r.tipo, versao:r.versao})})""", [r, csrf])
    p.wait_for_timeout(300)


# ------------------------------------------------------------------ Calendário

def abrir_calendario(t):
    t.ir("calendario")
    t.page.wait_for_selector("#cdTabela tbody tr")


def test_calendario_cartoes_tabela_e_filtros(admin):
    p = admin.page
    hora = hora_agora()
    e = esperado(hora)
    abrir_calendario(admin)
    assert admin.numeros("#cdResumo") == {"ins": e["ins"], "outs": e["outs"], "interditados": 1, "ocupados": e["ocupados"], "vagos": e["vagos"]}
    assert e["ocupados"] + e["vagos"] == 24
    # visão padrão em blocos: chegam (2), saem (1), ficam (201 e 205)
    blocos = p.locator("#cdTabela .cd-bloco-tit th").all_inner_texts()
    assert blocos == ["Chegam hoje (2)", "Saem hoje (1)", "Ocupados (ficam) (2)"]
    assert "Troca" in p.locator("#cdTabela").inner_text()                           # 203 sai e entra no mesmo dia
    # o nome malicioso aparece como texto e não vira elemento
    assert p.locator("#cdTabela img").count() == 0 and p.evaluate("() => window.__xss") is None
    assert XSS in p.locator("#cdTabela").inner_text()
    for cat, qtd in (("ins", e["ins"]), ("outs", e["outs"]), ("interditados", 1), ("ocupados", e["ocupados"]), ("vagos", e["vagos"])):
        p.click("#cdResumo .cd-cat-" + cat)
        assert p.get_attribute("#cdResumo .cd-cat-" + cat, "aria-pressed") == "true"
        assert p.locator("#cdTabela tbody tr.cd-linha").count() == qtd, cat
        assert p.locator("#cdTabela .cd-bloco-tit").count() == 0
        assert "Mostrando %d de %d" % (qtd, qtd) in p.inner_text("#cdContagem")
    p.click("#cdResumo .cd-cat-vagos")                                              # segundo clique remove o filtro
    assert p.get_attribute("#cdResumo .cd-cat-vagos", "aria-pressed") == "false"
    assert p.locator("#cdLimpar").is_hidden()
    # pesquisa: sem acento, várias palavras
    p.fill("#cdBusca", "bruno")
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 1
    p.fill("#cdBusca", "turma azul")
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 1
    p.fill("#cdBusca", "pousada")                                                   # texto do pagamento
    assert "Davi Rocha" in p.inner_text("#cdTabela")
    p.fill("#cdBusca", "zzz")
    assert "Nenhuma reserva corresponde à busca" in p.inner_text("#cdTabela")
    p.click("#cdLimpar")
    assert p.input_value("#cdBusca") == "" and p.locator("#cdLimpar").is_hidden()
    p.click("#cdResumo .cd-cat-ins")
    p.fill("#cdBusca", "silva")
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 0
    p.fill("#cdBusca", "davi")
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 1
    admin.foto("21_calendario_claro")
    assert not erros_graves(admin.erros), admin.erros


def test_calendario_escolher_dia_e_mes(admin):
    p = admin.page
    abrir_calendario(admin)
    mes = p.inner_text("#cdMesTitulo")
    assert p.locator("#cdMes .cd-dia").count() == 42
    assert p.locator("#cdMes .cd-dia.cd-hoje").count() == 1 and p.get_attribute("#cdMes .cd-dia.cd-sel", "aria-pressed") == "true"
    # todo dia traz o número de livres escrito e no rótulo acessível
    assert all(t.strip().isdigit() for t in p.locator("#cdMes .cd-dia-liv b").all_inner_texts())
    assert "apartamento" in p.get_attribute("#cdMes .cd-dia.cd-hoje", "aria-label")
    hoje_livres = p.locator("#cdMes .cd-dia.cd-hoje .cd-dia-liv b").inner_text()
    assert int(hoje_livres) == esperado(hora_agora())["livres_noite"]
    amanha = dia(1)
    p.click('#cdMes .cd-dia[data-dia="%s"]' % amanha)
    assert p.input_value("#cdData") == amanha
    assert p.locator("#cdTabela .cd-bloco-tit th").all_inner_texts()[:1] == ["Saem hoje (1)"] or "Saem" in p.inner_text("#cdTabela")
    n = admin.numeros("#cdResumo")
    assert n["outs"] == 1 and n["ins"] == 0
    assert "só existe para hoje" in p.inner_text("#cdResumo .cd-ocup")
    p.click("#cdProx")
    assert p.input_value("#cdData") == dia(2)
    p.click("#cdAnt"); p.click("#cdAnt"); p.click("#cdAnt")
    assert p.input_value("#cdData") == dia(-1)
    p.click("#cdMesProx")
    assert p.inner_text("#cdMesTitulo") != mes
    p.click("#cdMesHoje")
    assert p.inner_text("#cdMesTitulo") == mes and p.input_value("#cdData") == HOJE.isoformat()
    p.click("#cdHoje")
    assert p.input_value("#cdData") == HOJE.isoformat()
    assert not erros_graves(admin.erros), admin.erros


def test_modo_mapa_de_apartamento_cores_e_cliques(admin):
    p = admin.page
    abrir_calendario(admin)
    p.click("#cdModoGrade")
    p.wait_for_selector("#cdGrade .cd-apto")
    assert p.locator("#cdTabela").is_hidden()
    assert p.get_attribute("#cdModoGrade", "aria-pressed") == "true"
    est = p.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#cdGrade .cd-apto')].map(e => [e.dataset.apto,
        [...e.classList].find(c => c.startsWith('cd-est-'))]))""")
    assert len(est) == 25
    assert est["104"] == "cd-est-interditada" and est["203"] == "cd-est-troca" and est["202"] == "cd-est-chegando"
    assert est["201"] == "cd-est-ocupada" and est["205"] == "cd-est-ocupada" and est["301"] == "cd-est-vaga"
    legenda = p.inner_text("#cdLegenda")
    assert "Interditada 1" in legenda.replace("\n", " ") and "Troca hoje 1" in legenda.replace("\n", " ")
    soma = sum(int(x) for x in p.locator("#cdLegenda .cd-leg b").all_inner_texts())
    assert soma == 25
    assert p.locator('#cdGrade .cd-apto[data-apto="203"] .cd-hosp').count() == 2        # quem sai e quem entra
    admin.foto("22_mapa_de_apartamento_claro")
    p.click('#cdGrade .cd-apto[data-apto="201"] .cd-hosp')                               # ocupada: abre o Resumo da reserva
    p.wait_for_selector("#dlgResumo[open]")
    p.click('#rcCartao [data-rc="editar"]')
    p.wait_for_selector("#dlg[open]")
    assert p.inner_text("#dlgTitulo") == "Editar reserva" and p.input_value("#fnome") == "Ana Silva"
    p.click("#btnCancelar")
    p.evaluate("() => document.getElementById('dlgResumo').close()")
    p.click('#cdGrade .cd-apto[data-apto="301"] .cd-hosp-vaga')                          # vaga: nova reserva com unidade e data do dia
    p.wait_for_selector("#dlg[open]")
    assert p.inner_text("#dlgTitulo") == "Nova reserva" and p.input_value("#fa") == "301" and p.input_value("#fi") == HOJE.isoformat()
    p.click("#btnCancelar")
    assert p.locator('#cdGrade .cd-apto[data-apto="104"] button').count() == 0           # interditada: nada para clicar
    p.click("#cdResumo .cd-cat-ins")                                                     # filtro apaga o que não combina
    assert p.locator("#cdGrade .cd-apagado").count() == 23
    assert not erros_graves(admin.erros), admin.erros


def test_linha_da_tabela_abre_a_reserva_e_vaga_abre_nova(admin):
    p = admin.page
    abrir_calendario(admin)
    p.click('#cdTabela .cd-apto-btn[aria-label*="Bruno Lima"]')
    p.wait_for_selector("#dlgResumo[open]")
    p.click('#rcCartao [data-rc="editar"]')
    p.wait_for_selector("#dlg[open]")
    assert p.input_value("#fnome") == "Bruno Lima"
    p.click("#btnCancelar")
    p.evaluate("() => document.getElementById('dlgResumo').close()")
    p.click("#cdResumo .cd-cat-vagos")
    p.click('#cdTabela .cd-apto-btn[data-apto="302"]')
    p.wait_for_selector("#dlg[open]")
    assert p.inner_text("#dlgTitulo") == "Nova reserva" and p.input_value("#fa") == "302"
    p.click("#btnCancelar")


def test_polling_de_8s_nao_perde_dia_filtro_pesquisa_nem_foco(admin):
    p = admin.page
    abrir_calendario(admin)
    p.click('#cdMes .cd-dia[data-dia="%s"]' % dia(1))
    p.click("#cdResumo .cd-cat-outs")
    p.click("#cdBusca")
    p.keyboard.type("ana")
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 1
    p.wait_for_timeout(9500)                                                            # passa pelo menos um ciclo do polling
    assert p.input_value("#cdData") == dia(1) and p.input_value("#cdBusca") == "ana"
    assert p.get_attribute("#cdResumo .cd-cat-outs", "aria-pressed") == "true"
    assert p.evaluate("() => document.activeElement.id") == "cdBusca"
    p.click("#cdResumo .cd-cat-outs")                                                   # foco num cartão sobrevive ao redesenho
    p.focus("#cdResumo .cd-cat-ins")
    p.wait_for_timeout(9500)
    assert p.evaluate("() => document.activeElement.dataset.foco") == "cat:ins"
    assert not erros_graves(admin.erros), admin.erros


# ------------------------------------------------------------------ perfis

def test_consulta_ve_o_calendario_so_leitura(servidor, navegador):
    t = Tela(navegador, "consulta")
    try:
        abrir_calendario(t)
        assert t.page.locator("#btnNova").is_hidden()
        t.page.click("#cdModoGrade")
        assert t.page.locator("#cdGrade .cd-hosp-vaga").count() == 0                     # vaga sem botão de reservar
        assert "Sem hóspede" in t.page.inner_text('#cdGrade .cd-apto[data-apto="301"]')
        t.page.click("#cdModoLista"); t.page.click("#cdResumo .cd-cat-vagos")
        assert t.page.locator("#cdTabela button.cd-apto-btn").count() == 0
        t.page.click("#cdResumo .cd-cat-ins")
        t.page.click('#cdTabela .cd-apto-btn[aria-label*="Bruno Lima"]')
        t.page.wait_for_selector("#dlgResumo[open]")
        assert t.page.locator('#dlgResumo [data-rc="editar"]').count() == 0            # consulta: Resumo só leitura
        assert "R$" not in t.page.inner_text("#dlgResumo")                               # nunca vê valor
        t.foto("23_consulta")
        assert not erros_graves(t.erros), t.erros
    finally:
        t.fechar()


def test_camareira_nao_ve_os_menus_novos_nem_nomes(servidor, navegador):
    t = Tela(navegador, "cam")
    try:
        for aba in ("mapa", "calendario"):
            assert t.page.locator('nav button[data-aba="%s"]' % aba).is_hidden()
        assert t.page.locator("#mrResumo .cd-cartao").count() == 0
        assert t.page.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-governanca"
        assert not erros_graves(t.erros), t.erros
    finally:
        t.fechar()


# ------------------------------------------------------------------ personalização e cabeçalho

def test_ocultar_calendario_pelo_personalizar_persiste_e_aba_inicial(admin):
    p = admin.page
    p.click("#btnPersonalizar")
    p.wait_for_selector("#dlgPref[open]")
    assert "Calendário" in p.locator("#prefMenus label").all_inner_texts()[1]
    p.select_option("#prefAba", "calendario")
    p.click("#prefSalvar")
    p.wait_for_selector("#dlgPref", state="hidden")
    admin.recarregar()
    assert p.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-calendario"
    p.click("#btnPersonalizar")
    p.wait_for_selector("#dlgPref[open]")
    p.select_option("#prefAba", "")
    p.locator('#prefMenus .prefMenu[data-menu="calendario"]').set_checked(False)
    p.click("#prefSalvar")
    p.wait_for_selector("#dlgPref", state="hidden")
    assert p.locator('nav button[data-menu="calendario"]').is_hidden()
    admin.recarregar()
    assert p.locator('nav button[data-menu="calendario"]').is_hidden()
    assert p.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-mapa"
    # clique num indicador do mapa com o Calendário oculto não troca de aba
    p.click("#mrResumo .cd-cat-ins")
    assert p.evaluate("() => document.querySelector('.aba.ativa').id") == "aba-mapa"


@pytest.mark.parametrize("largura", [1366, 1920])
def test_cabecalho_em_uma_linha_com_os_novos_menus(servidor, navegador, largura):
    t = Tela(navegador, "admin", largura=largura, altura=900)
    try:
        m = t.page.evaluate("""() => {
            const h1 = document.querySelector('header h1').getBoundingClientRect(), cy = h1.top + h1.height / 2;
            const itens = [...document.querySelectorAll('header nav > *')].filter(e => e.offsetParent !== null)
                .map(e => Math.abs(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2 - cy));
            return {n: itens.length, max: Math.max(...itens), altura: document.querySelector('header').getBoundingClientRect().height,
                    rolagem: document.documentElement.scrollWidth <= document.documentElement.clientWidth};
        }""")
        assert m["n"] >= 14 and m["max"] < 14 and m["altura"] < 70 and m["rolagem"], m
        t.foto("24_cabecalho_%d" % largura)
    finally:
        t.fechar()


# ------------------------------------------------------------------ tema escuro, contraste, celular, impressão

CONTRASTE = """() => {
  const lum = (rgb) => { const v = rgb.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126*v[0] + 0.7152*v[1] + 0.0722*v[2]; };
  const cor = (s) => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
  const piores = [];
  const alvos = [...document.querySelectorAll('#mapa .linha.disp .d, #cdMes .cd-dia-liv, #cdMes .cd-dia-n, .cd-apto-btn, .cd-sit, .cd-apto-est, .cd-ocup-num, .cd-cartao-sub, .cd-hosp')]
    .filter(e => e.offsetParent !== null);
  for (const e of alvos) {
    const cs = getComputedStyle(e);
    let fundo = null, n = e;
    while (n && !fundo) { const b = getComputedStyle(n).backgroundColor; if (b && !/rgba\\(.*, 0\\)|transparent/.test(b)) fundo = b; n = n.parentElement; }
    if (!fundo) fundo = 'rgb(255,255,255)';
    const l1 = lum(cor(cs.color)), l2 = lum(cor(fundo)), r = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    piores.push([r, e.className.toString().slice(0, 40), cs.color, fundo]);
  }
  piores.sort((a, b) => a[0] - b[0]);
  return piores.slice(0, 3);
}"""


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_contraste_aa_e_fotos_nos_dois_temas(servidor, navegador, esquema):
    t = Tela(navegador, "admin", esquema=esquema)
    try:
        p = t.page
        p.wait_for_selector("#mapa .linha.disp")
        for r in p.evaluate(CONTRASTE):
            assert r[0] >= 4.5, ("mapa", esquema, r)
        t.foto("30_mapa_%s" % esquema)
        abrir_calendario(t)
        for r in p.evaluate(CONTRASTE):
            assert r[0] >= 4.5, ("calendario", esquema, r)
        t.foto("31_calendario_%s" % esquema)
        p.click("#cdModoGrade")
        for r in p.evaluate(CONTRASTE):
            assert r[0] >= 4.5, ("grade", esquema, r)
        t.foto("32_grade_%s" % esquema)
        assert not erros_graves(t.erros), t.erros
    finally:
        t.fechar()


def test_celular_sem_estourar_a_pagina(servidor, navegador):
    t = Tela(navegador, "admin", largura=390, altura=844)
    try:
        p = t.page
        sem_rolagem = "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        assert p.evaluate(sem_rolagem)
        t.foto("40_mapa_celular")
        abrir_calendario(t)
        assert p.evaluate(sem_rolagem)
        t.foto("41_calendario_celular")
        cartoes = p.evaluate("() => [...document.querySelectorAll('#cdResumo .cd-cartao')].map(b => Math.round(b.getBoundingClientRect().top))")
        assert len(set(cartoes)) >= 2                                                    # os cartões quebram em linhas
        w = p.evaluate("() => [document.querySelector('#cdListaWrap').clientWidth, document.querySelector('#cdListaWrap').scrollWidth]")
        assert w[1] <= w[0]                                                              # no celular a lista vira cartões empilhados (sem rolagem lateral)
        p.click("#cdModoGrade")
        assert p.evaluate(sem_rolagem)
        t.foto("42_grade_celular")
    finally:
        t.fechar()


def test_impressao_mostra_so_a_lista_com_cabecalho(admin):
    p = admin.page
    abrir_calendario(admin)
    p.click("#cdResumo .cd-cat-outs")
    p.evaluate("() => document.body.classList.add('imp-calendario')")
    p.emulate_media(media="print")
    assert p.inner_text("#cdCabImp") == "Mapa da reserva - %s" % br(0)
    assert p.locator("#cdCabImp").is_visible() and p.locator("#cdTabela").is_visible()
    assert p.locator("#cdResumo").is_hidden() and p.locator("#cdGrade").is_hidden() and p.locator("header").is_hidden()
    assert p.locator("#aba-camareiras").is_hidden() and p.locator("#aba-mapa").is_hidden() and p.locator("#aba-folha").is_hidden()
    assert "Filtro: Check-outs" in p.inner_text("#cdSubImp")
    assert p.locator("#cdTabela tbody tr.cd-linha").count() == 1
    p.emulate_media(media="screen")
    p.evaluate("() => document.body.classList.remove('imp-calendario')")
    assert p.locator("#cdCabImp").is_hidden()
