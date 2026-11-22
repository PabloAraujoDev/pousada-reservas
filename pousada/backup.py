"""Cópias de segurança do banco SQLite e restauração.

As cópias usam a API de backup do próprio SQLite (segura mesmo com o sistema ligado, ao contrário de
copiar o arquivo no Explorer). Ficam FORA do OneDrive: o OneDrive pode sincronizar um banco aberto
pela metade e corromper tudo.
"""
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

log = logging.getLogger("pousada")

MANTER = 30                     # quantas cópias automáticas ficam guardadas
INTERVALO_HORAS = 6
INTERVALO_MINIMO_SEG = 20       # pelos pedidos da tela: backups em sequência não apagam as cópias antigas
_PADRAO_NOME = re.compile(r"^reservas_\d{8}_\d{6}(_\d+)?\.db$")


class ErroBackup(Exception):
    """Não foi possível fazer, conferir ou restaurar uma cópia de segurança."""


# ---------------------------------------------------------------- onde guardar

def pasta_backup_padrao():
    """POUSADA_BACKUP_DIR ou %LOCALAPPDATA%\\PousadaBackups (no Windows)."""
    do_ambiente = os.environ.get("POUSADA_BACKUP_DIR")
    if do_ambiente:
        return do_ambiente
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "PousadaBackups")


def validar_pasta(pasta):
    """Recusa pastas dentro do OneDrive (também resolve atalhos/links)."""
    for caminho in (pasta, os.path.realpath(pasta)):
        if "onedrive" in caminho.replace("\\", "/").lower():
            raise ErroBackup("A pasta de backup não pode ficar dentro do OneDrive (%s). "
                             "Defina POUSADA_BACKUP_DIR com outra pasta, por exemplo C:\\PousadaBackups." % pasta)
    return pasta


# ---------------------------------------------------------------- copiar

def nome_do_backup(agora=None):
    return "reservas_%s.db" % (agora or datetime.now()).strftime("%Y%m%d_%H%M%S")


def _integridade(caminho):
    """Resultado do PRAGMA integrity_check ('ok' quando está tudo certo)."""
    con = sqlite3.connect(caminho)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as e:          # arquivo que nem é um banco SQLite
        return str(e)
    finally:
        con.close()


def copiar_com_verificacao(origem, destino):
    """Copia o banco 'origem' para 'destino' e confere a integridade da cópia.

    Escreve num arquivo temporário e só renomeia no fim, para nunca deixar uma cópia pela metade.
    """
    temporario = destino + ".tmp"
    src = dst = None
    try:
        src = sqlite3.connect(origem, timeout=10)
        dst = sqlite3.connect(temporario)
        src.backup(dst)
        resultado = dst.execute("PRAGMA integrity_check").fetchone()[0]
        dst.close()
        dst = None
        if resultado != "ok":
            raise ErroBackup("A cópia de segurança falhou na verificação de integridade: %s" % resultado)
        os.replace(temporario, destino)
    except sqlite3.Error as e:
        raise ErroBackup("Não foi possível copiar o banco: %s" % e)
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()
        if os.path.exists(temporario):
            os.remove(temporario)
    return destino


def listar_backups(pasta):
    """Nomes das cópias automáticas, da mais antiga para a mais nova."""
    if not os.path.isdir(pasta):
        return []
    return sorted(f for f in os.listdir(pasta) if _PADRAO_NOME.match(f))


def backup_recente(pasta, segundos=INTERVALO_MINIMO_SEG):
    """Já existe uma cópia automática feita há menos de 'segundos'? (trava contra quem tenta empurrar as boas para fora)"""
    copias = listar_backups(pasta)
    try:
        return bool(copias) and time.time() - os.path.getmtime(os.path.join(pasta, copias[-1])) < segundos
    except OSError:
        return False


def _rotacionar(pasta, manter=MANTER):
    todos = listar_backups(pasta)
    for antigo in (todos[:-manter] if manter else todos):
        try:
            os.remove(os.path.join(pasta, antigo))
        except OSError as e:
            log.warning("Não consegui apagar o backup antigo %s: %s", antigo, e)


