#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

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
if [[ "${EUID}" -ne 0 ]]; then
  echo "release.sh باید با دسترسی root اجرا شود." >&2
  exit 2
fi

# A prior root shell may have retained umask 077 after creating the backup key.
# Normalize only application source and virtualenv readability; instance data stays private.
chmod 755 "${APP_DIR}"
for source_dir in app migrations; do
  find "${APP_DIR}/${source_dir}" -type d -exec chmod 755 {} +
  find "${APP_DIR}/${source_dir}" -type f -exec chmod a+r {} +
done
chmod a+r "${APP_DIR}/wsgi.py" "${APP_DIR}/config.py"
find "${APP_DIR}/.venv" -type d -exec chmod 755 {} +
find "${APP_DIR}/.venv" -type f -exec chmod a+r {} +
find "${APP_DIR}/.venv/bin" -maxdepth 1 -type f -exec chmod 755 {} +

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

install -m 644 "${APP_DIR}/deploy/valedgari-jobs.service" "/etc/systemd/system/valedgari-jobs.service"
install -m 644 "${APP_DIR}/deploy/valedgari-jobs.timer" "/etc/systemd/system/valedgari-jobs.timer"
systemctl daemon-reload
systemctl enable --now valedgari-jobs.timer
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
