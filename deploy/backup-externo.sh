#!/bin/bash
# Copia diaria dos backups do sistema para FORA da VPS (se a VPS morrer, os dados sobrevivem).
# Uso: sudo cp deploy/backup-externo.sh /usr/local/sbin/ && sudo chmod 700 /usr/local/sbin/backup-externo.sh
# Agende (como root):  echo '30 3 * * * root /usr/local/sbin/backup-externo.sh' | sudo tee /etc/cron.d/pousada-backup
# Destino: configure antes com "sudo rclone config" um remote (ex.: "pousada-nuvem", Google Drive/Backblaze/S3),
# de preferencia do tipo "crypt" (cifra os arquivos: eles tem dados de hospedes - LGPD).
set -euo pipefail
umask 077      # arquivos novos so para o dono: nunca ficam legiveis por outros, nem por um instante
ORIGEM=/var/lib/pousada/backups
REMOTO="${POUSADA_REMOTO:-pousada-nuvem:pousada-backups}"
BANCO=/var/lib/pousada/reservas.db

# Copia consistente do banco vivo agora (sqlite .backup nao trava o sistema).
# Roda como o usuario "pousada" (nao como root): se o root abrisse o banco, poderia criar arquivos -wal/-shm
# de propriedade dele, e o sistema deixaria de conseguir gravar.
mkdir -p "$ORIGEM"
chown pousada:pousada "$ORIGEM"
runuser -u pousada -- sqlite3 "$BANCO" ".backup '$ORIGEM/diario_$(date +%Y%m%d).db'"
chmod 600 "$ORIGEM"/*.db
# Mantem 30 dias localmente
find "$ORIGEM" -name 'diario_*.db' -mtime +30 -delete

rclone copy "$ORIGEM" "$REMOTO" --max-age 2d --transfers 2
echo "$(date -Is) backup externo ok" >> /var/log/pousada-backup-externo.log
