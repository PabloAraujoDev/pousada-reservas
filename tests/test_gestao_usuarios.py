"""Tela de usuários do administrador: criar, editar perfil, ativar, redefinir senha e o perfil "consulta" (só ver e imprimir)."""
import os
import shutil
import sqlite3

import pytest

from pousada.db import conectar, iniciar_banco
from pousada.permissoes import PERMISSOES
from tests.conftest import cliente_como, inserir_usuario

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESERVA = {"a": "201", "nome": "Hóspede Teste", "extras": "", "n": 2, "i": "2026-10-10", "f": "2026-10-12",
           "p": "pendente", "o": "", "grupo": ""}


def _novo(admin, login="maria", papel="consulta", senha="Tz9k-Pq4m-Wx7c"):
    r = admin.post("/api/usuarios", json={"login": login, "nome": "Maria Silva", "senha": senha, "papel": papel})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _entrar(app, login, senha):
    c = app.test_client()
    c.csrf = c.get("/api/sessao").get_json()["csrf"]
    r = c.post("/api/login", json={"login": login, "senha": senha})
    assert r.status_code == 200, r.get_json()
    c.csrf = r.get_json()["csrf"]
    return c


# ---------------------------------------------------------------- perfil "consulta"

def test_consulta_so_tem_capacidades_de_leitura():
    assert PERMISSOES["consulta"] == frozenset({"reservas.ver", "folha.ver", "camareiras.ver", "governanca.ver"})


def test_consulta_ve_e_imprime(app, cli):
    cli.post("/api/reservas", json=RESERVA)
    c = cliente_como(app, "consulta")
    assert c.get("/api/reservas").status_code == 200
    assert c.get("/api/camareiras").status_code == 200
    pdf = c.get("/api/folha.pdf?inicio=2026-10-05")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_consulta_nao_altera_nada(app, cli):
    criada = cli.post("/api/reservas", json=RESERVA).get_json()
    c = cliente_como(app, "consulta")
    assert c.post("/api/reservas", json=dict(RESERVA, a="202")).status_code == 403
    assert c.put("/api/reservas/%d" % criada["id"], json=dict(RESERVA, versao=criada["versao"], p="pago")).status_code == 403
    assert c.delete("/api/reservas/%d" % criada["id"], json={"versao": criada["versao"], "motivo": "x"}).status_code == 403
    assert c.post("/api/reservas/%d/excluir-definitivo" % criada["id"], json={"versao": criada["versao"]}).status_code == 403
    assert c.get("/api/reservas?canceladas=1").status_code == 403


def test_consulta_nao_exporta_nem_ve_historico_nem_administra(app):
    c = cliente_como(app, "consulta")
    for metodo, url in (("get", "/api/export.csv"), ("get", "/api/historico"), ("get", "/api/reservas/1/historico"),
                        ("get", "/api/usuarios"), ("post", "/api/usuarios"), ("post", "/api/usuarios/1"),
                        ("get", "/api/backup"), ("post", "/api/backup"), ("get", "/api/pedidos"),
                        ("post", "/api/importar"), ("post", "/api/importar/confirmar")):
        assert getattr(c, metodo)(url).status_code == 403, (metodo, url)


def test_consulta_pode_ser_criado_pela_api_e_entra(app, cli):
    novo = _novo(cli, "visitante")
    assert novo["papel"] == "consulta" and novo["trocar_senha"] is True
    c = _entrar(app, "visitante", "Tz9k-Pq4m-Wx7c")
    sessao = c.get("/api/sessao").get_json()
    assert sorted(sessao["permissoes"]) == ["camareiras.ver", "folha.ver", "governanca.ver", "reservas.ver"]


# ---------------------------------------------------------------- migração 008 (CHECK do banco)

