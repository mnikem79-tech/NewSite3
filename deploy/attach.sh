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
PREV_URL=""
if [ -d .git ]; then
    ok "git здесь уже есть"
    PREV_URL="$(git remote get-url origin 2>/dev/null || true)"
    if [ -n "$PREV_URL" ]; then
        git remote set-url origin "$REPO"
        [ "$PREV_URL" != "$REPO" ] && echo "      прежний адрес: $PREV_URL"
    else
        git remote add origin "$REPO"
    fi
else
    git init -q -b main
    git remote add origin "$REPO"
    ok "git заведён"
fi
ok "$REPO"

# --- Загрузка кода, с запасными путями -----------------------------------
# Репозиторий открытый, читать его можно без пароля. Но если на сервере
# остались чужие сохранённые учётные данные, git подставит их, и GitHub
# ответит отказом 403. Поэтому вторая попытка идёт заведомо без них.
say "Загрузка кода"

diagnose() {
    echo
    printf "${Y}Не удалось скачать код. Что показывает сервер:${N}\n"
    echo "  — переменные прокси:"
    env | grep -iE '^(http|https|all)_proxy=' | sed 's/^/      /' || echo "      не заданы"
    echo "  — настройки git про сеть и пароли:"
    git config --get-regexp '^(http\.|url\.|credential\.)' 2>/dev/null | sed 's/^/      /' || true
    git config --global --get-regexp '^(http\.|url\.|credential\.)' 2>/dev/null | sed 's/^/      /' || true
    [ -f "$HOME/.git-credentials" ] \
        && echo "      есть файл $HOME/.git-credentials ($(wc -l < "$HOME/.git-credentials") записей)"
    echo "  — доступ к GitHub напрямую:"
    echo "      код ответа $(curl -s -o /dev/null -w '%{http_code}' \
        https://github.com/mnikem79-tech/NewSite3.git/info/refs?service=git-upload-pack 2>/dev/null || true) (ожидается 200)"
    echo
    echo "  — доступ к raw.githubusercontent.com:"
    echo "      код ответа $(curl -s -o /dev/null -w '%{http_code}' \
        https://raw.githubusercontent.com/mnikem79-tech/NewSite3/main/README.md 2>/dev/null || true) (ожидается 200)"
    echo "  — SSH к GitHub:"
    SSH_SAYS="$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=7 \
        -T git@github.com 2>&1 \
        | grep -iE "authenticat|denied|timed out|refused|unreachable" \
        | head -1 || true)"
    echo "      ${SSH_SAYS:-ответа нет}"
    echo

    if git config --get http.proxy >/dev/null 2>&1 \
       || git config --global --get http.proxy >/dev/null 2>&1; then
        echo "  Похоже, git ходит через прокси. Убрать его и повторить:"
        echo "      git config --global --unset http.proxy"
        echo "      git config --unset http.proxy"
        echo "      bash /tmp/attach.sh"
        echo
    fi
    echo "  Покажите этот вывод — по нему станет видно, что именно закрыто."
    echo "  Архив каталога цел: $BACKUP"
    die "загрузка кода не удалась"
}

# Адреса одного и того же репозитория. Порядок — от простого к обходному:
# обычный HTTPS; он же заведомо без чужих паролей; SSH по имени из
# ~/.ssh/config, если оно там осталось; обычный SSH; SSH через порт 443
# на случай, когда 22-й закрыт.
CANDIDATES=(
    "$REPO"
    "$REPO|anon"
    "git@github-newsite3:mnikem79-tech/NewSite3.git"
    "git@github.com:mnikem79-tech/NewSite3.git"
    "ssh://git@ssh.github.com:443/mnikem79-tech/NewSite3.git"
)
[ -n "$PREV_URL" ] && CANDIDATES+=("$PREV_URL")

FETCHED=""
TRIED=""
for entry in "${CANDIDATES[@]}"; do
    # один и тот же адрес мог попасть в список дважды
    case "$TRIED" in *"|$entry|"*) continue ;; esac
    TRIED="$TRIED|$entry|"

    url="${entry%|anon}"
    anon=""
    [ "$entry" != "$url" ] && anon="yes"

    git remote set-url origin "$url"
    if [ -n "$anon" ]; then
        if git -c credential.helper= -c http.extraheader= \
               fetch -q origin main 2>/dev/null; then
            # чтобы чужие пароли не мешали и при обновлениях
            git config credential.helper ""
            FETCHED="$url (без сохранённых паролей)"
        fi
    elif git fetch -q origin main 2>/dev/null; then
        FETCHED="$url"
    fi

    if [ -n "$FETCHED" ]; then
        ok "код получен: $FETCHED"
        break
    fi
    if [ -n "$anon" ]; then
        warn "не отвечает: тот же адрес без сохранённых паролей"
    else
        warn "не отвечает: $url"
    fi
done

[ -n "$FETCHED" ] || diagnose

REMOTE="$(git rev-parse --short origin/main)"
ok "версия $REMOTE"

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
