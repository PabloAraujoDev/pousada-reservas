"""Ponto de entrada.

  python app.py                 liga o sistema
  python app.py criar-admin     cria o primeiro usuário administrador
  python app.py restaurar ARQ   restaura um backup (com o sistema desligado)
  python app.py servir          modo internet: servidor waitress (use com POUSADA_HTTPS, POUSADA_PROXY,
                                TRUSTED_HOSTS; veja deploy/LEIAME-PUBLICAR.md). POUSADA_PRODUCAO=1 faz o
                                mesmo com "python app.py" puro.
"""
import sys


def _avisar_se_nao_ha_usuario(app):
    from pousada.db import conectar
    from pousada.usuarios import existe_algum_usuario
    con = conectar(app.config["CAMINHO_BANCO"])
    try:
        if not existe_algum_usuario(con):
            print("ATENÇÃO: ainda não existe nenhum usuário. Feche esta janela e execute:  python app.py criar-admin")
    finally:
        con.close()


def servir(app, config):
    """Servidor de produção (waitress): sem depurador, com limites de corpo, conexões e tempo."""
    from waitress import serve
    print("Pousada Boa Esperança (modo servidor) em %s:%d" % (config.HOST, config.PORTA))
    serve(app, host=config.HOST, port=config.PORTA,
          threads=config.THREADS,
          max_request_body_size=7 * 1024 * 1024,     # Flask recusa acima de 6 MB; aqui corta antes de ler
          max_request_header_size=16 * 1024,
          connection_limit=200,
          channel_timeout=60,                        # derruba conexões lentas/paradas (slowloris)
          cleanup_interval=10,
          ident="pousada",
          clear_untrusted_proxy_headers=False)       # X-Forwarded-* só é lido pelo ProxyFix (POUSADA_PROXY=1)


def main(args):
    from pousada import config
    modo_servidor = config.SERVIDOR or args == ["servir"]
    if args and args != ["servir"]:
        from pousada.cli import executar
        return executar(args)
    from pousada import create_app
    from pousada.config import ConfigInsegura
    try:
        app = create_app(config={"PRODUCAO": True, "SERVIDOR": modo_servidor})
    except ConfigInsegura as e:
        print("RECUSADO: %s" % e)
        return 3
    _avisar_se_nao_ha_usuario(app)
    if modo_servidor:
        servir(app, config)
        return 0
    print("Pousada Boa Esperança - abra no navegador: http://localhost:%d" % config.PORTA)
    app.run(host=config.HOST, port=config.PORTA, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
