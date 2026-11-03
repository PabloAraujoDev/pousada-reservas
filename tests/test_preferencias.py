"""Personalização de menus: preferências por usuário, guardadas no servidor. É só estética: nunca mexe em permissão."""
import os
import shutil
import sqlite3

import pytest

from pousada.db import conectar, iniciar_banco
from tests.conftest import SENHA, cliente_como, inserir_usuario

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPEIS = ["admin", "atendente", "recepcao", "camareira", "diretoria", "consulta"]
PADRAO = {"menus_ocultos": [], "aba_inicial": None, "mapa_semanas": None, "resumo_recolhido": None}
RESERVA = {"a": "201", "nome": "Hóspede Teste", "extras": "", "n": 2, "i": "2026-10-10", "f": "2026-10-12",
           "p": "pendente", "o": "", "grupo": ""}
ABAS = ["mapa", "calendario", "folha", "buscar", "governanca", "camareiras", "canceladas", "historico", "usuarios"]


def _salvar(c, corpo):
    return c.post("/api/preferencias", json=corpo)


def _entrar(app, login):
    c = app.test_client()
    c.csrf = c.get("/api/sessao").get_json()["csrf"]
    r = c.post("/api/login", json={"login": login, "senha": SENHA})
    assert r.status_code == 200, r.get_json()
    c.csrf = r.get_json()["csrf"]
    return c, r


def _gravar_no_banco(app, login, texto):
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        con.execute("UPDATE usuarios SET preferencias=? WHERE login=?", (texto, login))
    finally:
        con.close()


# ---------------------------------------------------------------- migração 010

def test_migracao_010_mantem_usuarios_e_da_padrao_vazio(tmp_path):
    antigas = tmp_path / "ate_009"
    antigas.mkdir()
    for nome in sorted(os.listdir(os.path.join(RAIZ, "migrations"))):
        if nome < "010":
            shutil.copy(os.path.join(RAIZ, "migrations", nome), antigas / nome)
    banco = str(tmp_path / "antigo.db")
    iniciar_banco(banco, str(antigas))
    con = conectar(banco)
    con.execute("INSERT INTO usuarios (login, nome, senha_hash, papel, ativo, trocar_senha, criado, sessao_ver) "
                "VALUES ('ana','Ana','hash-ana','diretoria',1,0,'2026-01-01 08:00:00',3)")
    con.close()
    iniciar_banco(banco, os.path.join(RAIZ, "migrations"))
    con = conectar(banco)
    try:
        u = dict(con.execute("SELECT * FROM usuarios").fetchone())
        assert u["login"] == "ana" and u["senha_hash"] == "hash-ana" and u["sessao_ver"] == 3
        assert u["preferencias"] == "{}"
        con.execute("UPDATE usuarios SET preferencias=?", ('{"aba_inicial":"folha"}',))
        with pytest.raises(sqlite3.IntegrityError):                       # o banco também limita o tamanho
            con.execute("UPDATE usuarios SET preferencias=?", ("x" * 2001,))
        assert con.execute("SELECT MAX(versao) FROM schema_version").fetchone()[0] >= 10
    finally:
        con.close()


# ---------------------------------------------------------------- leitura e gravação

def test_sessao_traz_preferencias_com_padroes(app):
    c = cliente_como(app, "admin")
    assert c.get("/api/sessao").get_json()["preferencias"] == PADRAO


def test_anonimo_nao_recebe_preferencias_na_sessao(app):
    s = app.test_client().get("/api/sessao").get_json()
    assert "preferencias" not in s and s["autenticado"] is False


def test_salva_e_devolve_normalizado(app):
    c = cliente_como(app, "admin")
    r = _salvar(c, {"menus_ocultos": ["canceladas", "importar"], "aba_inicial": "folha", "mapa_semanas": 28})
    assert r.status_code == 200
    esperado = {"menus_ocultos": ["canceladas", "importar"], "aba_inicial": "folha", "mapa_semanas": 28, "resumo_recolhido": None}
    assert r.get_json() == esperado
    assert c.get("/api/sessao").get_json()["preferencias"] == esperado


def test_ordem_fixa_na_resposta(app):
    c = cliente_como(app, "admin")
    assert _salvar(c, {"menus_ocultos": ["nova", "canceladas"]}).get_json()["menus_ocultos"] == ["canceladas", "nova"]


