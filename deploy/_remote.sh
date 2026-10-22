#!/usr/bin/env bash
#
# Общая часть для attach.sh и update.sh: получить код из репозитория,
# каким бы путём он ни был доступен.
#
# Зачем перебор. На этом сервере HTTPS к github.com закрыт, работает SSH.
# Но SSH-адрес вида git@github-newsite3 — это псевдоним из ~/.ssh/config
# конкретного пользователя. Под root (sudo) домашний каталог другой,
# псевдоним не читается, и ssh пытается искать в сети хост с таким
# именем — отсюда «Could not resolve hostname github-newsite3».
# Поэтому пробуем несколько адресов подряд и запоминаем рабочий.

REPO_HTTPS="https://github.com/mnikem79-tech/NewSite3.git"
REPO_SSH="git@github.com:mnikem79-tech/NewSite3.git"
REPO_SSH_443="ssh://git@ssh.github.com:443/mnikem79-tech/NewSite3.git"

ns3_diagnose() {
    local branch="${1:-main}"
    echo
    printf '\033[33mНе удалось получить код. Что видно на сервере:\033[0m\n'

    echo "  — запущено от пользователя: $(id -un) (домашний каталог: $HOME)"
    if [ "$(id -u)" = "0" ]; then
        echo "      ВНИМАНИЕ: под root настройки ssh обычного пользователя не читаются"
    fi

    echo "  — псевдонимы ssh в $HOME/.ssh/config:"
    if [ -f "$HOME/.ssh/config" ]; then
        grep -iE "^[[:space:]]*Host[[:space:]]" "$HOME/.ssh/config" | sed 's/^/      /'
    else
        echo "      файла нет"
    fi

    echo "  — ключи ssh:"
    local keys found=0
    for keys in "$HOME"/.ssh/id_*; do
        [ -f "$keys" ] || continue
        case "$keys" in *.pub) continue ;; esac
        echo "      $keys"
        found=1
    done
    [ "$found" = "1" ] || echo "      не найдены"

    echo "  — имена разрешаются:"
    for name in github.com ssh.github.com; do
        if getent hosts "$name" >/dev/null 2>&1; then
            echo "      $name — да"
        else
            echo "      $name — НЕТ (не работает DNS)"
        fi
    done

    echo "  — доступ к github.com по HTTPS:"
    echo "      код $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        "$REPO_HTTPS/info/refs?service=git-upload-pack" 2>/dev/null || true) (нужен 200)"

    echo "  — рукопожатие SSH:"
    local says
    says="$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 -o BatchMode=yes \
        -T git@github.com 2>&1 | grep -iE "success|denied|resolve|refused|timed out" | head -1)"
    echo "      ${says:-ответа нет}"
    echo
    echo "  Чаще всего помогает запуск от владельца каталога:"
    echo "      sudo -u $(stat -c %U . 2>/dev/null || echo nikem) bash deploy/update.sh"
    echo
}

# Пробует адреса по очереди и оставляет в origin тот, что ответил.
ns3_fetch() {
    local branch="${1:-main}"
    local current tried="" url key
    current="$(git remote get-url origin 2>/dev/null || true)"

    for url in "$current" "$REPO_SSH" "$REPO_SSH_443" "$REPO_HTTPS"; do
        [ -n "$url" ] || continue
        case "$tried" in *"|$url|"*) continue ;; esac
        tried="$tried|$url|"

        git remote set-url origin "$url" 2>/dev/null || git remote add origin "$url"
        if git fetch --prune -q origin "$branch" 2>/dev/null; then
            NS3_REMOTE_URL="$url"
            return 0
        fi
        printf '    \033[33m!\033[0m не отвечает: %s\n' "$url"
    done

    # Псевдоним из ~/.ssh/config мог не прочитаться, но сам ключ лежит на
    # месте. Пробуем каждый ключ напрямую — это и есть то, что псевдоним
    # обычно делает.
    for key in "$HOME"/.ssh/id_*; do
        [ -f "$key" ] || continue
        case "$key" in *.pub) continue ;; esac

        git remote set-url origin "$REPO_SSH"
        if GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o BatchMode=yes" \
           git fetch --prune -q origin "$branch" 2>/dev/null; then
            # Закрепляем ключ за этим каталогом, чтобы работало и дальше.
            git config core.sshCommand "ssh -i $key -o IdentitiesOnly=yes"
            NS3_REMOTE_URL="$REPO_SSH (ключ $(basename "$key"))"
            return 0
        fi
        printf '    \033[33m!\033[0m ключ не подошёл: %s\n' "$(basename "$key")"
    done

    [ -n "$current" ] && git remote set-url origin "$current" 2>/dev/null
    return 1
}
