#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/var/www/valedgari"
ENV_FILE="/etc/valedgari.env"
SERVICE_FILE="/etc/systemd/system/valedgari.service"
SNIPPET_FILE="/etc/nginx/snippets/valedgari.conf"

if [[ "${EUID}" -ne 0 ]]; then
  echo "این اسکریپت باید با دسترسی root اجرا شود." >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/requirements.txt" ]]; then
  echo "پروژه باید ابتدا در ${APP_DIR} clone شود." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip nginx sqlite3

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

install -d -o www-data -g www-data -m 750 "${APP_DIR}/instance"
chown -R www-data:www-data "${APP_DIR}/instance"

if [[ ! -f "${ENV_FILE}" ]]; then
  SECRET_VALUE="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  install -m 600 /dev/null "${ENV_FILE}"
  {
    echo "FLASK_ENV=production"
    echo "SECRET_KEY=${SECRET_VALUE}"
    echo "DATABASE_URL=sqlite:////var/www/valedgari/instance/valedgari.db"
  } > "${ENV_FILE}"
fi

install -m 644 "${APP_DIR}/deploy/valedgari.service" "${SERVICE_FILE}"
install -m 644 "${APP_DIR}/deploy/nginx-valedgari.conf" "${SNIPPET_FILE}"

SITE_FILE="$(grep -RslE 'server_name[^;]*srun\.ir' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n 1 || true)"
if [[ -z "${SITE_FILE}" ]]; then
  echo "فایل server block دامنه srun.ir پیدا نشد. این خط را داخل server دامنه قرار دهید:"
  echo "include /etc/nginx/snippets/valedgari.conf;"
else
  TARGET_FILE="$(readlink -f "${SITE_FILE}")"
  if ! grep -qF 'include /etc/nginx/snippets/valedgari.conf;' "${TARGET_FILE}"; then
    cp -a "${TARGET_FILE}" "${TARGET_FILE}.before-valedgari"
    python3 - "${TARGET_FILE}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
position = text.rfind("}")
if position < 0:
    raise SystemExit("ساختار Nginx معتبر نیست")
line = "    include /etc/nginx/snippets/valedgari.conf;\n"
path.write_text(text[:position] + line + text[position:])
PY
  fi
fi

nginx -t
systemctl daemon-reload
systemctl enable --now valedgari
systemctl reload nginx

sleep 2
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "والدیار نصب شد. اکنون مدیر را با دستور تعاملی create-admin بسازید."

