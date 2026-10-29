#!/usr/bin/env bash
set -Eeuo pipefail

DB_FILE="/var/www/valedgari/instance/valedgari.db"
BACKUP_DIR="/var/backups/valedgari"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "${DB_FILE}" ]]; then
  echo "دیتابیس پیدا نشد: ${DB_FILE}" >&2
  exit 1
fi

install -d -m 700 "${BACKUP_DIR}"
sqlite3 "${DB_FILE}" ".backup '${BACKUP_DIR}/valedgari-${STAMP}.db'"
gzip "${BACKUP_DIR}/valedgari-${STAMP}.db"
find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'valedgari-*.db.gz' -mtime +14 -delete
echo "Backup created: ${BACKUP_DIR}/valedgari-${STAMP}.db.gz"