def test_migracao_008_mantem_os_usuarios_e_aceita_consulta(tmp_path):
    antigas = tmp_path / "migracoes_ate_007"
    antigas.mkdir()
    for nome in sorted(os.listdir(os.path.join(RAIZ, "migrations"))):
        if nome < "008":
            shutil.copy(os.path.join(RAIZ, "migrations", nome), antigas / nome)
    banco = str(tmp_path / "antigo.db")
    iniciar_banco(banco, str(antigas))
    con = conectar(banco)
    con.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, ativo, trocar_senha, criado, ultimo_login, sessao_ver) "
                "VALUES ('ana','Ana','hash-ana','diretoria',1,0,'2026-01-01 08:00:00','2026-10-01 09:00:00',3)")
    con.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, ativo, trocar_senha, criado) "
                "VALUES ('bia','Bia','hash-bia','camareira',0,1,'2026-01-02 08:00:00')")
    con.close()
    with pytest.raises(sqlite3.IntegrityError):                     # antes da 008 o perfil não existe
        c0 = conectar(banco)
        try:
            c0.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, criado) VALUES ('x','X','h','consulta','2026-01-01')")
        finally:
            c0.close()

    iniciar_banco(banco, os.path.join(RAIZ, "migrations"))           # aplica a 008 sobre dados reais

    con = conectar(banco)
    try:
        linhas = {r["login"]: dict(r) for r in con.execute("SELECT * FROM usuarios")}
        assert linhas["ana"]["senha_hash"] == "hash-ana" and linhas["ana"]["papel"] == "diretoria"
        assert linhas["ana"]["ultimo_login"] == "2026-10-01 09:00:00" and linhas["ana"]["sessao_ver"] == 3
        assert linhas["bia"]["ativo"] == 0 and linhas["bia"]["trocar_senha"] == 1
        assert [linhas["ana"]["id"], linhas["bia"]["id"]] == [1, 2]
        con.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, criado) VALUES ('cris','Cris','h','consulta','2026-01-03')")
        with pytest.raises(sqlite3.IntegrityError):                  # o CHECK continua valendo para perfis inventados
            con.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, criado) VALUES ('dan','Dan','h','chefao','2026-01-03')")
        with pytest.raises(sqlite3.IntegrityError):                  # login continua único sem diferenciar maiúsculas
            con.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, criado) VALUES ('ANA','Outra','h','consulta','2026-01-03')")
        assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 8
    finally:
        con.close()


# ---------------------------------------------------------------- editar nome e perfil

def test_admin_edita_nome_e_perfil(app, cli):
    u = _novo(cli, "joana", "atendente")
    r = cli.post("/api/usuarios/%d" % u["id"], json={"nome": "Joana Souza", "papel": "recepcao"})
    assert r.status_code == 200
    assert r.get_json()["nome"] == "Joana Souza" and r.get_json()["papel"] == "recepcao"
    listados = {x["login"]: x for x in cli.get("/api/usuarios").get_json()}
    assert listados["joana"]["papel"] == "recepcao"


def test_mudanca_de_perfil_vale_no_proximo_pedido(app, cli):
    """Rebaixar alguém tira as permissões na hora, sem precisar sair e entrar."""
    u = _novo(cli, "pedro", "atendente")
    c = _entrar(app, "pedro", "Tz9k-Pq4m-Wx7c")
    # troca obrigatória de senha no primeiro acesso: o servidor bloqueia o resto até isso
    assert c.post("/api/senha", json={"atual": "Tz9k-Pq4m-Wx7c", "nova": "Nova-Senha-Forte-81"}).status_code == 200
    c.csrf = c.get("/api/sessao").get_json()["csrf"]
    assert c.post("/api/reservas", json=RESERVA).status_code == 201
    assert cli.post("/api/usuarios/%d" % u["id"], json={"nome": "Pedro", "papel": "consulta"}).status_code == 200
    assert c.post("/api/reservas", json=dict(RESERVA, a="202")).status_code == 403
    assert c.get("/api/reservas").status_code == 200


