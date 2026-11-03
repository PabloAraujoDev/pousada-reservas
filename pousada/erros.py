"""Erros da API: respostas em JSON (nunca páginas HTML) para tudo que começa com /api/."""
import logging
import sqlite3

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

log = logging.getLogger("pousada")

MENSAGENS = {
    400: "Requisição inválida", 401: "É preciso entrar no sistema", 403: "Acesso negado",
    404: "Não encontrado", 405: "Método não permitido", 413: "Arquivo grande demais (máximo 5 MB)",
    415: "Envie os dados em JSON (Content-Type: application/json)", 429: "Muitas tentativas. Aguarde alguns minutos.",
}


class ErroApi(Exception):
    """Erro previsto numa rota: dentro de uma transação, desfaz tudo e responde com o status."""

    def __init__(self, mensagem, status=400, **extra):
        super().__init__(mensagem)
        self.mensagem, self.status, self.extra = mensagem, status, extra


def resposta_erro(mensagem, status, **extra):
    corpo = {"erro": mensagem}
    corpo.update(extra)
    return jsonify(corpo), status


def _eh_api():
    return request.path.startswith("/api/")


def registrar_erros(app):
    @app.errorhandler(ErroApi)
    def _erro_api(e):
        return resposta_erro(e.mensagem, e.status, **e.extra)

    @app.errorhandler(sqlite3.OperationalError)
    def _banco_ocupado(e):
        log.warning("Banco indisponível: %s", e)
        return resposta_erro("Banco de dados ocupado, tente de novo", 503)

    @app.errorhandler(OverflowError)
    def _numero_grande(e):
        # id/número maior que o SQLite aceita (ou data fora do calendário): pedido inválido, não erro do servidor
        return resposta_erro("Valor numérico ou data fora do limite permitido", 400)

    @app.errorhandler(UnicodeError)
    def _texto_invalido(e):
        # JSON com caractere inválido (ex.: "\ud800" sozinho) que não pode ser gravado como UTF-8
        return resposta_erro("Texto com caracteres inválidos", 400)

    @app.errorhandler(RecursionError)
    def _json_fundo(e):
        return resposta_erro("Dados inválidos (estrutura aninhada demais)", 400)

    @app.errorhandler(HTTPException)
    def _http(e):
        if not _eh_api():
            return e
        return resposta_erro(MENSAGENS.get(e.code, e.description or "Erro"), e.code)

    @app.errorhandler(Exception)
    def _inesperado(e):
        log.exception("Erro inesperado em %s", request.path)
        if not _eh_api():
            return "Erro interno do servidor", 500
        return resposta_erro("Erro interno. O problema foi registrado; tente de novo.", 500)
