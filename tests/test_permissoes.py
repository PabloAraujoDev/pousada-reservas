"""Matriz de permissões: papel x rota, mais as regras finas de cada papel."""
import io

import pytest

from pousada.permissoes import PERMISSOES, TODAS
from tests.conftest import cliente_como, criar_app_teste

PAPEIS = ["admin", "atendente", "recepcao", "camareira", "diretoria", "consulta"]
RESERVA = {"a": "201", "nome": "Hóspede Teste", "extras": "berço", "n": 2, "i": "2026-10-10", "f": "2026-10-12",
           "p": "pendente", "o": "obs original", "grupo": ""}
SO_ADMIN = {"admin"}
LER = {"admin", "atendente", "recepcao", "camareira", "diretoria", "consulta"}
FOLHA = {"admin", "atendente", "recepcao", "diretoria", "consulta"}


def _xlsx_invalido():
    return {"arquivo": (io.BytesIO(b"nao e planilha"), "x.xlsx")}


# (descrição, método, url, corpo, papéis que PODEM). Quem não pode recebe 403; quem pode recebe qualquer outro status.
ROTAS = [
    ("listar reservas", "get", "/api/reservas", None, LER),
    ("detalhe da reserva", "get", "/api/reservas/1", None, {"admin", "atendente", "recepcao", "diretoria", "consulta"}),
    ("mover reserva", "post", "/api/reservas/1/mover", {"versao": 1, "a": "202"}, {"admin", "atendente"}),
    ("criar reserva", "post", "/api/reservas", dict(RESERVA, a="202"), {"admin", "atendente"}),
    ("editar reserva", "put", "/api/reservas/1", dict(RESERVA, versao=1), {"admin", "atendente", "recepcao"}),
    ("excluir/cancelar reserva", "delete", "/api/reservas/1", {"versao": 1, "motivo": "teste"}, {"admin", "atendente"}),
    ("listar canceladas", "get", "/api/reservas?canceladas=1", None, {"admin", "atendente"}),
    ("reativar", "post", "/api/reservas/1/reativar", {"versao": 1}, {"admin", "atendente"}),
    ("excluir definitivo", "post", "/api/reservas/1/excluir-definitivo", {"versao": 1}, SO_ADMIN),
    ("camareiras", "get", "/api/camareiras", None, {"admin", "atendente", "camareira", "consulta"}),
    ("export completo", "get", "/api/export.csv", None, {"admin", "diretoria"}),
    ("export da folha", "get", "/api/export.csv?inicio=2026-10-10&dias=7", None, FOLHA),
    ("folha em PDF", "get", "/api/folha.pdf?inicio=2026-10-05", None, FOLHA),
    ("importar exemplos", "post", "/api/importar", None, SO_ADMIN),
    ("importar prévia", "post", "/api/importar/previa", "multipart", SO_ADMIN),
    ("importar confirmar", "post", "/api/importar/confirmar", {"linhas": [], "pedidos": []}, SO_ADMIN),
    ("importar desfazer", "post", "/api/importar/desfazer/1", None, SO_ADMIN),
    ("pedidos", "get", "/api/pedidos", None, SO_ADMIN),
    ("histórico completo/resumo", "get", "/api/historico", None, {"admin", "diretoria"}),
    ("histórico de uma reserva", "get", "/api/reservas/1/historico", None, {"admin", "atendente"}),
    ("fazer backup agora", "post", "/api/backup", None, SO_ADMIN),
    ("listar backups", "get", "/api/backup", None, SO_ADMIN),
    ("salvar as próprias preferências de tela", "post", "/api/preferencias", {"mapa_semanas": 7}, LER),
    ("governança: ver", "get", "/api/governanca", None, LER),
    ("governança: eventos da unidade", "get", "/api/governanca/201/eventos", None, LER),
    ("governança: atualizar", "post", "/api/governanca/acao", {"acao": "pronta", "unidades": [{"u": "201", "versao": 1}]},
     {"admin", "atendente", "recepcao", "camareira"}),
    ("governança: manutenção", "post", "/api/governanca/acao",
     {"acao": "manutencao_abrir", "unidades": [{"u": "201", "versao": 1}], "motivo": "teste"}, {"admin", "atendente"}),
    ("despesas: ver", "get", "/api/reservas/1/despesas", None, {"admin", "atendente", "recepcao", "diretoria"}),
    ("despesas: resumo de contas abertas", "get", "/api/despesas/resumo", None, {"admin", "atendente", "recepcao", "diretoria"}),
    ("despesas: lançar", "post", "/api/reservas/1/despesas",
     {"item_id": 1, "item_versao": 1, "quantidade": 1, "chave": "chave-perm-1"},
     {"admin", "atendente", "recepcao"}),
    ("despesas: estornar", "post", "/api/despesas/1/estorno", {"motivo": "digitado errado"}, {"admin", "atendente"}),
    ("listar usuários", "get", "/api/usuarios", None, SO_ADMIN),
    ("criar usuário", "post", "/api/usuarios", {"login": "novo1", "nome": "N", "senha": "senha-longa-123", "papel": "recepcao"}, SO_ADMIN),
    ("editar usuário", "post", "/api/usuarios/1", {"nome": "Novo Nome", "papel": "admin"}, SO_ADMIN),
    ("ativar usuário", "post", "/api/usuarios/1/ativo", {"ativo": True}, SO_ADMIN),
    ("redefinir senha", "post", "/api/usuarios/1/senha", {"senha": "senha-longa-123"}, SO_ADMIN),
]


