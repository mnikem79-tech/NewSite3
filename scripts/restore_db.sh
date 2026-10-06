#!/usr/bin/env bash
# Восстановление базы из бэкапа: scripts/restore_db.sh backups/файл.sql.gz
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUMP="${1:?Укажи файл бэкапа}"

[ -f "${DUMP}" ] || { echo "Файл не найден: ${DUMP}" >&2; exit 1; }
set -a; . "${PROJECT_DIR}/.env"; set +a

echo "ВНИМАНИЕ: текущие данные в ${POSTGRES_DB} будут заменены."
read -r -p "Продолжить? (yes/no) " ans
[ "${ans}" = "yes" ] || { echo "Отменено."; exit 0; }

gunzip -c "${DUMP}" | PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    --host="${POSTGRES_HOST}" --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --quiet --set ON_ERROR_STOP=1

echo "Восстановлено из ${DUMP}"
