"""Rotas só do administrador: usuários (e, mais adiante, backup e histórico)."""
import json
import os

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import generate_password_hash

from . import backup
from .db import obter_con, transacao
from .erros import ErroApi
from .historico import registrar
from .permissoes import exige, pode
from .usuarios import criar_usuario, validar_edicao, validar_novo_usuario

bp = Blueprint("admin", __name__)
CAMPOS_USUARIO = ["id", "login", "nome", "papel", "ativo", "trocar_senha", "criado", "ultimo_login"]


def _usuario_json(r):
    d = {c: r[c] for c in CAMPOS_USUARIO}
    d["ativo"], d["trocar_senha"] = bool(d["ativo"]), bool(d["trocar_senha"])
    return d


def _buscar_usuario(con, uid):
    u = con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not u:
        raise ErroApi("Usuário não encontrado", 404)
    return u


@bp.route("/api/usuarios", methods=["GET"])
@exige("usuarios")
def listar_usuarios():
    return jsonify([_usuario_json(r) for r in obter_con().execute("SELECT * FROM usuarios ORDER BY login")])


@bp.route("/api/usuarios", methods=["POST"])
@exige("usuarios")
def criar_novo_usuario():
    """Cria um usuário; ele terá de trocar a senha no primeiro acesso."""
    c = request.get_json(silent=True)
    if not isinstance(c, dict):
        raise ErroApi("Dados inválidos", 400)
    con = obter_con()
    with transacao(con):
        try:
            uid = criar_usuario(con, c.get("login"), c.get("nome"), c.get("senha"), c.get("papel"), trocar_senha=True)
        except ValueError as e:
            raise ErroApi(str(e), 400)
        registrar(con, "usuario_criado", "usuario", uid, None, {"papel": c.get("papel")})
    return jsonify(_usuario_json(_buscar_usuario(con, uid))), 201


def _sem_outro_admin_ativo(con, uid):
    """True se, fora o usuário uid, não sobra nenhum administrador ativo.

    Chamada DEPOIS do "BEGIN IMMEDIATE" (dentro da transação): o SQLite só deixa uma escrita
    de cada vez, então esta contagem já reflete qualquer mudança de outro administrador que
    tenha terminado um instante antes (fecha a corrida de dois administradores se rebaixando
    ou desativando um ao outro ao mesmo tempo).
    """
    return con.execute(
        "SELECT COUNT(*) FROM usuarios WHERE papel='admin' AND ativo=1 AND id<>?", (uid,)).fetchone()[0] == 0


@bp.route("/api/usuarios/<int:uid>", methods=["POST"])
@exige("usuarios")
def editar_usuario(uid):
    """Muda o nome e o perfil. O perfil vale já no próximo pedido (as permissões são lidas do banco a cada pedido)."""
    c = request.get_json(silent=True)
    if not isinstance(c, dict):
        raise ErroApi("Dados inválidos", 400)
    erro = validar_edicao(c.get("nome"), c.get("papel"))
    if erro:
        raise ErroApi(erro, 400)
    con = obter_con()
    with transacao(con):
        u = _buscar_usuario(con, uid)
        if uid == g.usuario["id"] and c["papel"] != u["papel"]:
            raise ErroApi("Você não pode mudar o seu próprio perfil (peça a outro administrador)", 400)
        if u["papel"] == "admin" and c["papel"] != "admin" and _sem_outro_admin_ativo(con, uid):
            raise ErroApi("Não é possível rebaixar o último administrador ativo", 400)
        con.execute("UPDATE usuarios SET nome=?, papel=? WHERE id=?", (c["nome"].strip(), c["papel"], uid))
        registrar(con, "usuario_editado", "usuario", uid, {"papel": u["papel"]}, {"papel": c["papel"]})
    return jsonify(_usuario_json(_buscar_usuario(con, uid)))


@bp.route("/api/usuarios/<int:uid>/ativo", methods=["POST"])
@exige("usuarios")
def ativar_usuario(uid):
    c = request.get_json(silent=True)
    if not isinstance(c, dict) or not isinstance(c.get("ativo"), bool):
        raise ErroApi("Informe ativo: true ou false", 400)
    con = obter_con()
    with transacao(con):
        u = _buscar_usuario(con, uid)
        if uid == g.usuario["id"] and not c["ativo"]:
            raise ErroApi("Você não pode desativar o seu próprio usuário", 400)
        if u["papel"] == "admin" and not c["ativo"] and _sem_outro_admin_ativo(con, uid):
            raise ErroApi("Não é possível desativar o último administrador ativo", 400)
        con.execute("UPDATE usuarios SET ativo=? WHERE id=?", (1 if c["ativo"] else 0, uid))
        registrar(con, "usuario_ativo", "usuario", uid, None, {"ativo": c["ativo"]})
    return jsonify(_usuario_json(_buscar_usuario(con, uid)))