def test_editar_recusa_dados_ruins(app, cli):
    u = _novo(cli, "lia", "consulta")
    url = "/api/usuarios/%d" % u["id"]
    assert cli.post(url, json={"nome": "Lia", "papel": "superadmin"}).status_code == 400
    assert cli.post(url, json={"nome": "", "papel": "consulta"}).status_code == 400
    assert cli.post(url, json={"nome": "   ", "papel": "consulta"}).status_code == 400
    assert cli.post(url, json={"nome": "x" * 121, "papel": "consulta"}).status_code == 400
    assert cli.post(url, json={"nome": "Li\x00a", "papel": "consulta"}).status_code == 400
    assert cli.post(url, json={"nome": "Lia‮evil", "papel": "consulta"}).status_code == 400
    assert cli.post(url, json={"nome": 123, "papel": "consulta"}).status_code == 400
    assert cli.post(url, json={"nome": "Lia"}).status_code == 400
    assert cli.post(url, json=["lista"]).status_code == 400
    assert cli.post("/api/usuarios/99999", json={"nome": "Z", "papel": "consulta"}).status_code == 404
    assert cli.get("/api/usuarios").get_json()[0]["papel"] in ("admin", "consulta")      # nada foi alterado por engano


def test_editar_ignora_campos_extras(app, cli):
    """Só nome e perfil mudam: login, senha, situação e versão da sessão ficam como estão."""
    u = _novo(cli, "rita", "consulta")
    r = cli.post("/api/usuarios/%d" % u["id"], json={"nome": "Rita", "papel": "consulta", "login": "outro", "ativo": False,
                                                        "senha_hash": "x", "id": 999, "trocar_senha": False})
    assert r.status_code == 200 and r.get_json()["login"] == "rita" and r.get_json()["ativo"] is True
    assert r.get_json()["trocar_senha"] is True and r.get_json()["id"] == u["id"]


def test_ninguem_muda_o_proprio_perfil(app, cli):
    meu_id = next(x["id"] for x in cli.get("/api/usuarios").get_json() if x["login"] == "admin")
    r = cli.post("/api/usuarios/%d" % meu_id, json={"nome": "Admin", "papel": "consulta"})
    assert r.status_code == 400 and "próprio perfil" in r.get_json()["erro"]
    assert cli.get("/api/usuarios").status_code == 200                    # continua administrador
    assert cli.post("/api/usuarios/%d" % meu_id, json={"nome": "Novo Nome do Admin", "papel": "admin"}).status_code == 200


def test_edicao_fica_no_historico(app, cli):
    u = _novo(cli, "vera", "atendente")
    cli.post("/api/usuarios/%d" % u["id"], json={"nome": "Vera", "papel": "consulta"})
    itens = [x for x in cli.get("/api/historico").get_json() if x["acao"] == "usuario_editado"]
    assert itens and itens[0]["antes"] == {"papel": "atendente"} and itens[0]["depois"] == {"papel": "consulta"}
    assert itens[0]["entidade_id"] == u["id"]


def test_so_admin_edita_usuarios(app, cli):
    u = _novo(cli, "gil", "consulta")
    for papel in ("atendente", "recepcao", "camareira", "diretoria", "consulta"):
        assert cliente_como(app, papel).post("/api/usuarios/%d" % u["id"], json={"nome": "G", "papel": "admin"}).status_code == 403
    assert next(x for x in cli.get("/api/usuarios").get_json() if x["login"] == "gil")["papel"] == "consulta"


# ---------------------------------------------------------------- redefinir senha, ativar, criar

def test_admin_nao_redefine_a_propria_senha_por_aqui(app, cli):
    meu_id = next(x["id"] for x in cli.get("/api/usuarios").get_json() if x["login"] == "admin")
    r = cli.post("/api/usuarios/%d/senha" % meu_id, json={"senha": "Tz9k-Pq4m-Wx7c"})
    assert r.status_code == 400 and "Trocar minha senha" in r.get_json()["erro"]


