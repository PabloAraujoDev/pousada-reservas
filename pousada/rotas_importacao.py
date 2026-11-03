"""Rotas da importação: exemplos (seed.json), planilha Excel (prévia, confirmar, desfazer) e lista de espera."""
import io
import json
import re
import sqlite3

from flask import Blueprint, current_app, jsonify, request

from .backup import ErroBackup, fazer_backup
from .db import obter_con, transacao
from .erros import ErroApi
from .historico import ator_atual, registrar, resumo_reserva
from .importador import ImportacaoRecusada, confirmar_importacao, desfazer_lote, montar_previa
from .permissoes import exige
from .regras import MSG_CARTAO, existe_conflito, validar_reserva
from .rotas import SQL_INSERIR, hoje, valores_inserir
from .seguranca import aceita_multipart
from .validacao_xlsx import MAX_ABAS, MAX_TITULO_ABA, ErroPlanilha, conferir_zip, sha256_do_arquivo

bp = Blueprint("importacao", __name__)
LIMITE_ARQUIVO = 5 * 1024 * 1024   # 5 MB
_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def backup_antes_de_importar():
    """Importar mexe em muitos registros de uma vez: antes, guarda uma cópia. Se a cópia falhar, não importa."""
    try:
        fazer_backup(current_app.config["CAMINHO_BANCO"], current_app.config["PASTA_BACKUP"])
    except ErroBackup as e:
        raise ErroApi("Não foi possível fazer a cópia de segurança antes de importar, então nada foi importado. %s" % e, 503)


@bp.route("/api/importar", methods=["POST"])
@exige("importar")
def importar_exemplos():
    """Importa o seed.json somente se o banco estiver vazio."""
    backup_antes_de_importar()
    con = obter_con()
    with transacao(con):
        if con.execute("SELECT COUNT(*) FROM reservas").fetchone()[0] > 0:
            raise ErroApi("O banco já tem reservas; importação recusada", 409)
        try:
            with open(current_app.config["ARQUIVO_SEED"], encoding="utf-8") as fh:
                itens = json.load(fh)
        except (OSError, ValueError):
            raise ErroApi("Arquivo seed.json não encontrado ou inválido", 400)
        total = 0
        for item in itens:
            dados, erro = validar_reserva(item)
            if erro is None and existe_conflito(con, dados["a"], dados["i"], dados["f"]):
                erro = "conflito de datas"
            if erro:
                nome = item.get("nome") if isinstance(item, dict) else item
                if erro == MSG_CARTAO:      # nunca repete o texto recusado
                    raise ErroApi("Seed inválido: " + erro, 422)
                raise ErroApi("Seed inválido (%s): %s" % (nome, erro), 400)
            novo = con.execute(SQL_INSERIR, valores_inserir(dados)).lastrowid
            registrar(con, "importar", "reserva", novo, None, resumo_reserva(dados))
            total += 1
        registrar(con, "importar", "importacao", None, None, {"criadas": total, "arquivo": "seed.json"})
    return jsonify({"importadas": total}), 201


def _abrir_planilha(arquivo):
    """Valida o upload (.xlsx, até 5 MB, zip seguro) e abre com o openpyxl, só na memória.

    Devolve (planilha, sha256 do arquivo).
    """
    import openpyxl
    if arquivo is None or not arquivo.filename:
        raise ErroApi("Escolha um arquivo .xlsx", 400)
    if not arquivo.filename.lower().endswith(".xlsx"):
        raise ErroApi("Só são aceitos arquivos .xlsx (Excel)", 400)
    dados = arquivo.read(LIMITE_ARQUIVO + 1)
    if len(dados) > LIMITE_ARQUIVO:
        raise ErroApi("Arquivo grande demais (máximo 5 MB)", 413)
    try:
        conferir_zip(dados)
        wb = openpyxl.load_workbook(io.BytesIO(dados), data_only=True)
    except ErroPlanilha as e:               # mensagens nossas, em português
        raise ErroApi("Não foi possível ler o arquivo: %s" % e, 400)
    except Exception:                        # o que o openpyxl diz por dentro não vai para a tela
        raise ErroApi("Não foi possível ler o arquivo: ele não parece ser uma planilha .xlsx válida", 400)
    if len(wb.worksheets) > MAX_ABAS:
        raise ErroApi("Planilha com abas demais (máximo %d)" % MAX_ABAS, 400)
    if any(len(ws.title) > MAX_TITULO_ABA for ws in wb.worksheets):
        raise ErroApi("Planilha com nome de aba longo demais (arquivo suspeito)", 400)
    return wb, sha256_do_arquivo(dados)


def _importacao_anterior(con, sha256):
    """Já houve importação deste mesmo arquivo? (só um aviso: a importação não duplica nada)"""
    r = con.execute("SELECT id, criado, usuario FROM importacoes WHERE sha256=? ORDER BY id DESC LIMIT 1", (sha256,)).fetchone()
    return {"lote_id": r["id"], "criado": r["criado"], "usuario": r["usuario"]} if r else None


@bp.route("/api/importar/previa", methods=["POST"])
@aceita_multipart
@exige("importar")
def importar_previa():
    """Lê a planilha e mostra o que seria importado. Não grava nada."""
    wb, sha256 = _abrir_planilha(request.files.get("arquivo"))
    titulos = request.form.getlist("abas") if "abas" in request.form else None
    incluir = request.form.get("incluir_passadas", "") in ("1", "true", "sim")
    con = obter_con()
    previa = montar_previa(wb, con, hoje(), titulos, incluir)
    previa["sha256"] = sha256
    previa["importado_antes"] = _importacao_anterior(con, sha256)
    return jsonify(previa)


@bp.route("/api/importar/confirmar", methods=["POST"])
@exige("importar")
def importar_confirmar():
    """Revalida e grava as linhas aprovadas em uma única transação (tudo ou nada)."""
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        raise ErroApi("Dados inválidos", 400)
    if corpo.get("linhas") or corpo.get("pedidos"):     # sem nada a gravar não há o que proteger (e não gira as cópias)
        backup_antes_de_importar()
    sha256 = corpo.get("sha256")
    sha256 = sha256 if isinstance(sha256, str) and _RE_SHA256.match(sha256) else None
    con = obter_con()
    repetido = _importacao_anterior(con, sha256) if sha256 else None
    try:
        r = confirmar_importacao(con, corpo.get("arquivo"), corpo.get("usuario"),
                                 corpo.get("linhas", []), corpo.get("pedidos", []), ator=ator_atual(), sha256=sha256)
    except ImportacaoRecusada as e:
        raise ErroApi("Importação recusada: nada foi gravado. Corrija os itens indicados.",
                      409 if e.conflito else 400, problemas=e.problemas)
    r["importado_antes"] = repetido
    return jsonify(r), 201


@bp.route("/api/importar/desfazer/<int:lote_id>", methods=["POST"])
@exige("importar")
def importar_desfazer(lote_id):
    try:
        r = desfazer_lote(obter_con(), lote_id, ator_atual())
    except sqlite3.IntegrityError:        # trava das migrações 012/013: reserva do lote com despesas ou notas
        raise ErroApi("Alguma reserva deste lote tem despesas ou notas lançadas e não pode ser removida", 409)
    if r is None:
        raise ErroApi("Importação não encontrada", 404)
    return jsonify(r)


@bp.route("/api/pedidos", methods=["GET"])
@exige("pedidos.ver")
def listar_pedidos():
    return jsonify([dict(r) for r in obter_con().execute("SELECT * FROM pedidos ORDER BY entrada, id")])
