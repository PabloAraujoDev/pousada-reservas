"""Login, logout, sessão e troca de senha."""
from flask import Blueprint, current_app, g, jsonify, redirect, request, session
from werkzeug.security import generate_password_hash

from .db import obter_con, transacao
from .erros import ErroApi
from .historico import ator_atual, registrar
from .permissoes import capacidades
from .preferencias import aplicar, ler, serializar
from .regras import agora
from .seguranca import iniciar_sessao, publico, token_csrf
from .usuarios import (_RE_LOGIN, PREFIXO_SENHA, existe_algum_usuario, limpar_falhas_login, login_bloqueado,
                       registrar_falha_login, senha_confere, validar_senha)

bp = Blueprint("auth", __name__)
MENSAGEM_LOGIN = "Login ou senha inválidos"


def estado_da_sessao():
    """Resposta de /api/sessao e do login: quem está logado e o token CSRF."""
    u = g.usuario
    corpo = {"autenticado": u is not None, "csrf": token_csrf()}
    if u is None:
        corpo["existe_usuario"] = existe_algum_usuario(obter_con())
    else:
        corpo["usuario"] = {"id": u["id"], "login": u["login"], "nome": u["nome"], "papel": u["papel"],
                            "trocar_senha": bool(u["trocar_senha"])}
        corpo["permissoes"] = sorted(capacidades(u["papel"]))
        corpo["preferencias"] = ler(u["preferencias"])          # só estética: não altera as permissões acima
    return corpo


@bp.route("/login")
@publico
def pagina_login():
    if g.usuario is not None:
        return redirect("/")
    return current_app.send_static_file("login.html")


@bp.route("/api/sessao")
@publico
def sessao():
    return jsonify(estado_da_sessao())


@bp.route("/api/login", methods=["POST"])
@publico
def login():
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict) or not isinstance(corpo.get("login"), str) or not isinstance(corpo.get("senha"), str):
        raise ErroApi("Informe login e senha", 400)
    nome, senha = corpo["login"].strip()[:80], corpo["senha"][:200]
    ip = request.remote_addr or "?"
    con = obter_con()
    # Login com formato impossível nem chega ao banco; as falhas dele contam todas numa chave só
    # (inventar textos diferentes a cada tentativa não escapa do limite, nem enche o histórico de lixo).
    valido = bool(_RE_LOGIN.fullmatch(nome))
    chave = nome if valido else "(formato inválido)"
    usuario = con.execute("SELECT * FROM usuarios WHERE login=?", (nome,)).fetchone() if valido else None
    if login_bloqueado(con, chave, ip, usuario["id"] if usuario else None):
        raise ErroApi("Muitas tentativas de login. Aguarde alguns minutos e tente de novo.", 429)
    confere = senha_confere(usuario, senha)       # com login inexistente gasta o mesmo tempo (hash falso)
    if not (confere and usuario["ativo"]):
        with transacao(con):
            registrar_falha_login(con, chave, ip)
            registrar(con, "login_falha", "usuario", usuario["id"] if usuario else None, ator=ator_atual(chave))
        raise ErroApi(MENSAGEM_LOGIN, 401)
    with transacao(con):
        limpar_falhas_login(con, chave, ip)
        con.execute("UPDATE usuarios SET ultimo_login=? WHERE id=?", (agora(), usuario["id"]))
        registrar(con, "login_ok", "usuario", usuario["id"],
                  ator={"id": usuario["id"], "login": usuario["login"], "ip": ip})
    iniciar_sessao(usuario)
    g.usuario = usuario
    return jsonify(estado_da_sessao())


@bp.route("/api/logout", methods=["POST"])
def logout():
    """Sair vale de verdade no servidor: aumenta a versão da sessão, e um cookie copiado antes deixa de funcionar."""
    if g.usuario is not None:
        con = obter_con()
        with transacao(con):
            con.execute("UPDATE usuarios SET sessao_ver=sessao_ver+1 WHERE id=?", (g.usuario["id"],))
    session.clear()
    return jsonify({"ok": True})


@bp.route("/api/senha", methods=["POST"])
def alterar_senha():
    """O próprio usuário troca a senha (precisa da senha atual)."""
    corpo = request.get_json(silent=True)
    corpo = corpo if isinstance(corpo, dict) else {}
    atual, nova = corpo.get("atual"), corpo.get("nova")
    if not isinstance(atual, str) or not isinstance(nova, str):
        raise ErroApi("Informe a senha atual e a nova", 400)
    con = obter_con()
    # Quem roubou um cookie de sessão não pode chutar a senha atual sem limite: mesmas travas do login.
    ip, chave = request.remote_addr or "?", PREFIXO_SENHA + g.usuario["login"]
    if login_bloqueado(con, chave, ip, g.usuario["id"]):
        raise ErroApi("Muitas tentativas. Aguarde alguns minutos e tente de novo.", 429)
    if not senha_confere(g.usuario, atual[:200]):
        with transacao(con):
            registrar_falha_login(con, chave, ip)
        raise ErroApi("Senha atual incorreta", 400)
    erro = validar_senha(nova, g.usuario["login"])
    if erro:
        raise ErroApi(erro, 400)
    if nova == atual:
        raise ErroApi("A nova senha precisa ser diferente da atual", 400)
    with transacao(con):
        con.execute("UPDATE usuarios SET senha_hash=?, trocar_senha=0 WHERE id=?",
                    (generate_password_hash(nova), g.usuario["id"]))
        limpar_falhas_login(con, chave, ip)
        registrar(con, "usuario_senha", "usuario", g.usuario["id"])
    novo = con.execute("SELECT * FROM usuarios WHERE id=?", (g.usuario["id"],)).fetchone()
    iniciar_sessao(novo)
    g.usuario = novo
    return jsonify(estado_da_sessao())


@bp.route("/api/preferencias", methods=["POST"])
def salvar_preferencias():
    """O próprio usuário (qualquer perfil) guarda as suas preferências de tela. Não existe alvo: nunca mexe nas de outro.

    Só estética: ocultar menus não concede nem retira permissão (as rotas de API seguem exigindo a capacidade).
    Corpo parcial: só as chaves enviadas mudam; null ou [] volta ao padrão.
    """
    con = obter_con()
    try:
        novas = aplicar(ler(g.usuario["preferencias"]), request.get_json(silent=True))
    except ValueError as e:
        raise ErroApi(str(e), 400)
    with transacao(con):
        con.execute("UPDATE usuarios SET preferencias=? WHERE id=?", (serializar(novas), g.usuario["id"]))
    return jsonify(novas)
