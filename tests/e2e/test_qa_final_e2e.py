"""QA final (exploratório, E2E Edge): números dos cartões x linhas das listas, em vários dias, no Mapa e no Calendário.

Não depende da hora do dia: o esperado é recalculado em Python com a hora do navegador (mesma regra: entra 14h, sai 12h).
"""
import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POUSADA_E2E_PORTA", "5071")
from base_operacao import *  # noqa: F401,F403,E402
from base_operacao import SEMENTE, Tela, dia, erros_graves, ocupa_agora  # noqa: E402

DIAS = range(-4, 9)


def esperado_dia(n, hora):
    """(ins, outs, ocupados, vagos, interditados) do dia hoje+n, por unidade."""
    un = {}
    for a, _nome, i, f, *_ in SEMENTE:
        e = un.setdefault(a, {"in": False, "out": False, "noite": False, "agora": False})
        e["in"] |= i == n
        e["out"] |= f == n
        e["noite"] |= i <= n < f
        e["agora"] |= (ocupa_agora(i - n, f - n, hora) if n == 0 else (i <= n < f))
    ocup = sum(1 for e in un.values() if e["agora"])
    return {"ins": sum(1 for e in un.values() if e["in"]), "outs": sum(1 for e in un.values() if e["out"]),
            "ocupados": ocup, "vagos": 24 - ocup, "interditados": 1}


def irpara(p, seletor, n):
    p.fill(seletor, dia(n))
    p.dispatch_event(seletor, "change")
    p.wait_for_timeout(120)


def linhas_unicas(p, tabela):
    return p.evaluate("(t) => new Set([...document.querySelectorAll(t + ' tbody tr.cd-linha')].map(tr => tr.querySelector('.cd-apto-btn').textContent.trim())).size", tabela)


def test_cartoes_do_mapa_batem_com_as_listas_em_varios_dias(admin):
    p = admin.page
    for n in DIAS:
        irpara(p, "#mrData", n)
        hora = p.evaluate("() => new Date().getHours()")
        esp = esperado_dia(n, hora)
        assert admin.numeros("#mrResumo") == esp, n
        for cat in ("ins", "outs", "interditados", "ocupados", "vagos"):
            p.click("#mrResumo .cd-cat-" + cat)
            p.wait_for_selector("#mrLista:not(.oculto)")
            assert linhas_unicas(p, "#mrTabela") == esp[cat], (n, cat)
            p.click("#mrResumo .cd-cat-" + cat)          # fecha de novo
    assert erros_graves(admin.erros) == []


def test_cartoes_do_calendario_batem_com_as_listas_em_varios_dias(admin):
    p = admin.page
    p.click('nav button[data-aba="calendario"]')
    for n in DIAS:
        irpara(p, "#cdData", n)
        hora = p.evaluate("() => new Date().getHours()")
        esp = esperado_dia(n, hora)
        assert admin.numeros("#cdResumo") == esp, n
        for cat in ("ins", "outs", "interditados", "ocupados", "vagos"):
            p.click("#cdResumo .cd-cat-" + cat)
            p.wait_for_function("(c) => document.querySelector('#cdResumo .cd-cat-' + c).classList.contains('cd-sel')", arg=cat)
            assert linhas_unicas(p, "#cdTabela") == esp[cat], (n, cat)
            assert ("Mostrando %d de %d" % (esp[cat], esp[cat])) in p.inner_text("#cdContagem") or cat in ("ins", "outs", "ocupados")
            p.click("#cdResumo .cd-cat-" + cat)
    assert erros_graves(admin.erros) == []


LONGO = "Ççãéü" * 24                      # 120 caracteres seguidos, sem espaço
JS_ESTOURO = """(sel) => { const W = window.innerWidth, r = [];
  document.querySelectorAll(sel + ' *').forEach(e => { const b = e.getBoundingClientRect();
    if (b.width > 0 && (b.right > W + 1 || b.left < -1) && getComputedStyle(e).position !== 'fixed' && !e.closest('.oculto,[hidden],.rc-barra,thead')) r.push(e.tagName + '.' + e.className + ' ' + Math.round(b.right)); });
  return {doc: document.documentElement.scrollWidth - W, itens: r.slice(0, 8)}; }"""


def api(p, metodo, url, corpo=None):
    return p.evaluate("([m, u, c]) => api(m, u, c).then(r => ({s: r.status, d: r.dados}))", [metodo, url, corpo])


