"""Segurança de cada pedido: quem está logado, CSRF, Origin/Host e (mais abaixo) cabeçalhos.

Regra principal: TUDO é negado por padrão. Só passa sem login a rota marcada com @publico.
"""
import hashlib
import hmac
import logging
import logging.handlers
import os
import secrets
from urllib.parse import urlsplit

from flask import current_app, g, redirect, request, session

from .db import obter_con
from .erros import resposta_erro

METODOS_QUE_MUDAM = {"POST", "PUT", "PATCH", "DELETE"}
# Arquivos estáticos que a tela de login precisa (o resto de /static exige login).
ESTATICOS_PUBLICOS = {"login.js", "app.css", "logo.png",   # o que a tela de login precisa antes de entrar
                      "favicon.ico", "icon-192.png", "apple-touch-icon.png"}   # ícones da aba do navegador
# Fontes da tela (a de login também as usa antes de entrar). Lista fixa: nada mais de /static/fonts fica aberto.
FONTES_PUBLICAS = {"fonts/bricolage-grotesque-latin.woff2", "fonts/figtree-latin.woff2"}
# Quem precisa trocar a senha só pode usar estas rotas (endpoints).
ENDPOINTS_TROCA_SENHA = {"auth.sessao", "auth.logout", "auth.alterar_senha", "api.pagina", "static"}


def publico(f):
    """Marca uma rota que pode ser usada sem estar logado."""
    f._publico = True
    return f


def aceita_multipart(f):
    """Marca a rota que recebe upload de arquivo (única exceção à regra 'só JSON')."""
    f._aceita_multipart = True
    return f


# ---------------------------------------------------------------- sessão e CSRF

def assinatura_da_senha(senha_hash):
    """Muda quando a senha muda: sessões antigas deixam de valer."""
    return hashlib.sha256(senha_hash.encode("utf-8")).hexdigest()[:16]