def test_corpo_parcial_mantem_o_resto(app):
    c = cliente_como(app, "admin")
    _salvar(c, {"menus_ocultos": ["canceladas"], "aba_inicial": "folha", "mapa_semanas": 7})
    r = _salvar(c, {"mapa_semanas": 28}).get_json()
    assert r == {"menus_ocultos": ["canceladas"], "aba_inicial": "folha", "mapa_semanas": 28, "resumo_recolhido": None}


def test_null_e_lista_vazia_voltam_ao_padrao(app):
    c = cliente_como(app, "admin")
    _salvar(c, {"menus_ocultos": ["canceladas"], "aba_inicial": "folha", "mapa_semanas": 7})
    assert _salvar(c, {"menus_ocultos": []}).get_json()["menus_ocultos"] == []
    assert _salvar(c, {"aba_inicial": None}).get_json()["aba_inicial"] is None
    assert _salvar(c, {"mapa_semanas": None}).get_json()["mapa_semanas"] is None
    _salvar(c, {"menus_ocultos": ["canceladas"]})
    assert _salvar(c, {"menus_ocultos": None}).get_json() == PADRAO


@pytest.mark.parametrize("corpo", [
    {"menus_ocultos": ["inexistente"]}, {"menus_ocultos": ["mapa", "mapa"]}, {"menus_ocultos": "mapa"},
    {"menus_ocultos": [1]}, {"menus_ocultos": [None]}, {"menus_ocultos": [["mapa"]]}, {"menus_ocultos": {"mapa": 1}},
    {"menus_ocultos": ["canceladas"] * 500}, {"menus_ocultos": ["x"] * 100000},
    {"aba_inicial": "importar"}, {"aba_inicial": "nova"}, {"aba_inicial": "xx"}, {"aba_inicial": 1}, {"aba_inicial": ["mapa"]},
    {"mapa_semanas": 10}, {"mapa_semanas": 0}, {"mapa_semanas": "14"}, {"mapa_semanas": 14.0}, {"mapa_semanas": True},
    {"mapa_semanas": [14]}, {"mapa_semanas": -7},
    {"menus_ocultos": ABAS},                                   # nenhuma aba sobra
    {"menus_ocultos": ABAS + ["importar", "nova"]},
    {"menus_ocultos": ["folha"], "aba_inicial": "folha"},      # aba inicial oculta
    {"cor": "azul"}, {}, {"id": 1}, {"usuario_id": 1}, {"menus_ocultos": [], "papel": "admin"},
])
def test_entrada_invalida_e_400_e_nao_grava(app, corpo):
    c = cliente_como(app, "admin")
    r = _salvar(c, corpo)
    assert r.status_code == 400 and r.get_json()["erro"]
    assert c.get("/api/sessao").get_json()["preferencias"] == PADRAO


@pytest.mark.parametrize("texto", ["[]", '"oi"', "123", "null", "{"])
def test_json_que_nao_e_objeto_e_400(app, texto):
    c = cliente_como(app, "admin")
    assert c.post("/api/preferencias", data=texto, content_type="application/json").status_code == 400


def test_aba_inicial_ja_gravada_impede_ocultar_a_mesma(app):
    c = cliente_como(app, "admin")
    _salvar(c, {"aba_inicial": "folha"})
    assert _salvar(c, {"menus_ocultos": ["folha"]}).status_code == 400
    assert _salvar(c, {"menus_ocultos": ["folha"], "aba_inicial": None}).status_code == 200


def test_ocultar_seis_abas_e_tudo_mais_pode(app):
    c = cliente_como(app, "admin")
    assert _salvar(c, {"menus_ocultos": ABAS[1:] + ["importar", "nova"]}).status_code == 200


# ---------------------------------------------------------------- isolamento e segurança

def test_nao_altera_preferencias_de_outro_usuario(app):
    a, b = cliente_como(app, "admin"), cliente_como(app, "atendente")
    outro = b.get("/api/sessao").get_json()["usuario"]["id"]
    for corpo in ({"id": outro, "menus_ocultos": ["folha"]}, {"usuario_id": outro, "menus_ocultos": ["folha"]}):
        assert _salvar(a, corpo).status_code == 400                       # alvo não existe: recusado
    assert _salvar(a, {"menus_ocultos": ["folha"]}).status_code == 200
    assert b.get("/api/sessao").get_json()["preferencias"] == PADRAO       # o outro não mudou
    assert a.get("/api/sessao").get_json()["preferencias"]["menus_ocultos"] == ["folha"]


