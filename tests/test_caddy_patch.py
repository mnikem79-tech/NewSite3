"""
Правка чужого Caddyfile.

Файл обслуживает несколько посторонних сайтов, и цена ошибки здесь выше,
чем в остальном проекте: сломанная конфигурация роняет их все сразу.
Поэтому проверяется не только «наш блок появился», но и «чужое осталось
нетронутым».
"""

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "deploy" / "caddy_patch.py"
_spec = importlib.util.spec_from_file_location("caddy_patch", MODULE_PATH)
caddy_patch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(caddy_patch)

patch = caddy_patch.patch
PatchError = caddy_patch.PatchError


PLAIN = """\
shop.example.com {
    import app_origin_tls
    import security_headers

    reverse_proxy localhost:3080
}
"""

ROUTED = """\
app.example.com {
    import security_headers

    header {
        Content-Security-Policy "frame-ancestors 'self' https://vk.com"
    }

    handle /api/* {
        reverse_proxy localhost:8000
    }

    handle {
        reverse_proxy localhost:8080
    }
}
"""


def test_bare_proxy_is_wrapped_in_handle():
    """
    Голый reverse_proxy рассматривается раньше handle и забирает все
    запросы себе — подпуть в таком блоке отдавал бы 404 чужого сервиса.
    """
    result = patch(PLAIN, "shop.example.com", "/newsite3", 8001)

    assert "handle {\n        reverse_proxy localhost:3080\n    }" in result
    assert "handle_path /newsite3/* {" in result
    assert "reverse_proxy 127.0.0.1:8001" in result


def test_shared_headers_stay_outside_handle():
    """Заголовки безопасности должны применяться и к страницам магазина."""
    result = patch(PLAIN, "shop.example.com", "/newsite3", 8001)
    body = result.split("{", 1)[1]

    assert body.index("import security_headers") < body.index("handle_path")


def test_block_with_handles_is_not_rewrapped():
    """Где маршруты уже разложены по handle, чужое трогать незачем."""
    result = patch(ROUTED, "app.example.com", "/newsite3", 8001)

    assert result.count("handle {") == 1  # тот же, что был
    assert "handle /api/* {" in result
    assert "handle_path /newsite3/* {" in result


def test_quoted_braces_do_not_break_parsing():
    """В Content-Security-Policy встречаются кавычки — скобки внутри них не в счёт."""
    result = patch(ROUTED, "app.example.com", "/newsite3", 8001)

    assert "frame-ancestors 'self' https://vk.com" in result
    assert result.rstrip().endswith("}")


def test_other_sites_are_untouched():
    source = PLAIN + "\n" + ROUTED
    result = patch(source, "shop.example.com", "/newsite3", 8001)

    assert ROUTED.strip() in result


def test_broken_import_is_removed_from_whole_file():
    """
    Строка import из прежней схемы ломает Caddy целиком, в каком бы блоке
    ни осталась: внутри контейнера этого файла нет.
    """
    source = "example.com {\n    import /etc/caddy/newsite3.caddy\n    file_server\n}\n\n" + PLAIN
    result = patch(source, "shop.example.com", "/newsite3", 8001)

    assert "newsite3.caddy" not in result


def test_redirect_without_slash_is_added():
    """Без него /newsite3 без слэша попал бы к чужому сайту."""
    result = patch(PLAIN, "shop.example.com", "/newsite3", 8001)

    assert "redir /newsite3 /newsite3/ 308" in result


def test_crlf_is_preserved():
    """Файл с сервера приходит с виндовыми переводами строк — не меняем их."""
    result = patch(PLAIN.replace("\n", "\r\n"), "shop.example.com", "/newsite3", 8001)

    assert "\r\n" in result
    assert "\n\n" not in result.replace("\r\n", "\n\n").replace("\n\n", "\r\n")


def test_second_run_refuses():
    once = patch(PLAIN, "shop.example.com", "/newsite3", 8001)

    with pytest.raises(PatchError, match="уже прописан"):
        patch(once, "shop.example.com", "/newsite3", 8001)


def test_unknown_host_refuses():
    with pytest.raises(PatchError, match="не найден"):
        patch(PLAIN, "nosuch.example.com", "/newsite3", 8001)


def test_commented_block_is_not_matched():
    """Закомментированный блок выглядит так же — вставка ушла бы в никуда."""
    source = "# shop.example.com {\n#     reverse_proxy localhost:1\n# }\n"

    with pytest.raises(PatchError, match="не найден"):
        patch(source, "shop.example.com", "/newsite3", 8001)


def test_custom_prefix_and_port():
    result = patch(PLAIN, "shop.example.com", "/shop", 9100)

    assert "handle_path /shop/* {" in result
    assert "reverse_proxy 127.0.0.1:9100" in result


# ------------------------------------------- магазин занимает адрес целиком
def test_takeover_replaces_foreign_proxy():
    result = patch(PLAIN, "shop.example.com", "", 8001)

    assert "reverse_proxy 127.0.0.1:8001" in result
    assert "#    reverse_proxy localhost:3080" in result


def test_takeover_keeps_old_config_as_comment():
    """Вернуть прежний сайт — снять решётки, а не вспоминать удалённое."""
    result = patch(ROUTED, "app.example.com", "", 8001)

    assert "#    handle /api/* {" in result
    assert "#        reverse_proxy localhost:8000" in result
    assert result.count("reverse_proxy 127.0.0.1:8001") == 1


def test_takeover_keeps_shared_directives_active():
    """Сертификат и заголовки безопасности нужны и магазину."""
    result = patch(ROUTED, "app.example.com", "", 8001)
    body = result.split("{", 1)[1]

    assert "\n    import security_headers" in body
    assert "\n        Content-Security-Policy" in body


def test_takeover_has_no_prefix_routing():
    """В корне адреса ни redir, ни handle_path не нужны."""
    result = patch(PLAIN, "shop.example.com", "", 8001)

    assert "handle_path" not in result
    assert "redir" not in result


def test_takeover_second_run_refuses():
    once = patch(PLAIN, "shop.example.com", "", 8001)

    with pytest.raises(PatchError, match="уже прописан"):
        patch(once, "shop.example.com", "", 8001)
