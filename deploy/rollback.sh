#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VALEDGARI_APP_DIR:-/var/www/valedgari}"
HEALTH_URL="${VALEDGARI_HEALTH_URL:-http://127.0.0.1:8010/health/ready}"
GOOD_COMMIT="${1:-}"
DATABASE_BACKUP="${2:-}"

if [[ -z "${GOOD_COMMIT}" || -z "${DATABASE_BACKUP}" ]]; then
  echo "Usage: $0 <known-good-commit> </absolute/encrypted-backup.db.gz.enc>" >&2
  exit 2
fi
if [[ "${VALEDGARI_ROLLBACK_CONFIRM:-}" != "ROLLBACK" ]]; then
  echo "برای بازگشت، VALEDGARI_ROLLBACK_CONFIRM=ROLLBACK را تنظیم کنید." >&2
  exit 2
fi
cd "${APP_DIR}"
git rev-parse --verify "${GOOD_COMMIT}^{commit}" >/dev/null
test -f "${DATABASE_BACKUP}"

"${APP_DIR}/deploy/backup-db.sh"
systemctl stop valedgari
git checkout --detach "${GOOD_COMMIT}"
"${APP_DIR}/.venv/bin/pip" install -r requirements.txt
VALEDGARI_RESTORE_CONFIRM=RESTORE "${APP_DIR}/deploy/restore-db.sh" "${DATABASE_BACKUP}"
curl -fsS "${HEALTH_URL}" >/dev/null
echo "Rollback completed at ${GOOD_COMMIT}."
