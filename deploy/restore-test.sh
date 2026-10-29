#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VALEDGARI_APP_DIR:-/var/www/valedgari}"
BACKUP_DIR="${VALEDGARI_BACKUP_DIR:-/var/backups/valedgari}"
ENV_FILE="${VALEDGARI_ENV_FILE:-/etc/valedgari.env}"
LATEST="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'valedgari-*.db.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n 1 | cut -d' ' -f2-)"

if [[ -z "${LATEST}" || ! -f "${LATEST}" ]]; then
  echo "هیچ بکاپی برای مانور بازیابی وجود ندارد." >&2
  exit 1
fi

DRILL_DIR="$(mktemp -d /tmp/valedgari-restore-drill.XXXXXX)"
trap 'rm -rf -- "${DRILL_DIR}"' EXIT
gzip -cd -- "${LATEST}" > "${DRILL_DIR}/restored.db"
RESULT="$(sqlite3 "${DRILL_DIR}/restored.db" 'PRAGMA integrity_check;')"
if [[ "${RESULT}" != "ok" ]]; then
  echo "Integrity check failed: ${RESULT}" >&2
  exit 1
fi

TABLES="$(sqlite3 "${DRILL_DIR}/restored.db" "SELECT count(*) FROM sqlite_master WHERE type='table';")"
if [[ "${TABLES}" -lt 5 ]]; then
  echo "بکاپ بازیابی‌شده جدول‌های کافی ندارد." >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
cd "${APP_DIR}"
"${APP_DIR}/.venv/bin/flask" --app wsgi:app record-operation \
  --event-type restore_drill --status success \
  --details "{\"backup\":\"$(basename "${LATEST}")\",\"tables\":${TABLES}}"
echo "Restore drill succeeded: $(basename "${LATEST}") (${TABLES} tables)"