def test_redefinir_senha_derruba_a_sessao_e_exige_troca(app, cli):
    u = _novo(cli, "marta", "consulta")
    c = _entrar(app, "marta", "Tz9k-Pq4m-Wx7c")
    assert cli.post("/api/usuarios/%d/senha" % u["id"], json={"senha": "Outra-Provisoria-55"}).status_code == 200
    assert c.get("/api/reservas").status_code == 401                      # a sessão antiga deixou de valer
    novo = _entrar(app, "marta", "Outra-Provisoria-55")
    assert novo.get("/api/sessao").get_json()["usuario"]["trocar_senha"] is True


def test_senha_provisoria_fraca_e_recusada_na_criacao_e_na_redefinicao(app, cli):
    for ruim in ("1234567890", "senha12345", "curta", "aaaaaaaaaaaa", "maria"):
        r = cli.post("/api/usuarios", json={"login": "maria", "nome": "M", "senha": ruim, "papel": "consulta"})
        assert r.status_code == 400, ruim
    u = _novo(cli, "nina", "consulta")
    assert cli.post("/api/usuarios/%d/senha" % u["id"], json={"senha": "1234567890"}).status_code == 400


def test_desativar_e_reativar_usuario(app, cli):
    u = _novo(cli, "ivo", "consulta")
    c = _entrar(app, "ivo", "Tz9k-Pq4m-Wx7c")
    assert cli.post("/api/usuarios/%d/ativo" % u["id"], json={"ativo": False}).status_code == 200
    assert c.get("/api/sessao").get_json()["autenticado"] is False       # derrubado na hora
    assert app.test_client().post("/api/login", json={"login": "ivo", "senha": "Tz9k-Pq4m-Wx7c"}, headers={"X-CSRF-Token": "x"}).status_code in (401, 403)
    assert cli.post("/api/usuarios/%d/ativo" % u["id"], json={"ativo": True}).status_code == 200
    _entrar(app, "ivo", "Tz9k-Pq4m-Wx7c")


def test_login_repetido_e_perfil_invalido_na_criacao(app, cli):
    _novo(cli, "duda", "consulta")
    assert cli.post("/api/usuarios", json={"login": "DUDA", "nome": "Outra", "senha": "Tz9k-Pq4m-Wx7c", "papel": "consulta"}).status_code == 400
    assert cli.post("/api/usuarios", json={"login": "eva", "nome": "Eva", "senha": "Tz9k-Pq4m-Wx7c", "papel": "dono"}).status_code == 400


def test_lista_de_usuarios_nunca_devolve_a_senha(app, cli):
    _novo(cli, "zeca", "consulta")
    bruto = cli.get("/api/usuarios").get_data(as_text=True)
    assert "senha_hash" not in bruto and "scrypt" not in bruto and "pbkdf2" not in bruto and "sessao_ver" not in bruto


# ---------------------------------------------------------------- tela (HTML/JS)

def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as fh:
        return fh.read()


def test_tela_de_usuarios_so_aparece_para_quem_tem_a_capacidade():
    html = _ler("static", "index.html")
    assert 'data-aba="usuarios" data-cap="usuarios"' in html
    assert 'id="aba-usuarios"' in html and 'id="dlgUsu"' in html and 'id="btnMinhaSenha"' in html
    assert "style=" not in html                                          # a CSP não permite estilo inline


def test_js_da_tela_lista_todos_os_perfis_do_servidor():
    from pousada.usuarios import PAPEIS
    js = _ler("static", "app.js")
    for papel in PAPEIS:
        assert '["%s",' % papel in js, papel
    assert "usuario_editado" in js


def test_js_da_tela_escapa_o_que_vem_do_servidor():
    """Login, nome e perfil de usuário entram no HTML da tabela: tudo passa por esc()."""
    js = _ler("static", "app.js")
    bloco = js.split("/* ---------- Usuários (administrador) ----------")[1].split('$("btnSair")')[0]
    for valor in ("u.login", "u.nome", "rotuloPerfil(u.papel)", "u.id"):
        assert "esc(" + valor + ")" in bloco, valor


def test_inserir_usuario_de_teste_aceita_consulta(app):
    assert inserir_usuario(app, "consulta", "leitor") > 0
