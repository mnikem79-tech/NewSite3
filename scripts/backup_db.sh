#!/usr/bin/env bash
# Бэкап базы NewSite3. Пароль берётся из .env, в командной строке не светится.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
KEEP_DAYS="${KEEP_DAYS:-14}"

[ -f "${PROJECT_DIR}/.env" ] || { echo "Нет ${PROJECT_DIR}/.env" >&2; exit 1; }

set -a; . "${PROJECT_DIR}/.env"; set +a

mkdir -p "${BACKUP_DIR}"; chmod 700 "${BACKUP_DIR}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/${POSTGRES_DB}-${STAMP}.sql.gz"

PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    --host="${POSTGRES_HOST}" --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --no-owner --no-privileges --clean --if-exists \
  | gzip -9 > "${OUT}"

chmod 600 "${OUT}"
echo "Бэкап: ${OUT} ($(du -h "${OUT}" | cut -f1))"

find "${BACKUP_DIR}" -name '*.sql.gz' -mtime "+${KEEP_DAYS}" -delete
echo "Старше ${KEEP_DAYS} дней — удалены."
