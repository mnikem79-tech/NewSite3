#!/usr/bin/env bash
#
# Обновление боевого сайта из GitHub.
#
#   cd /opt/newsite3 && bash deploy/update.sh
#
# Что делает: забирает изменения, доустанавливает зависимости (если список
# менялся), применяет миграции, собирает статику, перезапускает службу и
# проверяет, что сайт отвечает. Если после обновления сайт не отвечает —
# сам возвращается на предыдущий коммит и перезапускает службу обратно.
#
# Файл с паролями (.env), загруженные картинки (media/) и виртуальное
# окружение не трогаются: они в .gitignore и живут только на сервере.
#
set -euo pipefail

TARGET="${TARGET:-/opt/newsite3}"
SERVICE="${SERVICE:-newsite3}"
PORT="${PORT:-8001}"
HOST="${HOST:-sandbox.nail-app.ru}"
PREFIX="${PREFIX-}"
BRANCH="${BRANCH:-main}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

cd "$TARGET"
[ -d .git ] || die "$TARGET не является git-репозиторием. Сначала выполните привязку."
[ -x .venv/bin/python ] || die "Нет виртуального окружения $TARGET/.venv"

# Запоминаем, куда возвращаться, если обновление окажется неудачным.
PREVIOUS="$(git rev-parse HEAD)"
REQ_BEFORE="$(sha256sum requirements/*.txt 2>/dev/null | sha256sum)"

say "Проверка локальных изменений"
if ! git diff --quiet || ! git diff --cached --quiet; then
    git status --short
    die "В $TARGET есть несохранённые правки. Либо отмените их (git checkout -- .),
либо сохраните, прежде чем обновляться."
fi
ok "Рабочая копия чистая"

say "Загрузка изменений"
git fetch --prune origin
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
    ok "Уже последняя версия ($(git log -1 --format='%h %s'))"
    exit 0
fi

echo
git log --oneline --no-decorate "HEAD..origin/$BRANCH" | sed 's/^/    /'
echo

git merge --ff-only "origin/$BRANCH" >/dev/null \
    || die "История разошлась — ускоренное обновление невозможно.
Проверьте: git log --oneline --graph --all"
ok "Обновлено до $(git log -1 --format='%h %s')"

rollback() {
    warn "Возвращаюсь на предыдущую версию"
    git reset --hard "$PREVIOUS" >/dev/null
    DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py collectstatic --noinput >/dev/null 2>&1 || true
    sudo systemctl restart "$SERVICE" || true
    sleep 3
    die "Обновление отменено, сайт возвращён на $(git log -1 --format='%h %s').
Логи: sudo journalctl -u $SERVICE -n 50"
}

if [ "$REQ_BEFORE" != "$(sha256sum requirements/*.txt 2>/dev/null | sha256sum)" ]; then
    say "Список зависимостей изменился — доустанавливаю"
    .venv/bin/pip install -q -r requirements/prod.txt || rollback
    ok "Зависимости обновлены"
fi

say "Миграции и статика"
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py migrate --noinput || rollback
DJANGO_SETTINGS_MODULE=config.settings.prod .venv/bin/python manage.py collectstatic --noinput >/dev/null || rollback
ok "Готово"

say "Перезапуск службы"
sudo systemctl restart "$SERVICE"
sleep 3
systemctl is-active --quiet "$SERVICE" || rollback
ok "Служба $SERVICE работает"

say "Проверка"
# Заголовок X-Forwarded-Proto ставит Caddy; без него Django отвечает
# редиректом на https, и проверка показала бы ложную ошибку.
probe() {
    curl -s -o /dev/null -w '%{http_code}' \
        -H "Host: $HOST" -H "X-Forwarded-Proto: https" \
        "http://127.0.0.1:$PORT$PREFIX$1" 2>/dev/null || echo 000
}

for url in "/healthz/" "/"; do
    CODE="$(probe "$url")"
    [ "$CODE" = "200" ] || { warn "$CODE  $url"; rollback; }
    ok "$CODE  $url"
done

for url in "/about/" "/cart/" "/admin/login/"; do
    CODE="$(probe "$url")"
    if [ "$CODE" = "200" ]; then ok "$CODE  $url"; else warn "$CODE  $url"; fi
done

say "Сайт обновлён: https://$HOST$PREFIX/"
echo "    версия: $(git log -1 --format='%h %s (%cd)' --date=short)"
echo