def criar_longa(p, apto="206"):
    r = api(p, "POST", "/api/reservas", {"a": apto, "nome": LONGO, "extras": LONGO, "n": 2, "i": dia(-1), "f": dia(2), "p": "pendente",
                                          "o": LONGO, "grupo": LONGO, "tipo": "socio", "diaria_centavos": 99999999})
    assert r["s"] == 201, r
    rid = r["d"]["id"]
    assert api(p, "POST", "/api/reservas/%d/despesas" % rid, {"categoria": "bar", "descricao": LONGO[:80], "quantidade": 99,
                                                              "valor_unit_centavos": 10000})["s"] == 201
    assert api(p, "POST", "/api/reservas/%d/notas" % rid, {"texto": (LONGO * 3)[:300]})["s"] == 201
    return rid


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_textos_longos_no_celular_390_nao_estouram(navegador, servidor, esquema):
    t = Tela(navegador, "admin", largura=390, altura=844, esquema=esquema)
    p = t.page
    rid = criar_longa(p, "206" if esquema == "light" else "207")
    p.reload()
    p.wait_for_selector("#mrResumo .cd-cartao")
    p.click("#mrResumo .cd-cat-ocupados")
    p.wait_for_selector("#mrLista:not(.oculto)")
    assert p.evaluate(JS_ESTOURO, "#mrLista")["doc"] <= 0, "lista do Mapa"
    p.click('#mrTabela .cd-apto-btn[data-id="%d"]' % rid)
    p.wait_for_selector("#dlgResumo[open]")
    p.wait_for_selector("#rcPainel .nt-msg:empty")
    e = p.evaluate(JS_ESTOURO, "#dlgResumo")
    assert e["doc"] <= 0 and e["itens"] == [], ("resumo", e)
    p.click('#rcCartao [data-rc="despesas"]')
    p.wait_for_selector("#dlgDesp[open]")
    p.wait_for_function("() => document.getElementById('dsSituacao').textContent !== ''")
    e = p.evaluate(JS_ESTOURO, "#dlgDesp")
    assert e["doc"] <= 0 and e["itens"] == [], ("despesas", e)
    p.keyboard.press("Escape")
    p.click('#rcCartao [data-rc="editar"]')
    p.wait_for_selector("#dlg[open]")
    e = p.evaluate(JS_ESTOURO, "#dlg")
    assert e["doc"] <= 0 and e["itens"] == [], ("form", e)
    assert erros_graves(t.erros) == []
    t.fechar()


JS_CONTRASTE = """(raiz) => {
  const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
  const rgba = s => { const m = s.match(/[\d.]+/g).map(Number); return [m[0], m[1], m[2], m.length > 3 ? m[3] : 1]; };
  const mix = (f, b) => [0, 1, 2].map(i => f[i] * f[3] + b[i] * (1 - f[3]));
  const fundo = el => { const pilha = []; for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor); if (c[3] > 0) { pilha.push(c); if (c[3] === 1) break; } }
    let b = [255, 255, 255, 1]; pilha.reverse().forEach(c => { b = mix(c, b).concat(1); }); return b; };
  const ruins = [];
  document.querySelectorAll(raiz + ' *').forEach(el => {
    if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || cs.display === 'none' || el.closest('.oculto,[hidden],.so-leitor') || el.disabled) return;
    const fr = rgba(cs.color), bg = fundo(el), fg = mix(fr, bg);
    const L1 = lum(fg) + .05, L2 = lum(bg) + .05, ratio = Math.max(L1, L2) / Math.min(L1, L2);
    const grande = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.66 && +cs.fontWeight >= 700);
    if (ratio < (grande ? 3 : 4.5)) ruins.push(el.tagName + '.' + el.className + ' "' + el.textContent.trim().slice(0, 25) + '" ' + ratio.toFixed(2));
  });
  return ruins.slice(0, 12); }"""


@pytest.mark.parametrize("esquema", ["light", "dark"])
def test_contraste_das_telas_novas(navegador, servidor, esquema):
    t = Tela(navegador, "admin", largura=1280, altura=900, esquema=esquema)
    p = t.page
    p.evaluate("() => { const e = document.createElement('p'); e.id = 'qa-ruim'; e.style.cssText = 'color:#bbb;background:#fff'; e.textContent = 'texto ruim'; document.getElementById('aba-mapa').appendChild(e); }")
    assert len(p.evaluate(JS_CONTRASTE, "#aba-mapa")) == 1, "o detector de contraste precisa achar o texto ruim injetado"
    p.evaluate("() => document.getElementById('qa-ruim').remove()")
    p.click("#mrResumo .cd-cat-ocupados")
    p.wait_for_selector("#mrLista:not(.oculto)")
    assert p.evaluate(JS_CONTRASTE, "#aba-mapa") == [], "mapa + lista"
    p.click('#mrTabela .cd-apto-btn[data-id="1"]')
    p.wait_for_selector("#dlgResumo[open]")
    p.wait_for_selector("#rcPainel .nt-msg:empty")
    assert p.evaluate(JS_CONTRASTE, "#dlgResumo") == [], "resumo"
    p.click('#rcCartao [data-rc="cancelar"]')
    assert p.evaluate(JS_CONTRASTE, "#dlgResumo") == [], "resumo com painel de cancelar"
    p.keyboard.press("Escape")
    p.click('#rcCartao [data-rc="despesas"]')
    p.wait_for_selector("#dlgDesp[open]")
    p.fill("#dsDesc", "Cartão 4111 1111 1111 1111")
    p.fill("#dsQtd", "0")
    assert p.evaluate(JS_CONTRASTE, "#dlgDesp") == [], "despesas"
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgDesp').open")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgResumo').open")
    p.click('nav button[data-aba="calendario"]')
    assert p.evaluate(JS_CONTRASTE, "#aba-calendario") == [], "calendario"
    p.click('nav button[data-aba="governanca"]')
    p.wait_for_timeout(500)
    assert p.evaluate(JS_CONTRASTE, "#aba-governanca") == [], "governanca"
    t.fechar()