def test_anonimo_recebe_401(app):
    c = app.test_client()
    c.csrf = c.get("/api/sessao").get_json()["csrf"]
    assert _salvar(c, {"mapa_semanas": 7}).status_code == 401


def test_csrf_origem_e_content_type_obrigatorios(app):
    c = cliente_como(app, "admin")
    assert c.post("/api/preferencias", json={"mapa_semanas": 7}, sem_csrf=True).status_code == 403
    assert c.post("/api/preferencias", json={"mapa_semanas": 7}, headers={"X-CSRF-Token": "errado"}).status_code == 403
    assert c.post("/api/preferencias", json={"mapa_semanas": 7}, headers={"Origin": "https://mal.example"}).status_code == 403
    assert c.post("/api/preferencias", data="a=1", content_type="application/x-www-form-urlencoded").status_code == 415
    assert c.get("/api/sessao").get_json()["preferencias"] == PADRAO


def test_get_na_rota_nao_grava(app):
    assert cliente_como(app, "admin").get("/api/preferencias").status_code == 405


def test_quem_precisa_trocar_a_senha_continua_bloqueado(app):
    uid = inserir_usuario(app, "atendente", "novato", trocar_senha=1)
    c, _ = _entrar(app, "novato")
    r = _salvar(c, {"mapa_semanas": 7})
    assert r.status_code == 403 and r.get_json().get("trocar_senha") is True
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        assert con.execute("SELECT preferencias FROM usuarios WHERE id=?", (uid,)).fetchone()[0] == "{}"
    finally:
        con.close()


@pytest.mark.parametrize("papel", PAPEIS)
def test_todos_os_perfis_salvam_as_proprias(app, papel):
    c = cliente_como(app, papel)
    r = _salvar(c, {"menus_ocultos": ["buscar", "nova"], "aba_inicial": "camareiras", "mapa_semanas": 7})
    assert r.status_code == 200
    assert c.get("/api/sessao").get_json()["preferencias"]["aba_inicial"] == "camareiras"


def test_lista_de_usuarios_nao_expoe_preferencias(app):
    adm = cliente_como(app, "admin")
    _salvar(adm, {"menus_ocultos": ["buscar"]})
    assert "preferencias" not in adm.get("/api/usuarios").get_json()[0]


# ---------------------------------------------------------------- ocultar NÃO muda permissão

def test_sem_permissao_continua_403_mesmo_com_preferencias(app):
    cliente_como(app, "admin", "chefe").post("/api/reservas", json=RESERVA)
    cam = cliente_como(app, "camareira")
    assert _salvar(cam, {"menus_ocultos": ["mapa", "folha", "buscar", "historico", "usuarios"]}).status_code == 200
    for metodo, url in (("get", "/api/usuarios"), ("get", "/api/historico"), ("get", "/api/export.csv"),
                        ("get", "/api/reservas?canceladas=1"), ("post", "/api/importar"), ("get", "/api/backup")):
        assert getattr(cam, metodo)(url).status_code == 403, url
    s = cam.get("/api/sessao").get_json()                       # as permissões da sessão são as do perfil, intactas
    assert "camareiras.ver" in s["permissoes"] and "usuarios" not in s["permissoes"]


def test_admin_com_menu_oculto_ainda_acessa_a_api(app):
    adm = cliente_como(app, "admin")
    assert _salvar(adm, {"menus_ocultos": ["usuarios", "canceladas", "historico", "importar"]}).status_code == 200
    assert adm.get("/api/usuarios").status_code == 200
    assert adm.get("/api/reservas?canceladas=1").status_code == 200
    assert adm.get("/api/historico").status_code == 200
    assert "usuarios" in adm.get("/api/sessao").get_json()["permissoes"]


# ---------------------------------------------------------------- persistência e robustez