@pytest.mark.parametrize("papel", PAPEIS)
@pytest.mark.parametrize("rota", ROTAS, ids=[r[0] for r in ROTAS])
def test_matriz_papel_x_rota(tmp_path, papel, rota):
    _, metodo, url, corpo, permitidos = rota
    app = criar_app_teste(tmp_path)
    admin = cliente_como(app, "admin", "chefe")
    assert admin.post("/api/reservas", json=RESERVA).status_code == 201
    c = admin if papel == "admin" else cliente_como(app, papel)
    if corpo == "multipart":
        r = c.post(url, data=_xlsx_invalido(), content_type="multipart/form-data")
    elif corpo is None:
        r = getattr(c, metodo)(url)
    else:
        r = getattr(c, metodo)(url, json=corpo)
    if papel in permitidos:
        assert r.status_code not in (401, 403), "%s deveria poder: %s" % (papel, r.get_data(as_text=True))
    else:
        assert r.status_code == 403, "%s não deveria poder (%s)" % (papel, r.status_code)
        assert "permissão" in r.get_json()["erro"]


def test_todo_papel_so_tem_capacidades_conhecidas():
    for papel, caps in PERMISSOES.items():
        assert caps <= TODAS, papel
    assert PERMISSOES["admin"] == TODAS


def test_recepcao_so_altera_pagamento_e_observacoes(app):
    admin = cliente_como(app, "admin")
    r = admin.post("/api/reservas", json=RESERVA).get_json()
    rec = cliente_como(app, "recepcao")
    tentativa = dict(RESERVA, nome="Nome Trocado", a="301", n=9, i="2026-11-01", f="2026-11-09", extras="x",
                     p="pago", o="pagou no balcão", versao=r["versao"])
    resp = rec.put("/api/reservas/%d" % r["id"], json=tentativa)
    assert resp.status_code == 200
    novo = resp.get_json()
    assert (novo["p"], novo["o"]) == ("pago", "pagou no balcão")
    for campo in ("a", "nome", "n", "i", "f", "extras"):
        assert novo[campo] == r[campo], campo
    # mandar só p e o também funciona
    resp = rec.put("/api/reservas/%d" % r["id"], json={"p": "parcial", "versao": novo["versao"]})
    assert resp.status_code == 200 and resp.get_json()["p"] == "parcial" and resp.get_json()["o"] == "pagou no balcão"
    assert rec.put("/api/reservas/%d" % r["id"], json={"p": "invalido", "versao": 3}).status_code == 400


def test_camareira_recebe_listagem_reduzida(app):
    cliente_como(app, "admin").post("/api/reservas", json=dict(RESERVA, o="telefone 11 99999-0000", p="pago"))
    cam = cliente_como(app, "camareira")
    linha = cam.get("/api/reservas").get_json()[0]
    assert set(linha) == {"id", "a", "n", "i", "f"}
    texto = cam.get("/api/reservas").get_data(as_text=True)
    assert "Hóspede" not in texto and "99999" not in texto and "pago" not in texto and "berço" not in texto


def test_camareira_nao_consegue_pedir_nomes_na_folha(app):
    cliente_como(app, "admin").post("/api/reservas", json=RESERVA)
    cam = cliente_como(app, "camareira")
    dia = cam.get("/api/camareiras?inicio=2026-10-10&fim=2026-10-10&nomes=1").get_json()["dias"][0]
    assert "nome" not in dia["unidades"][0]["entrada"]
    adm = cliente_como(app, "atendente").get("/api/camareiras?inicio=2026-10-10&fim=2026-10-10&nomes=1").get_json()
    assert adm["dias"][0]["unidades"][0]["entrada"]["nome"] == "Hóspede Teste"


def test_diretoria_somente_leitura(app):
    cliente_como(app, "admin").post("/api/reservas", json=RESERVA)
    d = cliente_como(app, "diretoria")
    assert d.get("/api/reservas").status_code == 200
    assert d.post("/api/reservas", json=dict(RESERVA, a="203")).status_code == 403
    assert d.put("/api/reservas/1", json=dict(RESERVA, versao=1)).status_code == 403
    assert d.delete("/api/reservas/1", json={"versao": 1}).status_code == 403


def test_sessao_informa_as_permissoes_do_papel(app):
    j = cliente_como(app, "recepcao").get("/api/sessao").get_json()
    assert "reservas.editar_pagamento" in j["permissoes"] and "importar" not in j["permissoes"]


# ---------------------------------------------------------------- gestão de usuários

def test_admin_cria_desativa_e_redefine_usuario(app):
    admin = cliente_como(app, "admin")
    r = admin.post("/api/usuarios", json={"login": "joana", "nome": "Joana", "senha": "senha-longa-123", "papel": "recepcao"})
    assert r.status_code == 201 and r.get_json()["trocar_senha"] is True and "senha-longa" not in str(r.get_json())
    uid = r.get_json()["id"]
    assert admin.post("/api/usuarios", json={"login": "JOANA", "nome": "x", "senha": "senha-longa-123", "papel": "recepcao"}).status_code == 400
    assert admin.post("/api/usuarios", json={"login": "x1x", "nome": "x", "senha": "curta", "papel": "recepcao"}).status_code == 400
    assert admin.post("/api/usuarios/%d/ativo" % uid, json={"ativo": False}).get_json()["ativo"] is False
    assert admin.post("/api/usuarios/%d/senha" % uid, json={"senha": "outra-senha-forte"}).get_json()["trocar_senha"] is True
    eu = [u for u in admin.get("/api/usuarios").get_json() if u["login"] == "admin"][0]
    assert admin.post("/api/usuarios/%d/ativo" % eu["id"], json={"ativo": False}).status_code == 400
    assert "senha_hash" not in admin.get("/api/usuarios").get_data(as_text=True)