def fazer_backup(origem, pasta_destino, agora=None, manter=MANTER):
    """Cria 'reservas_AAAAMMDD_HHMMSS.db' em pasta_destino, confere a cópia e guarda só as 'manter' mais novas."""
    validar_pasta(pasta_destino)
    try:
        os.makedirs(pasta_destino, exist_ok=True)
    except OSError as e:
        raise ErroBackup("Não foi possível criar a pasta de backup %s: %s" % (pasta_destino, e))
    nome = nome_do_backup(agora)
    destino, k = os.path.join(pasta_destino, nome), 1
    while True:                                         # dois backups no mesmo segundo (até em threads): nome reservado de forma atômica
        try:
            os.close(os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            k += 1
            destino = os.path.join(pasta_destino, nome[:-3] + "_%d.db" % k)
        except OSError as e:
            raise ErroBackup("Não foi possível criar a cópia em %s: %s" % (pasta_destino, e))
    try:
        copiar_com_verificacao(origem, destino)
    except BaseException:
        if os.path.exists(destino) and os.path.getsize(destino) == 0:
            os.remove(destino)                          # não deixa a reserva de nome vazia
        raise
    _rotacionar(pasta_destino, manter)
    return destino


# ---------------------------------------------------------------- restaurar (sistema desligado)

def restaurar(banco, arquivo, agora=None):
    """Restaura 'arquivo' como o banco do sistema. Devolve a mensagem final.

    Guarda o banco atual como reservas_pre_restauracao_*.db, confere a integridade do backup,
    troca o arquivo e remove os restos -wal/-shm. Só funciona com o sistema desligado.
    """
    if not os.path.isfile(arquivo):
        raise ErroBackup("Arquivo de backup não encontrado: %s" % arquivo)
    if _integridade(arquivo) != "ok":
        raise ErroBackup("O arquivo de backup está danificado (falhou na verificação de integridade). Nada foi alterado.")
    con = sqlite3.connect(arquivo)
    try:
        tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    if not {"reservas", "schema_version"} <= tabelas:
        raise ErroBackup("Esse arquivo não parece ser um banco da pousada. Nada foi alterado.")
    guardado = None
    if os.path.exists(banco):
        _exigir_sistema_desligado(banco)
        pasta = os.path.dirname(os.path.abspath(banco))
        guardado = os.path.join(pasta, "reservas_pre_restauracao_%s.db" % (agora or datetime.now()).strftime("%Y%m%d_%H%M%S"))
        copiar_com_verificacao(banco, guardado)
    temporario = banco + ".restaurando"
    copiar_com_verificacao(arquivo, temporario)
    for sufixo in ("-wal", "-shm"):
        if os.path.exists(banco + sufixo):
            os.remove(banco + sufixo)
    os.replace(temporario, banco)
    msg = "Backup restaurado em %s." % banco
    if guardado:
        msg += " O banco que estava em uso foi guardado em %s." % guardado
    return msg


def _exigir_sistema_desligado(banco):
    con = sqlite3.connect(banco, timeout=1)
    try:
        con.execute("BEGIN EXCLUSIVE")
        con.execute("ROLLBACK")
    except sqlite3.OperationalError:
        raise ErroBackup("O banco está em uso. Feche o sistema (a janela preta) e tente de novo.")
    finally:
        con.close()


# ---------------------------------------------------------------- automático a cada 6 horas

class BackupPeriodico(threading.Thread):
    """Thread de fundo: faz um backup a cada INTERVALO_HORAS enquanto o sistema estiver ligado."""

    def __init__(self, banco, pasta, horas=INTERVALO_HORAS):
        super().__init__(daemon=True, name="backup-periodico")
        self.banco, self.pasta, self.horas = banco, pasta, horas
        self.parar = threading.Event()

    def run(self):
        while not self.parar.wait(self.horas * 3600):
            try:
                fazer_backup(self.banco, self.pasta)
            except Exception as e:      # nunca derruba o sistema por causa do backup
                log.error("Falha no backup automático: %s", e)