@pytest.mark.parametrize("login,ve_valor,ve_conta", [("recep", True, True), ("atend", True, True), ("dir", True, True), ("consulta", False, False)])
def test_valores_so_para_quem_pode_na_tela_e_na_rede(navegador, servidor, login, ve_valor, ve_conta):
    t = Tela(navegador, login, largura=1280, altura=900)
    p = t.page
    corpos = []
    p.on("response", lambda r: corpos.append((r.url, r.text())) if "/api/" in r.url and r.status == 200 else None)
    p.click("#mrResumo .cd-cat-ocupados")
    p.wait_for_selector("#mrLista:not(.oculto)")
    assert "R$" not in p.inner_text("#mrLista"), "a lista nunca traz dinheiro"
    p.click('#mrTabela .cd-apto-btn[data-id="1"]')
    p.wait_for_selector("#dlgResumo[open]")
    p.wait_for_selector("#rcPainel .nt-msg:empty")
    tela = p.inner_text("#dlgResumo")
    assert ("R$" in tela) == ve_valor, tela
    assert (p.locator('#rcCartao [data-rc="despesas"]').count() == 1) == ve_conta
    vazou = [u for u, c in corpos if ("diaria_centavos" in c or "valor_unit_centavos" in c) and not ve_valor]
    assert vazou == [], vazou
    if not ve_conta:
        assert [u for u, _ in corpos if "/despesas" in u] == []
    assert erros_graves(t.erros) == []
    t.fechar()


@pytest.mark.parametrize("login,escreve_reserva,escreve_apto,estorna", [
    ("admin", True, True, True), ("atend", True, True, True), ("recep", True, False, False), ("dir", False, False, False), ("consulta", False, False, False)])
def test_controles_de_escrita_por_perfil_no_resumo(navegador, servidor, login, escreve_reserva, escreve_apto, estorna):
    a = Tela(navegador, "admin")           # um lançamento para o estorno existir (a chave evita repetir entre os perfis)
    api(a.page, "POST", "/api/reservas/1/despesas", {"categoria": "bar", "descricao": "Agua", "quantidade": 1, "valor_unit_centavos": 500, "chave": "qa-final-estorno"})
    a.fechar()
    t = Tela(navegador, login, largura=1280, altura=900)
    p = t.page
    p.click("#mrResumo .cd-cat-ocupados")
    p.wait_for_selector("#mrLista:not(.oculto)")
    p.click('#mrTabela .cd-apto-btn[data-id="1"]')
    p.wait_for_selector("#dlgResumo[open]")
    p.wait_for_selector("#rcPainel .nt-msg:empty")
    assert (p.locator("#rcPainel .nt-novo textarea").count() == 1) == escreve_reserva
    p.click("#rcAbas button:last-child")                                  # aba Apartamento
    p.wait_for_selector("#rcPainel .nt-msg:empty")
    assert (p.locator("#rcPainel .nt-novo textarea").count() == 1) == escreve_apto
    if login in ("admin", "atend", "recep"):                              # estorno: botão só para quem pode
        p.click('#rcCartao [data-rc="despesas"]')
        p.wait_for_selector("#dlgDesp[open]")
        p.wait_for_function("() => document.getElementById('dsSituacao').textContent !== ''")
        assert (p.locator("#dsLista [data-lid]").count() >= 1) == estorna
        p.keyboard.press("Escape")
    assert erros_graves(t.erros) == []
    t.fechar()


