"""Sistema de Reservas da Pousada Boa Esperança."""
import os
from datetime import timedelta

from flask import Flask

from . import config as cfg
from . import backup
from .db import iniciar_banco


def _iniciar_banco_com_backup(app):
    """Em uso real: backup ao ligar (antes de migrar) e a cada 6 horas. Falha no backup avisa, mas não impede o uso."""
    banco, pasta = app.config["CAMINHO_BANCO"], app.config["PASTA_BACKUP"]
    ja_fez = False
    if app.config["PRODUCAO"] and os.path.exists(banco) and os.path.getsize(banco) > 0:
        try:
            print("Backup ao iniciar: %s" % backup.fazer_backup(banco, pasta))
            ja_fez = True
        except backup.ErroBackup as e:
            print("ATENÇÃO: backup ao iniciar falhou: %s" % e)
    iniciar_banco(banco, cfg.PASTA_MIGRACOES, pasta_backup=None if ja_fez else pasta)
    if app.config["PRODUCAO"]:
        app.extensions["backup_periodico"] = backup.BackupPeriodico(banco, pasta)
        app.extensions["backup_periodico"].start()


def create_app(caminho_banco=None, config=None):
    """Monta o aplicativo.

    caminho_banco: arquivo do banco (padrão: cfg.CAMINHO_BANCO).
    config: dicionário que sobrepõe as configurações (usado nos testes).
      PRODUCAO=True liga as rotinas de uso real: backup ao iniciar e a cada 6 horas.
    """
    extra = dict(config or {})
    app = Flask(__name__, static_folder=cfg.PASTA_ESTATICA, static_url_path="/static")
    app.config.update(
        CAMINHO_BANCO=caminho_banco or cfg.CAMINHO_BANCO,
        ARQUIVO_SEED=cfg.ARQUIVO_SEED,
        PASTA_INSTANCIA=cfg.PASTA_INSTANCIA,
        TRUSTED_HOSTS=list(cfg.TRUSTED_HOSTS),
        PRODUCAO=False,
        SERVIDOR=cfg.SERVIDOR,          # modo internet (waitress + exigências); veja app.py servir
        PROXY=cfg.PROXY,                # opt-in: confiar em X-Forwarded-* do proxy reverso
        HTTPS=cfg.HTTPS,                # site servido por HTTPS: cookie Secure, HSTS
        PERMITIR_HTTP=cfg.PERMITIR_HTTP,
        PASTA_LOGS=cfg.PASTA_LOGS,
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,        # folga para o envio multipart de 5 MB
        SESSION_COOKIE_NAME="pousada_sessao",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=cfg.DURACAO_SESSAO_HORAS),
        GOV_DIAS_TROCA_ENXOVAL=cfg.GOV_DIAS_TROCA_ENXOVAL, GOV_DIAS_VAGA=cfg.GOV_DIAS_VAGA,
        GOV_JANELA_DESFAZER_MIN=cfg.GOV_JANELA_DESFAZER_MIN, GOV_HORA_TROCA_ATRASADA=cfg.GOV_HORA_TROCA_ATRASADA,
        GOV_HORA_SAIDA=cfg.GOV_HORA_SAIDA, GOV_HORA_ENTRADA=cfg.GOV_HORA_ENTRADA,
        PAG_MAX_PARCELAS=cfg.PAG_MAX_PARCELAS, PAG_PARCELA_MIN_CENTAVOS=cfg.PAG_PARCELA_MIN_CENTAVOS, PAG_BANDEIRAS=cfg.PAG_BANDEIRAS,
    )
    app.config.update(extra)
    if app.config["SERVIDOR"]:
        cfg.validar_servidor(app.config)
    if app.config["HTTPS"]:
        # Cookie só trafega por HTTPS; o prefixo __Host- impede que subdomínios o sobrescrevam.
        app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_NAME="__Host-pousada_sessao")
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = cfg.carregar_chave_secreta(app.config["PASTA_INSTANCIA"],
                                                              estrito=app.config["SERVIDOR"])
    elif app.config["SERVIDOR"] and cfg.chave_fraca(app.config["SECRET_KEY"]):
        raise cfg.ConfigInsegura("SECRET_KEY fraca no modo servidor")
    if app.config["PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        # 1 proxy (o Caddy, na mesma máquina): lê IP, esquema e Host reais dele. Sem POUSADA_PROXY nada disso é lido.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=0, x_prefix=0)
    app.json.ensure_ascii = False
    app.config.setdefault("PASTA_BACKUP", backup.pasta_backup_padrao())
    _iniciar_banco_com_backup(app)

    from . import (rotas, rotas_admin, rotas_auth, rotas_despesas, rotas_governanca, rotas_hospedagem, rotas_hospedes,
                   rotas_importacao, rotas_notas, rotas_pagamentos, rotas_transferencia, rotas_lancamentos)
    from .db import fechar_con
    from .erros import registrar_erros
    from .seguranca import iniciar_seguranca, configurar_logs
    configurar_logs(app)
    registrar_erros(app)
    iniciar_seguranca(app)
    app.teardown_appcontext(fechar_con)
    for modulo in (rotas, rotas_auth, rotas_admin, rotas_importacao, rotas_governanca, rotas_despesas, rotas_notas,
                   rotas_hospedes, rotas_hospedagem, rotas_pagamentos, rotas_transferencia, rotas_lancamentos):
        app.register_blueprint(modulo.bp)
    return app
