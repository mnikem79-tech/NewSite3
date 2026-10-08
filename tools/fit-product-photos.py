#!/usr/bin/env python3
"""Приводит фотографии товаров к единому виду для карточек каталога.

Генератор ставит предмет где попало и оставляет широкие поля — в квадратной
карточке это выглядит криво. Скрипт находит сам предмет, центрирует его,
обрезает до квадрата и выравнивает поля, чтобы вся витрина смотрелась ровно.

    python3 tools/fit-product-photos.py assets/raw assets/products
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

SIZE = 1000  # сторона готовой картинки
MARGIN = 0.07  # доля поля вокруг предмета
QUALITY = 86


def background_colour(im: Image.Image) -> tuple[int, int, int]:
    """Цвет фона — медиана по всей рамке кадра.

    По четырём углам считать нельзя: у части снимков там светлая виньетка,
    и заливка получалась белой рамкой вокруг розоватого фона.
    """
    w, h = im.size
    edge = max(6, min(w, h) // 50)
    strips = [
        im.crop((0, 0, w, edge)),
        im.crop((0, h - edge, w, h)),
        im.crop((0, 0, edge, h)),
        im.crop((w - edge, 0, w, h)),
    ]
    pixels = [p for s in strips for p in list(s.getdata())]
    return tuple(sorted(p[i] for p in pixels)[len(pixels) // 2] for i in range(3))


def subject_box(im: Image.Image, bg: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """Границы предмета.

    Плавный переход фона и мягкая тень сами по себе отличаются от среднего
    цвета, и простой порог растягивал рамку на весь кадр — предмет уезжал
    из центра. Поэтому слабые отличия сначала размываются и «съедаются»
    эрозией: остаётся только сам предмет.
    """
    diff = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L")
    diff = diff.filter(ImageFilter.GaussianBlur(2))
    mask = diff.point(lambda v: 255 if v > 22 else 0)
    mask = mask.filter(ImageFilter.MinFilter(7))  # убрать градиент и шум
    mask = mask.filter(ImageFilter.MaxFilter(7))  # вернуть предмету размер
    box = mask.getbbox()
    if box is None or (box[2] - box[0]) < im.size[0] // 50:
        return mask.getbbox() or (0, 0, *im.size)
    return box


def extend_edges(canvas: Image.Image, im: Image.Image, ox: int, oy: int) -> None:
    """Вставляет снимок и дотягивает фон до краёв холста.

    Заливка полей одним усреднённым цветом давала заметный шов: у снимков
    фон слегка неоднороден. Поэтому поля заполняются растянутыми крайними
    полосами самого снимка — переход получается незаметным.
    """
    w, h = im.size
    cw, ch = canvas.size

    if oy > 0:  # сверху
        canvas.paste(im.crop((0, 0, w, 1)).resize((w, oy), Image.BILINEAR), (ox, 0))
    if oy + h < ch:  # снизу
        pad = ch - (oy + h)
        canvas.paste(im.crop((0, h - 1, w, h)).resize((w, pad), Image.BILINEAR), (ox, oy + h))
    if ox > 0:  # слева
        canvas.paste(im.crop((0, 0, 1, h)).resize((ox, h), Image.BILINEAR), (0, oy))
    if ox + w < cw:  # справа
        pad = cw - (ox + w)
        canvas.paste(im.crop((w - 1, 0, w, h)).resize((pad, h), Image.BILINEAR), (ox + w, oy))

    # углы — растянутый угловой пиксель
    for cx_, cy_, px, py in (
        (0, 0, 0, 0),
        (ox + w, 0, w - 1, 0),
        (0, oy + h, 0, h - 1),
        (ox + w, oy + h, w - 1, h - 1),
    ):
        bw = ox if cx_ == 0 else cw - (ox + w)
        bh = oy if cy_ == 0 else ch - (oy + h)
        if bw > 0 and bh > 0:
            canvas.paste(Image.new("RGB", (bw, bh), im.getpixel((px, py))), (cx_, cy_))

    canvas.paste(im, (ox, oy))


def fit(src: Path, dst: Path) -> str:
    im = Image.open(src).convert("RGB")
    bg = background_colour(im)
    left, top, right, bottom = subject_box(im, bg)
    bw, bh = right - left, bottom - top

    # Предмет должен занимать одинаковую долю кадра во всех карточках,
    # иначе на витрине одни товары кажутся крупнее других без причины.
    side = int(max(bw, bh) / (1 - 2 * MARGIN))
    cx, cy = (left + right) // 2, (top + bottom) // 2

    canvas = Image.new("RGB", (side, side), bg)
    extend_edges(canvas, im, side // 2 - cx, side // 2 - cy)
    canvas = canvas.resize((SIZE, SIZE), Image.LANCZOS)

    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    share = round(100 * max(bw, bh) / side)
    return (
        f"{im.size[0]}x{im.size[1]} → {SIZE}x{SIZE}, "
        f"предмет {share}% кадра, {dst.stat().st_size // 1024} КБ"
    )


def main() -> int:
    src_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/raw")
    dst_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "assets/products")
    files = sorted(src_dir.glob("*.jpg")) + sorted(src_dir.glob("*.png"))
    if not files:
        print(f"В {src_dir} нет изображений", file=sys.stderr)
        return 1
    for f in files:
        print(f"  {f.stem:10} {fit(f, dst_dir / f'{f.stem.lower()}.jpg')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
