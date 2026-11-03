"""E2E (Edge): Despesas por perfil, extrato A4, celular 390 px, temas claro/escuro e atualização de 8 s. Porta 5068."""
from base_despesas import *  # noqa: F401,F403
from base_despesas import (Tela, abrir_despesas, abrir_lista, botao_despesas, erros_graves, lancar_pela_tela, preencher)


def semear(p, desc="Item de apoio", cat="bar", unit=900):
    """Lança direto pela API da própria página (garante ao menos uma linha na conta aberta)."""
    return p.evaluate("""([rid, d, c, u]) => api('POST', '/api/reservas/' + rid + '/despesas',
        {categoria: c, descricao: d, quantidade: 1, valor_unit_centavos: u, chave: 'sem-' + Math.random().toString(16).slice(2)})
        .then(r => r.status)""", [p.evaluate("() => reservas.filter(r => r.nome === 'Ana Silva')[0].id"), desc, cat, unit])


def test_recepcao_lanca_mas_nao_estorna(navegador, servidor):
    t = Tela(navegador, "recep")
    p = t.page
    semear(p, "Lanche da recepção")
    abrir_despesas(p, "ocupados", "Ana Silva")
    assert p.is_visible("#dsForm") and p.locator("#dsLista .ds-estornar").count() == 0
    assert "R$ 150,00 x 3 noites" in p.inner_text("#dsTotais")           # recepção tem valores.ver
    assert erros_graves(t.erros) == []
    t.fechar()


def test_diretoria_so_ve(navegador, servidor):
    t = Tela(navegador, "dir")
    p = t.page
    abrir_despesas(p, "ocupados", "Ana Silva")
    assert not p.is_visible("#dsForm") and p.locator("#dsLista .ds-estornar").count() == 0
    assert p.locator("#dsLista tr").count() >= 1
    assert p.evaluate("() => document.activeElement.id") == "dsTit"
    t.foto("despesas_03_diretoria_somente_leitura")
    assert erros_graves(t.erros) == []
    t.fechar()


def test_consulta_e_camareira_sem_acesso(navegador, servidor):
    t = Tela(navegador, "consulta")
    p = t.page
    abrir_lista(p, "ocupados")
    assert p.locator("button.od-acao-despesas").count() == 0 and p.locator("button.od-acao-info").count() > 0
    assert p.evaluate("() => api('GET', '/api/reservas/1/despesas').then(r => r.status)") == 403
    assert p.evaluate("() => api('GET', '/api/reservas').then(r => JSON.stringify(r.dados))").count("tem_despesa") == 0
    t.fechar()
    c = Tela(navegador, "cam")
    assert c.page.evaluate("() => sessao.permissoes.some(x => x.indexOf('despesas.') === 0)") is False
    assert c.page.evaluate("() => api('POST', '/api/reservas/1/despesas', {}).then(r => r.status)") == 403
    c.fechar()


def test_extrato_a4_so_o_dialogo(admin):
    p = admin.page
    semear(p, "Item para o extrato")
    abrir_despesas(p, "ocupados", "Ana Silva")
    p.evaluate("() => { window.__imp = []; window.print = () => window.__imp.push(document.body.classList.contains('imp-extrato')); }")
    p.click("#dsImprimir")
    assert p.evaluate("() => window.__imp") == [True] and p.evaluate("() => document.body.classList.contains('imp-extrato')") is False
    assert "Extrato parcial, conta aberta" in p.inner_text("#dsImpEstado") or "Extrato parcial" in p.text_content("#dsImpEstado")
    p.evaluate("() => document.body.classList.add('imp-extrato')")
    p.emulate_media(media="print")
    vis = p.evaluate("""() => { const v = s => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none'; };
        return {dlg: v('#dlgDesp'), cab: v('#dlgDesp .ds-imp-cab'), form: v('#dsForm'), botoes: v('#dlgDesp .ds-rodape .acoes'),
                estornar: v('#dlgDesp .ds-estornar'), header: v('header'), ass: v('#dlgDesp .ds-imp-ass'), tabela: v('#dsTabela')}; }""")
    assert vis == {"dlg": True, "cab": True, "form": False, "botoes": False, "estornar": False, "header": False, "ass": True, "tabela": True}
    pdf = p.pdf(format="A4", prefer_css_page_size=True)
    assert pdf[:4] == b"%PDF" and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type/Page") >= 1
    if SHOTS:
        open(os.path.join(SHOTS, "extrato_a4.pdf"), "wb").write(pdf)
    p.evaluate("() => document.body.classList.remove('imp-extrato')")
    # as outras impressões não são afetadas: sem a classe, o diálogo de despesas continua oculto na impressão
    assert p.evaluate("() => getComputedStyle(document.querySelector('#dlgDesp')).display") == "none"
    p.emulate_media(media="screen")
    assert erros_graves(admin.erros) == []


