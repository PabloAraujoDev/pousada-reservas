#!/bin/bash
# Roda comandos do sistema (criar-admin, restaurar...) com as mesmas variaveis e o mesmo usuario do servico.
# Instalar:  sudo cp /opt/pousada/deploy/pousada-cli.sh /usr/local/sbin/pousada-cli && sudo chmod 755 /usr/local/sbin/pousada-cli
# Usar:      sudo pousada-cli criar-admin
set -e
if [ "$(id -u)" -ne 0 ]; then
    echo "Use com sudo:  sudo pousada-cli COMANDO" >&2
    exit 1
fi
set -a
. /etc/pousada.env      # so o root le este arquivo (permissao 600): por isso o sudo vem ANTES
set +a
cd /opt/pousada
exec runuser -u pousada -- /opt/pousada/venv/bin/python app.py "$@"
