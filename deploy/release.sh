#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VALEDGARI_APP_DIR:-/var/www/valedgari}"
ENV_FILE="${VALEDGARI_ENV_FILE:-/etc/valedgari.env}"
DB_FILE="${VALEDGARI_DB_FILE:-${APP_DIR}/instance/valedgari.db}"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
cd "${APP_DIR}"
RUN_APP=(runuser -u www-data --preserve-environment --)

if [[ "${APP_VERSION:-}" != "stage-15" ]]; then
  echo "APP_VERSION باید در ${ENV_FILE} برابر stage-15 باشد." >&2
  exit 2
fi
if [[ "${AUTO_CREATE_SCHEMA:-}" != "0" ]]; then
  echo "AUTO_CREATE_SCHEMA باید در ${ENV_FILE} برابر 0 باشد." >&2
  exit 2
fi

if [[ -f "${DB_FILE}" ]]; then
  "${APP_DIR}/deploy/backup-db.sh"
fi
"${APP_DIR}/.venv/bin/pip" install -r requirements.txt

HAS_USERS="$(sqlite3 "${DB_FILE}" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users';" 2>/dev/null || echo 0)"
HAS_ALEMBIC="$(sqlite3 "${DB_FILE}" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='alembic_version';" 2>/dev/null || echo 0)"
if [[ "${HAS_USERS}" == "1" && "${HAS_ALEMBIC}" == "0" ]]; then
  "${RUN_APP[@]}" "${APP_DIR}/.venv/bin/flask" --app wsgi:app upgrade-legacy-stage6
  "${RUN_APP[@]}" "${APP_DIR}/.venv/bin/flask" --app wsgi:app db stamp head
fi
"${RUN_APP[@]}" "${APP_DIR}/.venv/bin/flask" --app wsgi:app db upgrade
"${RUN_APP[@]}" "${APP_DIR}/.venv/bin/flask" --app wsgi:app migrate-stage15-data
if [[ "${VALEDGARI_SEED_PILOT:-0}" == "1" ]]; then
  "${RUN_APP[@]}" "${APP_DIR}/.venv/bin/flask" --app wsgi:app seed-stage15-pilot
fi

systemctl restart valedgari
for attempt in {1..20}; do
  if curl -fsS http://127.0.0.1:8010/health/release >/dev/null; then
    echo "Stage 15 release is ready."
    exit 0
  fi
  sleep 2
done
systemctl status valedgari --no-pager --full || true
echo "Release health gate failed; use the encrypted backup for rollback." >&2
exit 1