@bp.route("/api/usuarios/<int:uid>/senha", methods=["POST"])
@exige("usuarios")
def redefinir_senha(uid):
    """O administrador define uma senha provisória; o usuário terá de trocá-la ao entrar."""
    c = request.get_json(silent=True)
    nova = c.get("senha") if isinstance(c, dict) else None
    con = obter_con()
    with transacao(con):
        u = _buscar_usuario(con, uid)
        if uid == g.usuario["id"]:
            raise ErroApi("Para trocar a sua própria senha use \"Trocar minha senha\"", 400)
        erro = validar_novo_usuario(u["login"], u["nome"], nova, u["papel"])
        if erro:
            raise ErroApi(erro, 400)
        con.execute("UPDATE usuarios SET senha_hash=?, trocar_senha=1 WHERE id=?", (generate_password_hash(nova), uid))
        registrar(con, "usuario_senha", "usuario", uid)
    return jsonify(_usuario_json(_buscar_usuario(con, uid)))


# ---------------------------------------------------------------- histórico

COLUNAS_RESUMO = ("id", "em", "usuario_login", "acao", "entidade", "entidade_id")
COLUNAS_RESERVA = ("id", "em", "usuario_login", "acao", "antes", "depois")


ACOES_DESPESA = frozenset({"despesa_lancada", "despesa_estornada", "despesas_transferidas", "despesas_recebidas", "diaria_zerada"})


def _com_json(linha, colunas):
    d = {c: linha[c] for c in colunas}
    if "em" in d and linha["acao"] in ACOES_DESPESA and not pode("despesas.hora"):
        d["em"] = d["em"][:10]            # a hora de um lançamento é dado de auditoria só do administrador
    for campo in ("antes", "depois"):
        if campo in d and d[campo]:
            d[campo] = json.loads(d[campo])
    return d


@bp.route("/api/historico", methods=["GET"])
@exige("historico.completo", "historico.resumo")
def listar_historico():
    """Administrador: tudo (com antes/depois e IP). Diretoria: só um resumo (quem, quando, o quê)."""
    completo = pode("historico.completo")
    try:
        limite = max(1, min(int(request.args.get("limite", 200)), 500))
        antes_id = int(request.args.get("antes_id", 0)) or None
    except ValueError:
        raise ErroApi("Parâmetro inválido", 400)
    filtros, args = [], []
    for campo in ("entidade", "acao"):
        if request.args.get(campo):
            filtros.append(campo + "=?")
            args.append(request.args[campo])
    if antes_id:
        filtros.append("id<?")
        args.append(antes_id)
    sql = "SELECT * FROM historico" + (" WHERE " + " AND ".join(filtros) if filtros else "") + " ORDER BY id DESC LIMIT ?"
    linhas = obter_con().execute(sql, args + [limite]).fetchall()
    colunas = tuple(linhas[0].keys()) if linhas and completo else COLUNAS_RESUMO
    return jsonify([_com_json(r, colunas) for r in linhas])


@bp.route("/api/reservas/<int:rid>/historico", methods=["GET"])
@exige("historico.reserva", "historico.completo")
def historico_da_reserva(rid):
    """Histórico de UMA reserva (aba 'Histórico' do formulário): quem fez, quando e o que mudou."""
    linhas = obter_con().execute(
        "SELECT * FROM historico WHERE entidade='reserva' AND entidade_id=? ORDER BY id DESC LIMIT 200", (rid,)).fetchall()
    return jsonify([_com_json(r, COLUNAS_RESERVA) for r in linhas])


# ---------------------------------------------------------------- backup

@bp.route("/api/backup", methods=["GET"])
@exige("backup")
def listar_backups():
    pasta = current_app.config["PASTA_BACKUP"]
    return jsonify({"pasta": pasta, "arquivos": backup.listar_backups(pasta)[::-1]})


@bp.route("/api/backup", methods=["POST"])
@exige("backup")
def fazer_backup_agora():
    """Botão 'Fazer backup agora' (administrador)."""
    pasta = current_app.config["PASTA_BACKUP"]
    if backup.backup_recente(pasta):
        raise ErroApi("Já foi feito um backup agora há pouco. Aguarde alguns segundos.", 429)
    try:
        caminho = backup.fazer_backup(current_app.config["CAMINHO_BANCO"], pasta)
    except backup.ErroBackup as e:
        raise ErroApi(str(e), 500)
    con = obter_con()
    with transacao(con):
        registrar(con, "backup", "backup", None, None, {"arquivo": os.path.basename(caminho)})
    return jsonify({"arquivo": os.path.basename(caminho), "pasta": pasta,
                    "total": len(backup.listar_backups(pasta))}), 201