def token_csrf():
    """Token da sessão atual (cria um se ainda não existir)."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def iniciar_sessao(usuario):
    """Abre uma sessão nova e limpa (também troca o token CSRF)."""
    session.clear()
    session.permanent = True
    session["uid"] = usuario["id"]
    session["sv"] = assinatura_da_senha(usuario["senha_hash"])
    session["sn"] = usuario["sessao_ver"]        # o logout aumenta este número no banco e invalida cookies copiados
    session["csrf"] = secrets.token_urlsafe(32)


def _carregar_usuario():
    """Recarrega o usuário do banco a CADA pedido: desativar ou trocar a senha vale na hora."""
    uid = session.get("uid")
    if uid is None:
        return None
    u = obter_con().execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if (u is None or not u["ativo"] or session.get("sv") != assinatura_da_senha(u["senha_hash"])
            or session.get("sn") != u["sessao_ver"]):
        session.clear()
        return None
    return u


def _origem_confere():
    origem = request.headers.get("Origin")
    if origem is None:
        return True            # pedidos que não vêm de navegador (ou do mesmo site sem Origin)
    return urlsplit(origem).netloc == request.host and origem != "null"


def _checar_csrf(view):
    if request.method not in METODOS_QUE_MUDAM:
        return None
    if not _origem_confere():
        return resposta_erro("Origem do pedido não permitida", 403)
    json_ok = request.mimetype == "application/json"
    multipart_ok = request.mimetype == "multipart/form-data" and getattr(view, "_aceita_multipart", False)
    if not (json_ok or multipart_ok):
        return resposta_erro("Envie os dados em JSON (Content-Type: application/json)", 415)
    enviado = request.headers.get("X-CSRF-Token", "")
    esperado = session.get("csrf", "")
    if not esperado or not hmac.compare_digest(enviado.encode("utf-8"), esperado.encode("utf-8")):
        return resposta_erro("Sessão expirada ou token inválido. Recarregue a página.", 403)
    return None


def _host_permitido():
    permitidos = current_app.config.get("TRUSTED_HOSTS")
    if not permitidos:
        return True
    return request.host.rsplit(":", 1)[0].lower() in [h.lower() for h in permitidos]


def _antes_do_pedido():
    if not _host_permitido():
        return resposta_erro("Endereço não permitido", 400)
    g.usuario = None
    view = current_app.view_functions.get(request.endpoint)
    if view is None:
        return None                              # 404/405: a resposta de erro sai normalmente
    g.usuario = _carregar_usuario()
    if request.endpoint == "static":
        nome = request.view_args.get("filename") or ""
        if nome in ESTATICOS_PUBLICOS or nome in FONTES_PUBLICAS:
            return None
    elif getattr(view, "_publico", False):
        return _checar_csrf(view)
    if g.usuario is None:
        if request.path.startswith("/api/"):
            return resposta_erro("É preciso entrar no sistema", 401)
        return redirect("/login")
    if g.usuario["trocar_senha"] and request.endpoint not in ENDPOINTS_TROCA_SENHA:
        return resposta_erro("Você precisa trocar a senha antes de continuar", 403, trocar_senha=True)
    return _checar_csrf(view)




# ---------------------------------------------------------------- cabeçalhos de segurança

POLITICA_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",                                  # sem 'unsafe-inline': todo o JavaScript está em arquivos
    "style-src 'self'",                                   # nada de terceiros: as fontes são servidas por /static/fonts
    "font-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
POLITICA_CSP_HTTPS = POLITICA_CSP + "; upgrade-insecure-requests"
# Recursos do navegador que o sistema não usa ficam desligados.
PERMISSIONS_POLICY = ("accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
                      "microphone=(), payment=(), usb=(), interest-cohort=()")
HSTS = "max-age=31536000"      # 1 ano. Sem includeSubDomains/preload de propósito (difícil de desfazer).


def _cabecalhos(resposta):
    https = current_app.config.get("HTTPS")
    resposta.headers["Content-Security-Policy"] = POLITICA_CSP_HTTPS if https else POLITICA_CSP
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    resposta.headers["Permissions-Policy"] = PERMISSIONS_POLICY
    resposta.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    resposta.headers["Server"] = "pousada"                  # não revela Werkzeug/Python/waitress e versões
    if https:
        resposta.headers["Strict-Transport-Security"] = HSTS
    if (request.path.startswith("/api/") or request.path in ("/", "/login")
            or "attachment" in resposta.headers.get("Content-Disposition", "")):
        resposta.headers["Cache-Control"] = "no-store"      # dados, PDF e CSV de quem está logado não ficam em cache
    elif request.endpoint == "static":
        fonte = request.path.startswith("/static/fonts/") and resposta.status_code in (200, 304)   # redirecionamento/404 nunca ficam uma semana em cache
        # Fontes quase nunca mudam: ficam uma semana no navegador. O resto confere se mudou a cada uso.
        resposta.headers["Cache-Control"] = "public, max-age=604800" if fonte else "no-cache"
    return resposta


# ---------------------------------------------------------------- logs (segurança e acesso)

log_seguranca = logging.getLogger("pousada.seguranca")
log_acesso = logging.getLogger("pousada.acesso")
_MARCA = "_pousada_handler"


def _limpo(texto, limite=200):
    """Texto seguro para uma linha de log: sem quebra de linha nem caracteres de controle."""
    return str(texto).encode("unicode_escape").decode("ascii")[:limite]


def configurar_logs(app):
    """Liga os arquivos rotativos se POUSADA_LOG_DIR estiver definida. Nunca grava senha, corpo, query string nem cookie."""
    pasta = app.config.get("PASTA_LOGS")
    if not pasta:
        return
    os.makedirs(pasta, exist_ok=True)
    for logger, nome in ((log_seguranca, "seguranca.log"), (log_acesso, "acesso.log")):
        for h in [h for h in logger.handlers if getattr(h, _MARCA, False)]:
            logger.removeHandler(h)
            h.close()
        h = logging.handlers.RotatingFileHandler(os.path.join(pasta, nome), maxBytes=5_000_000,
                                                 backupCount=10, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        setattr(h, _MARCA, True)
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False


def _registrar_logs(resposta):
    if not (log_seguranca.handlers or log_acesso.handlers):
        return resposta
    ip = request.remote_addr or "?"
    uid = session.get("uid", "-") if session else "-"
    rota, status = _limpo(request.path), resposta.status_code
    log_acesso.info("%s %s %s %s %s uid=%s", ip, request.method, rota, status,
                    resposta.calculate_content_length() or 0, uid)
    ep = request.endpoint
    if ep == "auth.login":
        evento = {200: "LOGIN_OK", 401: "LOGIN_FALHA", 429: "LOGIN_BLOQUEADO"}.get(status)
        if evento:
            log_seguranca.info("%s ip=%s uid=%s", evento, ip, uid)       # o nome digitado NÃO é gravado
    elif ep in ("auth.logout", "auth.alterar_senha") and status == 200:
        log_seguranca.info("%s ip=%s uid=%s", ep.split(".")[1].upper(), ip, uid)
    if status in (400, 401, 403, 413, 415, 429) and ep != "auth.login":
        log_seguranca.warning("NEGADO %s %s %s ip=%s uid=%s", status, request.method, rota, ip, uid)
    return resposta


def _apos_pedido(resposta):
    return _registrar_logs(_cabecalhos(resposta))


def iniciar_seguranca(app):
    app.before_request(_antes_do_pedido)
    app.after_request(_apos_pedido)
