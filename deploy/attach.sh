#!/usr/bin/env bash
#
# Привязка уже работающего каталога /opt/newsite3 к репозиторию на GitHub.
# Запускается один раз. Дальше обновления идут через deploy/update.sh.
#
# Что делает:
#   1. складывает каталог в архив (на случай «всё сломалось»);
#   2. заводит здесь git и подключает его к репозиторию;
#   3. приводит отслеживаемые файлы к версии из репозитория;
#   4. включает защиту от случайной отправки паролей;
#   5. применяет миграции, собирает статику, перезапускает службу.
#
# Ваши файлы — .env, media/, logs/, .venv/ — остаются нетронутыми:
# git не удаляет то, чего нет в репозитории.
#
set -euo pipefail

TARGET="${TARGET:-/opt/newsite3}"
REPO="${REPO:-https://github.com/mnikem79-tech/NewSite3.git}"
SERVICE="${SERVICE:-newsite3}"
SETTINGS="${SETTINGS:-config.settings.prod}"

G="\033[32m"; Y="\033[33m"; R="\033[31m"; N="\033[0m"
say()  { printf "\n${G}==> %s${N}\n" "$1"; }
ok()   { printf "    ${G}✓${N} %s\n" "$1"; }
warn() { printf "    ${Y}!${N} %s\n" "$1"; }
die()  { printf "\n${R}✗ %s${N}\n" "$1" >&2; exit 1; }

[ -d "$TARGET" ] || die "Каталога $TARGET нет."
cd "$TARGET"
[ -f manage.py ] || die "В $TARGET нет manage.py — это не каталог сайта."

# --- 1. Архив на случай отката -------------------------------------------
say "Архив текущего состояния"
STAMP="$(date +%Y%m%d-%H%M%S)"
PARENT="$(dirname "$TARGET")"
NAME="$(basename "$TARGET")"
BACKUP="$PARENT/$NAME-backup-$STAMP.tar.gz"
sudo tar czf "$BACKUP" \
    --exclude=.venv --exclude=__pycache__ --exclude=staticfiles \
    -C "$PARENT" "$NAME" \
    || die "не удалось создать архив $BACKUP"
ok "$BACKUP ($(sudo du -h "$BACKUP" | cut -f1))"
echo "      вернуть всё назад: sudo tar xzf $BACKUP -C $PARENT"

# --- 2. Подключение к репозиторию ----------------------------------------
say "Подключение к репозиторию"
if [ -d .git ]; then
    ok "git здесь уже есть"
    git remote get-url origin >/dev/null 2>&1 \
        && git remote set-url origin "$REPO" \
        || git remote add origin "$REPO"
else
    git init -q -b main
    git remote add origin "$REPO"
    ok "git заведён"
fi
ok "$REPO"

say "Загрузка кода"
git fetch -q origin main
REMOTE="$(git rev-parse --short origin/main)"
ok "получена версия $REMOTE"

# --- 3. Что именно изменится ---------------------------------------------
say "Что изменится в каталоге"
CHANGED="$(git diff --stat HEAD origin/main 2>/dev/null | tail -1 || true)"
if git rev-parse HEAD >/dev/null 2>&1; then
    [ -n "$CHANGED" ] && echo "    $CHANGED" || ok "расхождений нет"
else
    COUNT="$(git ls-tree -r --name-only origin/main | wc -l)"
    ok "будет размещено $COUNT файлов из репозитория"
fi
warn "файлы вне репозитория (.env, media/, logs/, .venv/) не затрагиваются"

git reset -q --hard origin/main
ok "каталог приведён к версии $REMOTE"

# --- 4. Защита от случайной отправки паролей -----------------------------
say "Защита секретов"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
ok "отправка .env, ключей и токенов в GitHub заблокирована"

# Без имени и почты git откажется делать любой коммит на этом сервере.
git config user.name  >/dev/null 2>&1 || git config user.name  "$(hostname)"
git config user.email >/dev/null 2>&1 || git config user.email "$(whoami)@$(hostname)"
ok "подпись коммитов: $(git config user.name) <$(git config user.email)>"

# --- 5. Приведение сайта в рабочее состояние -----------------------------
say "Миграции и статика"
if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
else
    PY=python3
    warn "виртуальное окружение не найдено, беру системный python3"
fi
DJANGO_SETTINGS_MODULE="$SETTINGS" $PY manage.py migrate --noinput
DJANGO_SETTINGS_MODULE="$SETTINGS" $PY manage.py collectstatic --noinput >/dev/null
ok "готово"

say "Перезапуск службы"
sudo systemctl restart "$SERVICE"
sleep 3
if sudo systemctl is-active --quiet "$SERVICE"; then
    ok "служба $SERVICE работает"
else
    die "служба не поднялась: sudo journalctl -u $SERVICE -n 50"
fi

say "Каталог подключён к репозиторию"
echo "    версия: $(git log -1 --format='%h %s' )"
echo
echo "    Дальше обновление сайта — одной командой:"
echo "        cd $TARGET && bash deploy/update.sh"
echo
