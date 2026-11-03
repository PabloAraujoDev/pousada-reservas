"""Configurações do sistema (valores padrão e variáveis de ambiente)."""
import os
import secrets

PASTA_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Banco de dados. Para guardá-lo fora do OneDrive, defina POUSADA_DB (veja o LEIAME).
CAMINHO_BANCO = os.environ.get("POUSADA_DB", os.path.join(PASTA_PROJETO, "reservas.db"))
PASTA_MIGRACOES = os.path.join(PASTA_PROJETO, "migrations")
PASTA_ESTATICA = os.path.join(PASTA_PROJETO, "static")
ARQUIVO_SEED = os.path.join(PASTA_PROJETO, "seed.json")
PASTA_INSTANCIA = os.environ.get("POUSADA_INSTANCIA", os.path.join(PASTA_PROJETO, "instance"))

# Rede: por padrão só este computador acessa. Para a rede da pousada: POUSADA_HOST=0.0.0.0
HOST = os.environ.get("POUSADA_HOST", "127.0.0.1")
PORTA = int(os.environ.get("POUSADA_PORTA", "5000"))
# Lista opcional (separada por vírgula) dos nomes que o navegador pode usar para chegar aqui.
TRUSTED_HOSTS = [h.strip() for h in os.environ.get("TRUSTED_HOSTS", "").split(",") if h.strip()]

# Publicação na internet (tudo desligado por padrão: o uso local no PC não muda).
def _ligado(nome):
    return os.environ.get(nome, "").strip().lower() in ("1", "true", "sim", "yes", "on")


# POUSADA_PRODUCAO=1 equivale a "python app.py servir": servidor waitress + exigências de segurança.
SERVIDOR = _ligado("POUSADA_PRODUCAO")
# POUSADA_PROXY=1: há um proxy reverso de confiança (Caddy) na frente; só então X-Forwarded-* é lido.
PROXY = _ligado("POUSADA_PROXY")
# POUSADA_HTTPS=1: o site é servido por HTTPS (cookie Secure + __Host-, HSTS, upgrade-insecure-requests).
HTTPS = _ligado("POUSADA_HTTPS")
# POUSADA_PERMITIR_HTTP=1: deixa o modo servidor rodar sem HTTPS (só para rede interna, nunca na internet).
PERMITIR_HTTP = _ligado("POUSADA_PERMITIR_HTTP")
THREADS = int(os.environ.get("POUSADA_THREADS", "8"))
# Pasta dos logs (segurança.log e acesso.log). Vazio = não grava arquivo (modo local).
PASTA_LOGS = os.environ.get("POUSADA_LOG_DIR", "")

# Sessão e login
DURACAO_SESSAO_HORAS = 10
MAX_FALHAS_LOGIN = 5
JANELA_FALHAS_MINUTOS = 15
SENHA_MIN = 10


# Governança (arrumação das unidades). Valores PADRÃO enquanto o clube não decide: veja docs/GOVERNANCA.md.
GOV_DIAS_TROCA_ENXOVAL = 7        # hospedado sem arrumação há N dias ou mais: alerta de troca de enxoval
GOV_DIAS_VAGA = 14                # vaga e pronta há M dias ou mais: selo "pronta há N dias" (poeira); não vira suja
GOV_JANELA_DESFAZER_MIN = 15      # a camareira pode desfazer o PRÓPRIO "pronto" por este tempo (minutos)
GOV_HORA_TROCA_ATRASADA = "13:00"  # chegada hoje e ainda não pronta a partir desta hora: "atrasada"
GOV_HORA_SAIDA = "12:00"          # saída fixa: a unidade com saída vira "suja" sozinha a partir daqui
GOV_HORA_ENTRADA = "14:00"        # entrada fixa (só exibição)

# Pagamentos (etapa 3B). Formas aceitas pelo clube: dinheiro, Pix e cartão. NUNCA se guarda número de cartão.
PAG_MAX_PARCELAS = 12             # crédito parcelado: de 2 até este número de parcelas (decisão do clube)
PAG_PARCELA_MIN_CENTAVOS = 500    # valor mínimo de cada parcela (R$ 5,00); a 1ª parcela absorve o resto dos centavos
PAG_BANDEIRAS = ("Visa", "Mastercard", "Elo", "Amex", "Hipercard", "Outra")


class ConfigInsegura(Exception):
    """Configuração recusada no modo servidor (internet)."""


_CHAVES_FRACAS = {"chave-so-de-teste", "changeme", "secret", "dev", "password"}


def chave_fraca(chave):
    return len(chave) < 32 or chave.lower() in _CHAVES_FRACAS or len(set(chave)) < 8


def _permissao_frouxa(caminho):
    """True se, no Linux/macOS, outras pessoas do servidor conseguem ler o arquivo."""
    if os.name != "posix":
        return False
    return bool(os.stat(caminho).st_mode & 0o077)


def carregar_chave_secreta(pasta_instancia, estrito=False):
    """Chave que assina o cookie de sessão.

    Vem da variável POUSADA_SECRET_KEY ou de instance/secret.key (criada na primeira vez,
    com permissão 600, fora do Git). Não existe chave "padrão" no código.
    estrito=True (modo servidor): recusa chave fraca/curta e arquivo legível por outros usuários.
    Para trocar a chave (rotação): apague o arquivo e reinicie; todos precisarão entrar de novo.
    """
    do_ambiente = os.environ.get("POUSADA_SECRET_KEY")
    if do_ambiente:
        if estrito and chave_fraca(do_ambiente):
            raise ConfigInsegura("POUSADA_SECRET_KEY fraca: use 32+ caracteres aleatórios "
                                 "(python -c \"import secrets;print(secrets.token_hex(32))\").")
        return do_ambiente
    caminho = os.path.join(pasta_instancia, "secret.key")
    if os.path.exists(caminho):
        if estrito and _permissao_frouxa(caminho):
            raise ConfigInsegura("%s legível por outros usuários. Corrija: chmod 600 %s" % (caminho, caminho))
        with open(caminho, encoding="ascii") as fh:
            chave = fh.read().strip()
        if estrito and chave_fraca(chave):
            raise ConfigInsegura("%s contém chave fraca. Apague o arquivo para gerar outra." % caminho)
        if len(chave) >= 32:
            return chave
    os.makedirs(pasta_instancia, exist_ok=True)
    chave = secrets.token_hex(32)
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(chave)
    return chave


def validar_servidor(conf):
    """Recusa configuração insegura no modo servidor. conf: app.config."""
    erros = []
    if not conf.get("TRUSTED_HOSTS"):
        erros.append("defina TRUSTED_HOSTS (ex.: reservapousadaboaesperanca.com.br,www.reservapousadaboaesperanca.com.br)")
    if not conf.get("HTTPS") and not conf.get("PERMITIR_HTTP"):
        erros.append("defina POUSADA_HTTPS=1 (o site deve ser servido por HTTPS; use POUSADA_PERMITIR_HTTP=1 só em rede interna)")
    if conf.get("HTTPS") and not conf.get("PROXY") and not conf.get("PERMITIR_HTTP"):
        erros.append("HTTPS exige o proxy (Caddy) na frente: defina POUSADA_PROXY=1")
    if erros:
        raise ConfigInsegura("Configuração insegura para o modo servidor:\n  - " + "\n  - ".join(erros))
