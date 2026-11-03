"""Base dos E2E da Operação do dia (Edge via Playwright, porta 5067, banco/instância em pasta temporária).

Só roda com POUSADA_E2E=1. Nunca toca no banco real. Screenshots em POUSADA_E2E_SHOTS (se definida).
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
PORTA = int(os.environ.get("POUSADA_E2E_PORTA", "5067"))
URL = "http://127.0.0.1:%d" % PORTA
SENHA = "senha-e2e-segura-123"
HOJE = date.today()
SHOTS = os.environ.get("POUSADA_E2E_SHOTS")
XSS = '<img src=x onerror="window.__xss=1">'
PERFIS = (("admin", "admin"), ("cam", "camareira"), ("consulta", "consulta"), ("recep", "recepcao"), ("atend", "atendente"), ("dir", "diretoria"))


def dia(n):
    return (HOJE + timedelta(days=n)).isoformat()


def br(n):
    d = HOJE + timedelta(days=n)
    return "%02d/%02d/%d" % (d.day, d.month, d.year)


# (apto, nome, entrada, saída, pessoas, pagamento, tipo, grupo, observação, extras)
SEMENTE = [
    ("201", "Ana Silva", -2, 1, 2, "pago", "socio", "", "Alergia a amendoim", "Berço"),
    ("202", "Bruno Lima", 0, 3, 2, "parcial", "convidado", "Turma Azul", "", ""),
    ("203", "Carla Souza", -3, 0, 2, "pendente", None, "", "", ""),
    ("203", "Davi Rocha", 0, 2, 2, "pousada", "socio", "", "", ""),
    ("205", XSS, -1, 2, 3, "pendente", None, "", "<b>negrito</b>", ""),
    ("Chalé A", "José Pereira", 5, 7, 2, "gratis", None, "", "", ""),
]


def ocupa_agora(i, f, hora):
    return (i < 0 < f) or (f == 0 and hora < 12) or (i == 0 and hora >= 14)


def esperado(hora):
    por_apto = {}
    for a, _n, i, f, n, *_ in SEMENTE:
        if ocupa_agora(i, f, hora):
            por_apto[a] = n
    return {"ins": sum(1 for s in SEMENTE if s[2] == 0), "outs": sum(1 for s in SEMENTE if s[3] == 0), "interditados": 1,
            "ocupados": len(por_apto), "vagos": 24 - len(por_apto), "pessoas_ocup": sum(por_apto.values())}


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("e2e_oper")
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
    for a, nome, i, f, n, p, tipo, grupo, o, extras in SEMENTE:
        con.execute("INSERT INTO reservas (a,nome,extras,n,i,f,p,o,grupo,criado,alterado,versao,tipo,diaria_centavos) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)", (a, nome, extras, n, dia(i), dia(f), p, o, grupo, agora(), agora(), tipo, 15000))
    con.execute("UPDATE governanca_unidade SET obs='Ar-condicionado barulhento' WHERE unidade='Chalé B'")      # vaga COM texto na governança
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
        try:
            self.page.wait_for_function("() => document.getElementById('quem') && document.getElementById('quem').textContent !== '' && "
                                        "document.querySelector('.aba.ativa') !== null", timeout=15000)
            if login not in ("cam",):
                self.page.wait_for_function("() => document.querySelector('#mrResumo .cd-cartao') !== null", timeout=15000)
        except Exception:
            print("FALHA NO LOGIN", login, self.page.url, self.erros, self.page.inner_text("body")[:300])   # ajuda a diagnosticar
            self.ctx.close()
            raise
        self.page.wait_for_timeout(300)

    def numeros(self, container):
        return self.page.evaluate("""(c) => Object.fromEntries([...document.querySelectorAll(c + ' .cd-cartao')].map(b =>
            [b.dataset.cat, +b.querySelector('.cd-num').textContent]))""", container)

    def foto(self, nome):
        if SHOTS:
            self.page.screenshot(path=os.path.join(SHOTS, nome + ".png"), full_page=True)

    def fechar(self):
        self.ctx.close()


def erros_graves(erros):
    return [e for e in erros if "Content Security Policy" in e or "pageerror" in e or "Refused" in e]


def hora_agora():
    return datetime.now().hour


@pytest.fixture
def admin(servidor, navegador):
    t = Tela(navegador, "admin")
    yield t
    t.fechar()


def com_perfil(navegador, login, **kw):
    return Tela(navegador, login, **kw)
