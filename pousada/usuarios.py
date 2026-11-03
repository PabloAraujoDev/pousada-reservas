"""Usuários: papéis, regras de login/senha, criação e verificação de senha."""
import re
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from . import config
from .regras import agora, texto_limpo

PAPEIS = ("admin", "atendente", "recepcao", "camareira", "diretoria", "consulta")
_RE_LOGIN = re.compile(r"[A-Za-z0-9_.@-]{3,40}")     # usado com fullmatch: "$" aceitaria uma quebra de linha no fim
_hash_falso = None
# Senhas que qualquer lista de ataque tenta primeiro. Além da lista exata, recusa "palavra fraca + só números".
SENHAS_COMUNS = frozenset({
    "1234567890", "12345678901", "123456789012", "0123456789", "0987654321", "9876543210", "1q2w3e4r5t",
    "qwertyuiop", "abcdefghij", "administrador", "boaesperanca", "senhasenha",
})
PALAVRAS_FRACAS = frozenset({
    "admin", "senha", "password", "passw0rd", "pousada", "boaesperanca", "mudar", "trocar", "teste", "qwerty",
    "clube", "abcd", "welcome", "letmein", "iloveyou", "pablo", "recepcao", "camareira", "atendente", "diretoria",
})


def validar_senha(senha, login=""):
    """Política de senha: devolve a mensagem de erro (em português) ou None se a senha serve."""
    if not isinstance(senha, str) or len(senha) < config.SENHA_MIN:
        return "A senha precisa ter pelo menos %d caracteres" % config.SENHA_MIN
    if len(senha) > 200:
        return "Senha longa demais"
    baixa = senha.lower()
    if baixa in SENHAS_COMUNS or baixa.rstrip("0123456789!@#.") in PALAVRAS_FRACAS:
        return "Essa senha é comum demais: escolha outra"
    if isinstance(login, str) and login and baixa == login.lower():
        return "A senha não pode ser igual ao login"
    if len(set(baixa)) < 4:
        return "A senha é repetitiva demais: use caracteres variados"
    return None


def validar_novo_usuario(login, nome, senha, papel):
    """Devolve a mensagem de erro (em português) ou None se estiver tudo certo."""
    if not isinstance(login, str) or not _RE_LOGIN.fullmatch(login):
        return "Login inválido: use de 3 a 40 letras, números, ponto, hífen, sublinhado ou @"
    if not texto_limpo(nome) or not nome.strip() or len(nome.strip()) > 120:
        return "Informe o nome do usuário (até 120 caracteres)"
    erro_senha = validar_senha(senha, login)
    if erro_senha:
        return erro_senha
    if papel not in PAPEIS:
        return "Papel inválido"
    return None


def validar_edicao(nome, papel):
    """Nome e perfil de um usuário que já existe: devolve a mensagem de erro (em português) ou None."""
    if not isinstance(nome, str) or not texto_limpo(nome) or not nome.strip() or len(nome.strip()) > 120:
        return "Informe o nome do usuário (até 120 caracteres)"
    if papel not in PAPEIS:
        return "Papel inválido"
    return None


def criar_usuario(con, login, nome, senha, papel, trocar_senha=False):
    """Cria o usuário. Levanta ValueError (mensagem em português) se algo estiver errado."""
    erro = validar_novo_usuario(login, nome, senha, papel)
    if erro:
        raise ValueError(erro)
    try:
        cur = con.execute(
            "INSERT INTO usuarios (login, nome, senha_hash, papel, ativo, trocar_senha, criado) VALUES (?,?,?,?,1,?,?)",
            (login, nome.strip(), generate_password_hash(senha), papel, 1 if trocar_senha else 0, agora()))
    except sqlite3.IntegrityError:
        raise ValueError("Já existe um usuário com esse login")
    return cur.lastrowid


def senha_confere(usuario, senha):
    """Confere a senha. Se o usuário não existe, gasta o mesmo tempo com um hash falso."""
    global _hash_falso
    if usuario is None:
        if _hash_falso is None:
            _hash_falso = generate_password_hash("senha-que-ninguem-tem")
        check_password_hash(_hash_falso, senha)
        return False
    return check_password_hash(usuario["senha_hash"], senha)


def existe_algum_usuario(con):
    return con.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None


# ---------------------------------------------------------------- limite de tentativas de login

def _limite_da_janela():
    return (datetime.now() - timedelta(minutes=config.JANELA_FALHAS_MINUTOS)).strftime("%Y-%m-%d %H:%M:%S")


MAX_FALHAS_POR_CONTA = 20      # falhas na janela, de QUALQUER IP, que travam a conta (contra rodízio de IP)
MAX_FALHAS_POR_IP = 50         # falhas na janela de um mesmo IP, com qualquer login (contra chute em vários logins)
PREFIXO_SENHA = "senha:"       # as tentativas erradas de TROCA de senha usam esta marca no lugar do login


def _contar(con, sql, args):
    return con.execute("SELECT COUNT(*) FROM tentativas_login WHERE " + sql, args).fetchone()[0]


def _ip_ja_entrou(con, usuario_id, ip):
    """Este IP já fez login com sucesso nesta conta? (o dono legítimo não fica trancado por um atacante)"""
    return usuario_id is not None and con.execute(
        "SELECT 1 FROM historico WHERE acao='login_ok' AND usuario_id=? AND ip=? LIMIT 1", (usuario_id, ip)).fetchone() is not None


def login_bloqueado(con, login, ip, usuario_id=None):
    """Falhas demais? Três limites na janela de tempo: login+IP (config), só o login (todos os IPs) e só o IP.

    Os limites da conta inteira e do IP não valem para um IP que já entrou nesta conta com sucesso antes;
    assim quem tenta adivinhar senhas não consegue trancar o administrador para fora.
    """
    desde, chave = _limite_da_janela(), login.lower()
    if _contar(con, "login=? AND ip=? AND em>=?", (chave, ip, desde)) >= config.MAX_FALHAS_LOGIN:
        return True
    if (_contar(con, "ip=? AND em>=?", (ip, desde)) >= MAX_FALHAS_POR_IP
            or _contar(con, "login=? AND em>=?", (chave, desde)) >= MAX_FALHAS_POR_CONTA):
        return not _ip_ja_entrou(con, usuario_id, ip)
    return False


def registrar_falha_login(con, login, ip):
    con.execute("INSERT INTO tentativas_login (login, ip, em) VALUES (?,?,?)", (login.lower(), ip, agora()))
    con.execute("DELETE FROM tentativas_login WHERE em<?", ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),))


def limpar_falhas_login(con, login, ip):
    con.execute("DELETE FROM tentativas_login WHERE login=? AND ip=?", (login.lower(), ip))
