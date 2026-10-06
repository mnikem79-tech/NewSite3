#!/usr/bin/env bash
# =====================================================================
#  NewSite3 — скелет проекта (этап 5)
#
#  Самораспаковывающийся архив: 33 файла, проверен sha256.
#  Запуск:  bash ns3-skeleton.sh
#
#  Скрипт НЕ трогает .env, .gitignore, .env.example и .githooks/ —
#  всё, что уже настроено, остаётся как есть.
# =====================================================================
set -euo pipefail

TARGET="/opt/newsite3"
EXPECTED_SHA="b8837ada216e419f2ce68d00522d72687f498b323a21d106a4cd3ee4455c0ead"

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
ylw()  { printf '\033[33m%s\033[0m\n' "$*"; }

die() { red "ОШИБКА: $*"; exit 1; }

# ---------------------------------------------------------- проверки
[ -d "$TARGET" ] || die "нет каталога $TARGET"
cd "$TARGET"

[ -w "$TARGET" ] || die "нет прав на запись в $TARGET (нужен chown)"
[ -f "$TARGET/.env" ] || die "нет $TARGET/.env — сначала этап 3"
[ -d "$TARGET/.git" ] || ylw "ВНИМАНИЕ: git-репозиторий не найден, но продолжаем"

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
    || die "нужен Python 3.10+"
python3 -c 'import venv' 2>/dev/null || die "нет python3-venv: sudo apt install python3-venv"

# ---------------------------------------------------------- распаковка
grn "==> Распаковка скелета"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

sed -n '/^__ARCHIVE__$/,$p' "$0" | tail -n +2 | base64 -d > "$TMP/ns3.tar.gz"

ACTUAL_SHA="$(sha256sum "$TMP/ns3.tar.gz" | cut -d' ' -f1)"
[ "$ACTUAL_SHA" = "$EXPECTED_SHA" ] \
    || die "контрольная сумма не совпала (файл повреждён при передаче)
  ожидалось: $EXPECTED_SHA
  получено:  $ACTUAL_SHA"
grn "    sha256 совпал"

# Резервная копия файлов, которые будут перезаписаны
CONFLICTS="$(tar tzf "$TMP/ns3.tar.gz" | grep -v '/$' | sed 's|^\./||' \
             | while read -r f; do [ -e "$f" ] && echo "$f"; done || true)"
if [ -n "$CONFLICTS" ]; then
    BAK="$TARGET/.backup-$(date +%Y%m%d-%H%M%S)"
    ylw "    существующие файлы сохраняю в $BAK"
    mkdir -p "$BAK"
    echo "$CONFLICTS" | while read -r f; do
        mkdir -p "$BAK/$(dirname "$f")"; cp -a "$f" "$BAK/$f"
    done
fi

tar xzf "$TMP/ns3.tar.gz" -C "$TARGET"
grn "    файлов распаковано: $(tar tzf "$TMP/ns3.tar.gz" | grep -vc '/$')"

chmod +x manage.py scripts/*.sh

# ---------------------------------------------------------- venv
if [ -d "$TARGET/.venv" ]; then
    ylw "==> .venv уже существует, переиспользую"
else
    grn "==> Создаю виртуальное окружение"
    python3 -m venv "$TARGET/.venv"
fi

grn "==> Установка зависимостей (пара минут)"
"$TARGET/.venv/bin/pip" install --quiet --upgrade pip wheel
"$TARGET/.venv/bin/pip" install --quiet -r "$TARGET/requirements/dev.txt"

grn "    Django $("$TARGET/.venv/bin/python" -c 'import django;print(django.get_version())')"

# ---------------------------------------------------------- проверка
grn "==> Проверка конфигурации"
"$TARGET/.venv/bin/python" manage.py check

grn "==> Подключение к PostgreSQL"
"$TARGET/.venv/bin/python" - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT current_user, current_database()")
    user, db = c.fetchone()
print(f"    подключено: {user}@{db}")
PY

echo
grn "================= СКЕЛЕТ УСТАНОВЛЕН ================="
cat <<'NEXT'

Дальше выполни вручную:

  cd /opt/newsite3
  source .venv/bin/activate

  python manage.py migrate
  python manage.py createsuperuser        # логин — e-mail, не username
  python manage.py runserver 0.0.0.0:8000

Затем открой в браузере:
  http://nail-srv:8000/admin/     — админка
  http://nail-srv:8000/healthz/   — должно вернуть {"status": "ok"}

Если всё работает — коммит:

  git add -A
  git status --short                      # .env быть НЕ должно
  git commit -m "feat: скелет Django — настройки, кастомный пользователь, базовые модели"
  git push

NEXT
exit 0

__ARCHIVE__
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
