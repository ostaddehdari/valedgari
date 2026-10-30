#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VALEDGARI_APP_DIR:-/var/www/valedgari}"
DB_FILE="${VALEDGARI_DB_FILE:-${APP_DIR}/instance/valedgari.db}"
KEY_FILE="${VALEDGARI_BACKUP_KEY_FILE:-/etc/valedgari-backup.key}"
BACKUP_FILE="${1:-}"

if [[ -z "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  echo "Usage: $0 /absolute/path/valedgari-*.db.gz.enc" >&2
  exit 2
fi
if [[ "${VALEDGARI_RESTORE_CONFIRM:-}" != "RESTORE" ]]; then
  echo "برای بازیابی، VALEDGARI_RESTORE_CONFIRM=RESTORE را تنظیم کنید." >&2
  exit 2
fi

RESTORE_DIR="$(mktemp -d /tmp/valedgari-restore.XXXXXX)"
trap 'rm -rf -- "${RESTORE_DIR}"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass "file:${KEY_FILE}" -in "${BACKUP_FILE}" -out "${RESTORE_DIR}/database.db.gz"
gzip -cd -- "${RESTORE_DIR}/database.db.gz" > "${RESTORE_DIR}/database.db"
sqlite3 "${RESTORE_DIR}/database.db" 'PRAGMA integrity_check;' | grep -qx ok

systemctl stop valedgari
if [[ -f "${DB_FILE}" ]]; then
  cp -a -- "${DB_FILE}" "${DB_FILE}.pre-restore-$(date -u +%Y%m%dT%H%M%SZ)"
fi
install -o www-data -g www-data -m 640 "${RESTORE_DIR}/database.db" "${DB_FILE}"
systemctl start valedgari
curl -fsS http://127.0.0.1:8010/health/ready >/dev/null
echo "Database restored and service is ready."