def test_persiste_entre_logins_e_o_login_traz_preferencias(app):
    inserir_usuario(app, "atendente", "maria")
    c, r = _entrar(app, "maria")
    assert r.get_json()["preferencias"] == PADRAO
    _salvar(c, {"menus_ocultos": ["canceladas"], "aba_inicial": "buscar", "mapa_semanas": 28})
    c.post("/api/logout")
    _, r2 = _entrar(app, "maria")                                # outro "computador"
    assert r2.get_json()["preferencias"] == {"menus_ocultos": ["canceladas"], "aba_inicial": "buscar", "mapa_semanas": 28, "resumo_recolhido": None}


@pytest.mark.parametrize("lixo", ["", "{", "[]", "null", "42", '{"menus_ocultos":"x"}', '{"aba_inicial":"zzz","mapa_semanas":99}',
                                  '{"menus_ocultos":["mapa","mapa"]}', '{"nova_chave":1}'])
def test_preferencia_corrompida_no_banco_nao_derruba_o_login(app, lixo):
    inserir_usuario(app, "atendente", "maria")
    _gravar_no_banco(app, "maria", lixo)
    c, r = _entrar(app, "maria")
    assert r.get_json()["preferencias"] == PADRAO
    assert c.get("/api/sessao").status_code == 200
    assert _salvar(c, {"mapa_semanas": 7}).get_json()["mapa_semanas"] == 7      # e dá para salvar por cima


@pytest.mark.parametrize("valor", [True, False, None])
def test_faixa_do_resumo_aceita_so_verdadeiro_falso_ou_nulo(app, valor):
    c = cliente_como(app, "atendente")
    r = _salvar(c, {"resumo_recolhido": valor})
    assert r.status_code == 200 and r.get_json()["resumo_recolhido"] is valor and r.get_json()["menus_ocultos"] == []


@pytest.mark.parametrize("valor", [1, 0, "true", [], {}, 1.0])
def test_faixa_do_resumo_recusa_outros_tipos(app, valor):
    assert _salvar(cliente_como(app, "atendente"), {"resumo_recolhido": valor}).status_code == 400


def test_valor_invalido_isolado_no_banco_nao_apaga_o_resto(app):
    inserir_usuario(app, "atendente", "maria")
    _gravar_no_banco(app, "maria", '{"menus_ocultos":["buscar"],"mapa_semanas":99}')
    _, r = _entrar(app, "maria")
    assert r.get_json()["preferencias"] == {"menus_ocultos": ["buscar"], "aba_inicial": None, "mapa_semanas": None, "resumo_recolhido": None}


def test_tudo_oculto_no_banco_cai_no_padrao(app):
    inserir_usuario(app, "atendente", "maria")
    _gravar_no_banco(app, "maria", '{"menus_ocultos":["mapa","calendario","folha","buscar","governanca","camareiras","canceladas","historico","usuarios"]}')
    assert _entrar(app, "maria")[1].get_json()["preferencias"] == PADRAO


def test_arquivo_estatico_de_preferencias_exige_login(app):
    assert app.test_client().get("/static/preferencias.js").status_code in (302, 401)
    assert cliente_como(app, "consulta").get("/static/preferencias.js").status_code == 200


def test_calendario_pode_ser_oculto_e_escolhido_como_aba_inicial(app):
    c = cliente_como(app, "admin")
    r = _salvar(c, {"aba_inicial": "calendario"})
    assert r.status_code == 200 and r.get_json()["aba_inicial"] == "calendario"
    assert _salvar(c, {"menus_ocultos": ["calendario"]}).status_code == 400          # aba inicial não pode estar oculta
    assert _salvar(c, {"aba_inicial": None, "menus_ocultos": ["calendario", "mapa"]}).get_json()["menus_ocultos"] == ["mapa", "calendario"]
    assert _salvar(c, {"aba_inicial": "painel"}).status_code == 400                   # o nome antigo não existe mais
    assert _salvar(c, {"menus_ocultos": ["painel"]}).status_code == 400


def test_menus_do_javascript_batem_com_a_lista_branca_do_servidor():
    from pousada.preferencias import ABAS
    js = open(os.path.join(RAIZ, "static", "preferencias.js"), encoding="utf-8").read()
    import re
    achado = re.search(r"var CHAVES_ABA = \[(.*?)\];", js).group(1)
    assert [x.strip().strip('"') for x in achado.split(",")] == list(ABAS)
