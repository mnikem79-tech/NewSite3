"""
Правка Caddyfile: добавить магазин подкаталогом в существующий блок сайта.

Зачем отдельный инструмент, а не «допишите строку руками»: в блоке уже
живёт чужой сайт, и важно не поменять его поведение. Тонкость в порядке
директив Caddy — голый `reverse_proxy` рассматривается раньше `handle`
и забирает себе все запросы, включая наш подкаталог. Проверено: подпуть
в таком блоке отдаёт 404 от чужого сервиса. Лечится тем, что чужая
директива заворачивается в `handle { }` — для неё ничего не меняется,
зато теперь два маршрута сравниваются по длине пути, и более точный
выигрывает.

Запуск:
    python deploy/caddy_patch.py --caddyfile Caddyfile \
        --host shop.example.com --prefix /newsite3 --port 8001 \
        --out Caddyfile.new
"""

from __future__ import annotations

import argparse
import re
import sys

MARK_START = "# --- NewSite3: магазин в подкаталоге {prefix} ---"
MARK_TAKEOVER = "# --- NewSite3: магазин занимает весь этот адрес ---"
MARK_END = "# --- конец NewSite3 ---"

# Остатки прежней схемы: файла нет внутри контейнера, Caddy не стартует.
BROKEN_IMPORT = re.compile(r"^\s*import\s+/etc/caddy/newsite3\.caddy\s*$")

# Эти директивы относятся ко всем ответам сразу и остаются снаружи:
# заворачивать их в handle означало бы перестать применять их к магазину.
PASS_THROUGH = re.compile(r"^\s*(#|import\s+[a-zA-Z_]|header\b|tls\b|encode\b|log\b|$)")

# Если блок уже разложен по handle-группам, заворачивать нечего.
ALREADY_ROUTED = re.compile(r"^\s*(handle|handle_path|route)\b")


class PatchError(Exception):
    """Поправить нельзя — лучше остановиться, чем испортить рабочий файл."""


def _depth_delta(line: str) -> int:
    """
    Изменение вложенности после строки.

    Скобки в кавычках не в счёт: в Content-Security-Policy они встречаются
    и сбили бы подсчёт.
    """
    without_quotes = re.sub(r'"[^"]*"', "", line)
    return without_quotes.count("{") - without_quotes.count("}")


def find_block(lines: list[str], host: str) -> tuple[int, int]:
    """Номера строк открывающей и закрывающей скобок блока сайта."""
    opener = re.compile(r"^\s*(?!#)([^#]*\s)?" + re.escape(host) + r"\s*(,.*)?\{\s*$")

    for start, line in enumerate(lines):
        if not opener.match(line):
            continue
        depth = _depth_delta(line)
        for end in range(start + 1, len(lines)):
            depth += _depth_delta(lines[end])
            if depth == 0:
                return start, end
        raise PatchError(f"Блок {host} не закрыт — проверьте скобки в файле")

    raise PatchError(f"Блок сайта {host} в файле не найден")


def split_units(body: list[str]) -> list[list[str]]:
    """
    Разбить тело блока на directives верхнего уровня.

    Многострочная директива (`header { ... }`) остаётся одной единицей:
    разорвать её пополам значило бы получить неработающий файл.
    """
    units: list[list[str]] = []
    current: list[str] = []
    depth = 0

    for line in body:
        current.append(line)
        depth += _depth_delta(line)
        if depth == 0:
            units.append(current)
            current = []

    if current:
        raise PatchError("Непарные скобки внутри блока сайта")
    return units


def indent_of(body: list[str], default: str = "    ") -> str:
    for line in body:
        match = re.match(r"^(\s+)\S", line)
        if match:
            return match.group(1)
    return default


def build_block(prefix: str, port: int, pad: str) -> list[str]:
    return [
        f"{pad}{MARK_START.format(prefix=prefix)}",
        f"{pad}redir {prefix} {prefix}/ 308",
        f"{pad}handle_path {prefix}/* {{",
        f"{pad}{pad}reverse_proxy 127.0.0.1:{port}",
        f"{pad}}}",
        f"{pad}{MARK_END}",
    ]


def build_takeover(port: int, pad: str, replaced: list[list[str]]) -> list[str]:
    """
    Магазин занимает адрес целиком.

    Прежние директивы не удаляем, а закомментируем: вернуть сайт обратно —
    снять решётки и убрать одну строку. Удалённое пришлось бы вспоминать.
    """
    block = [f"{pad}{MARK_TAKEOVER}"]
    if replaced:
        block.append(f"{pad}# было здесь раньше (вернуть — снять решётки, убрать строку ниже):")
        for unit in replaced:
            for line in unit:
                block.append(f"{pad}#{line}" if line.strip() else f"{pad}#")
    block.append(f"{pad}reverse_proxy 127.0.0.1:{port}")
    block.append(f"{pad}{MARK_END}")
    return block


def patch(text: str, host: str, prefix: str, port: int) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")

    if MARK_END in text:
        raise PatchError("Магазин уже прописан в этом файле — правка не нужна")

    # Чистим по всему файлу, а не только в нашем блоке: эта строка ломает
    # конфигурацию целиком, в каком бы блоке она ни осталась.
    lines = [line for line in lines if not BROKEN_IMPORT.match(line)]

    start, end = find_block(lines, host)
    body = lines[start + 1 : end]

    pad = indent_of(body)
    units = split_units(body)
    routed = any(ALREADY_ROUTED.match(unit[0]) for unit in units)

    outer: list[list[str]] = []
    inner: list[list[str]] = []
    for unit in units:
        if (routed and prefix) or PASS_THROUGH.match(unit[0]):
            outer.append(unit)
        else:
            inner.append(unit)

    # Хвостовые пустые строки — не содержимое, а отбивка перед скобкой.
    while outer and not any(line.strip() for line in outer[-1]):
        outer.pop()

    new_body: list[str] = [line for unit in outer for line in unit]
    new_body.append("")

    if not prefix:
        # Весь адрес отдаётся магазину: чужие маршруты заменяются целиком.
        new_body += build_takeover(port, pad, inner)
        inner = []
    else:
        new_body += build_block(prefix, port, pad)

    if inner:
        new_body.append("")
        new_body.append(f"{pad}handle {{")
        for unit in inner:
            for line in unit:
                new_body.append(f"{pad}{line}" if line.strip() else line)
        new_body.append(f"{pad}}}")

    while new_body and not new_body[-1].strip():
        new_body.pop()

    result = lines[: start + 1] + new_body + lines[end:]
    return newline.join(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caddyfile", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--prefix", default="", help="пусто — занять адрес целиком")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.caddyfile, encoding="utf-8") as handle:
        text = handle.read()

    try:
        patched = patch(text, args.host, args.prefix, args.port)
    except PatchError as error:
        print(f"Править не стал: {error}", file=sys.stderr)
        return 2

    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        handle.write(patched)

    print(f"Готово: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