def test_ponto_de_observacao_acende_com_nota_nova_da_reserva_e_do_apartamento(navegador, servidor):
    t = Tela(navegador, "atend", largura=1280, altura=900)
    p = t.page
    p.click("#mrResumo .cd-cat-outs")                                      # reserva 3 (Carla, 203): sem observação padrão nem extras
    p.wait_for_selector("#mrLista:not(.oculto)")
    botao = p.locator('#mrTabela button.od-acao-obs[data-rid="3"]')
    assert botao.locator(".od-ponto").count() == 0
    botao.click()
    p.wait_for_selector("#dlgNotas[open]")
    p.wait_for_selector(".nt-msg:empty")
    p.fill(".nt-novo textarea", "Pediu andar baixo")
    p.click(".nt-add")
    p.wait_for_selector(".nt-nota")
    p.keyboard.press("Escape")
    p.wait_for_function("() => !document.getElementById('dlgNotas').open")
    p.wait_for_selector('#mrTabela button.od-acao-obs[data-rid="3"] .od-ponto')       # sem esperar o relógio de 8 s
    assert "há observações" in p.locator('#mrTabela button.od-acao-obs[data-rid="3"]').get_attribute("aria-label")
    assert erros_graves(t.erros) == []
    t.fechar()


@pytest.mark.parametrize("h,m", [(0, 0), (11, 59), (12, 0), (13, 59), (14, 0), (23, 59)])
def test_cartoes_de_hoje_nas_horas_de_borda_com_relogio_do_navegador_fixo(navegador, servidor, h, m):
    """Relógio do navegador fixado: 11:59 (ainda ocupa quem sai), 12:00 (já livre), 13:59 (ainda não entrou), 14:00 (entra)."""
    from datetime import datetime as _dt
    ctx = navegador.new_context(viewport={"width": 1400, "height": 1000})
    p = ctx.new_page()
    hoje = _dt.now().replace(hour=h, minute=m, second=0, microsecond=0)
    p.clock.install(time=hoje)
    p.goto(URL + "/login")
    p.fill("#login", "admin")
    p.fill("#senha", SENHA)
    p.click("#btnEntrar")
    p.wait_for_selector("#mrResumo .cd-cartao")
    p.wait_for_timeout(300)
    got = p.evaluate("() => Object.fromEntries([...document.querySelectorAll('#mrResumo .cd-cartao')].map(b => [b.dataset.cat, +b.querySelector('.cd-num').textContent]))")
    lista = p.evaluate("() => api('GET', '/api/reservas').then(r => r.dados)")      # esperado recalculado em Python com as reservas que existem agora
    from datetime import date as _d
    desl = lambda iso: (_d.fromisoformat(iso) - HOJE).days
    ocup = {r["a"] for r in lista if ocupa_agora(desl(r["i"]), desl(r["f"]), h)}
    assert got["ocupados"] == len(ocup) and got["vagos"] == 24 - len(ocup), (h, m, got)
    assert got["ins"] == len({r["a"] for r in lista if desl(r["i"]) == 0}) and got["outs"] == len({r["a"] for r in lista if desl(r["f"]) == 0})
    p.click("#mrResumo .cd-cat-ocupados")
    p.wait_for_selector("#mrLista:not(.oculto)")
    assert p.locator("#mrTabela tbody tr.cd-linha").count() == got["ocupados"]
    ctx.close()


def test_duplo_clique_lanca_anota_e_estorna_uma_vez_so(navegador, servidor):
    t = Tela(navegador, "atend", largura=1280, altura=900)
    p = t.page
    p.click("#mrResumo .cd-cat-ins")
    p.wait_for_selector("#mrLista:not(.oculto)")
    p.click('#mrTabela .cd-apto-btn[data-id="4"]')                          # Davi, 203
    p.wait_for_selector("#dlgResumo[open]")
    p.wait_for_selector("#rcPainel .nt-msg:empty")
    p.fill(".nt-novo textarea", "Duplo clique na nota")
    p.dblclick(".nt-add")
    p.wait_for_selector(".nt-nota")
    p.wait_for_timeout(600)
    assert p.locator(".nt-nota .nt-texto", has_text="Duplo clique na nota").count() == 1
    p.click('#rcCartao [data-rc="despesas"]')
    p.wait_for_selector("#dlgDesp[open]")
    p.wait_for_function("() => document.getElementById('dsSituacao').textContent !== ''")
    p.fill("#dsDesc", "Suco duplo")
    p.fill("#dsQtd", "1")
    p.fill("#dsValor", "7,50")
    p.dblclick("#dsLancar")
    p.wait_for_selector("#dsLista tr")
    p.wait_for_timeout(600)
    assert p.locator("#dsLista tr", has_text="Suco duplo").count() == 1
    p.click("#dsLista [data-lid]")
    p.fill("#dsMotivo", "lancado em duplicidade")
    p.dblclick("#dsConfirmarEstorno")
    p.wait_for_selector("#dsLista tr.ds-s-estorno")
    p.wait_for_timeout(600)
    assert p.locator("#dsLista tr.ds-s-estorno").count() == 1
    assert erros_graves(t.erros) == []
    t.fechar()