def test_celular_390_tela_cheia_sem_rolagem_lateral(navegador, servidor):
    t = Tela(navegador, "admin", largura=390, altura=800)
    p = t.page
    semear(p, "Item de celular")
    abrir_lista(p, "ocupados")
    p.locator('#mrTabela button.od-acao-despesas[aria-label*="Ana Silva"]').click()
    p.wait_for_selector("#dlgDesp[open]")
    p.wait_for_function("() => document.querySelectorAll('#dsLista tr').length > 0")
    m = p.evaluate("""() => { const d = document.getElementById('dlgDesp').getBoundingClientRect();
        const alt = id => document.getElementById(id).getBoundingClientRect().height;
        return {w: d.width, h: d.height, rolagem: document.documentElement.scrollWidth, lancar: alt('dsLancar'), fechar: alt('dsFechar'),
                dialogoScroll: document.getElementById('dlgDesp').scrollWidth - document.getElementById('dlgDesp').clientWidth}; }""")
    assert m["w"] >= 389 and m["h"] >= 799 and m["rolagem"] <= 390 and m["dialogoScroll"] <= 1
    assert m["lancar"] >= 44 and m["fechar"] >= 44
    t.foto("despesas_04_celular_claro")
    assert erros_graves(t.erros) == []
    t.fechar()


def test_tema_escuro(navegador, servidor):
    t = Tela(navegador, "admin", esquema="dark")
    p = t.page
    semear(p, "Item do tema escuro")
    abrir_despesas(p, "ocupados", "Ana Silva")
    cores = p.evaluate("() => { const e = getComputedStyle(document.getElementById('dlgDesp')); return [e.backgroundColor, e.color]; }")
    assert cores[0] != "rgb(255, 255, 255)" and cores[1] != "rgb(0, 0, 0)"
    t.foto("despesas_05_escuro_desktop")
    t.fechar()
    m = Tela(navegador, "admin", largura=390, altura=800, esquema="dark")
    m.page.locator("body").wait_for()
    abrir_lista(m.page, "ocupados")
    m.page.locator('#mrTabela button.od-acao-despesas[aria-label*="Ana Silva"]').click()
    m.page.wait_for_selector("#dlgDesp[open]")
    m.page.wait_for_function("() => document.querySelectorAll('#dsLista tr').length > 0")
    m.foto("despesas_06_escuro_celular")
    assert erros_graves(m.erros) == []
    m.fechar()


def test_atualizacao_de_8s_sem_perder_o_que_esta_sendo_digitado(navegador, servidor):
    a, b = Tela(navegador, "admin"), Tela(navegador, "atend")
    abrir_despesas(a.page, "ins", "Bruno")
    a.page.fill("#dsDesc", "Texto em andamento")
    a.page.fill("#dsValor", "7,5")
    antes = a.page.locator("#dsLista tr").count()
    assert b.page.evaluate("""() => api('POST', '/api/reservas/' + reservas.filter(r => r.nome === 'Bruno Lima')[0].id + '/despesas',
        {categoria: 'outros', descricao: 'Lançado por outro', quantidade: 1, valor_unit_centavos: 1100, chave: 'chave-outro-001'}).then(r => r.status)""") == 201
    a.page.wait_for_function("n => document.querySelectorAll('#dsLista tr').length > n", arg=antes, timeout=14000)
    assert a.page.input_value("#dsDesc") == "Texto em andamento" and a.page.input_value("#dsValor") == "7,5"
    assert "Lançado por outro" in a.page.inner_text("#dsLista") and "R$ 11,00" in a.page.inner_text("#dsTotais")
    assert erros_graves(a.erros) == [] and erros_graves(b.erros) == []
    a.fechar()
    b.fechar()
