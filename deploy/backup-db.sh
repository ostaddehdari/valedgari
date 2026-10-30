#!/usr/bin/env bash
set -Eeuo pipefail

DB_FILE="${VALEDGARI_DB_FILE:-/var/www/valedgari/instance/valedgari.db}"
BACKUP_DIR="${VALEDGARI_BACKUP_DIR:-/var/backups/valedgari}"
RETENTION_DAYS="${VALEDGARI_BACKUP_RETENTION_DAYS:-14}"
KEY_FILE="${VALEDGARI_BACKUP_KEY_FILE:-/etc/valedgari-backup.key}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "${DB_FILE}" ]]; then
  echo "دیتابیس پیدا نشد: ${DB_FILE}" >&2
  exit 1
fi
if [[ ! -r "${KEY_FILE}" ]]; then
  echo "کلید رمزنگاری بکاپ خواندنی نیست: ${KEY_FILE}" >&2
  exit 1
fi

install -d -m 700 "${BACKUP_DIR}"
PLAIN_FILE="${BACKUP_DIR}/valedgari-${STAMP}.db"
ENCRYPTED_FILE="${PLAIN_FILE}.gz.enc"
trap 'rm -f -- "${PLAIN_FILE}" "${PLAIN_FILE}.gz"' EXIT
sqlite3 "${DB_FILE}" ".backup '${PLAIN_FILE}'"
sqlite3 "${PLAIN_FILE}" "PRAGMA integrity_check;" | grep -qx "ok"
gzip "${PLAIN_FILE}"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass "file:${KEY_FILE}" -in "${PLAIN_FILE}.gz" -out "${ENCRYPTED_FILE}"
chmod 600 "${ENCRYPTED_FILE}"
rm -f -- "${PLAIN_FILE}.gz"
find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'valedgari-*.db.gz.enc' -mtime "+${RETENTION_DAYS}" -delete
echo "Encrypted backup created: ${ENCRYPTED_FILE}"

