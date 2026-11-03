"""Comandos de terminal: python app.py criar-admin | criar-usuario | restaurar ARQUIVO | varrer-cartoes."""
import getpass
import sys

from . import config
from .backup import ErroBackup
from .db import conectar, iniciar_banco
from .usuarios import PAPEIS, criar_usuario


def _pedir_senha():
    senha = getpass.getpass("Senha (mínimo %d caracteres): " % config.SENHA_MIN)
    if getpass.getpass("Repita a senha: ") != senha:
        raise ValueError("As senhas não são iguais")
    return senha


def _criar(papel):
    iniciar_banco(config.CAMINHO_BANCO, config.PASTA_MIGRACOES)
    login = input("Login (ex.: pablo): ").strip()
    nome = input("Nome completo: ").strip() or login
    if papel is None:
        papel = input("Papel (%s): " % ", ".join(PAPEIS)).strip()
    senha = _pedir_senha()
    con = conectar(config.CAMINHO_BANCO)
    try:
        criar_usuario(con, login, nome, senha, papel)
    finally:
        con.close()
    print("Usuário '%s' criado com o papel '%s'." % (login, papel))


def executar(args):
    """Executa o comando e devolve o código de saída (0 = deu certo)."""
    comando = args[0] if args else ""
    try:
        if comando == "criar-admin":
            _criar("admin")
        elif comando == "criar-usuario":
            _criar(None)
        elif comando == "restaurar":
            from .backup import restaurar
            if len(args) != 2:
                raise ValueError("Use: python app.py restaurar ARQUIVO_DO_BACKUP.db")
            print(restaurar(config.CAMINHO_BANCO, args[1]))
        elif comando == "varrer-cartoes":
            from .varredura_cartoes import executar as varrer
            print(varrer(config.CAMINHO_BANCO))      # só leitura; não imprime nenhum número
        else:
            print("Comando desconhecido. Use: criar-admin, criar-usuario, restaurar ARQUIVO ou varrer-cartoes.")
            return 2
    except (ValueError, OSError, ErroBackup) as e:
        print("Erro: %s" % e)
        return 1
    except KeyboardInterrupt:
        print("\nCancelado.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(executar(sys.argv[1:]))
