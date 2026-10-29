#!/usr/bin/env bash
set -Eeuo pipefail

DB_FILE="${VALEDGARI_DB_FILE:-/var/www/valedgari/instance/valedgari.db}"
BACKUP_DIR="${VALEDGARI_BACKUP_DIR:-/var/backups/valedgari}"
RETENTION_DAYS="${VALEDGARI_BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "${DB_FILE}" ]]; then
  echo "دیتابیس پیدا نشد: ${DB_FILE}" >&2
  exit 1
fi

install -d -m 700 "${BACKUP_DIR}"
sqlite3 "${DB_FILE}" ".backup '${BACKUP_DIR}/valedgari-${STAMP}.db'"
sqlite3 "${BACKUP_DIR}/valedgari-${STAMP}.db" "PRAGMA integrity_check;" | grep -qx "ok"
gzip "${BACKUP_DIR}/valedgari-${STAMP}.db"
chmod 600 "${BACKUP_DIR}/valedgari-${STAMP}.db.gz"
find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'valedgari-*.db.gz' -mtime "+${RETENTION_DAYS}" -delete
echo "Backup created: ${BACKUP_DIR}/valedgari-${STAMP}.db.gz"

