"""Заголовок окна в цветах темы и своя иконка.

Заголовок остаётся системным (перетаскивание, прилипание к краям экрана, кнопка на панели задач работают
как обычно), но Windows 11 красит его по просьбе программы (DwmSetWindowAttribute): фон - цвет фона окна,
текст и рамка - из темы. Windows 10 умеет только тёмный заголовок, остальное молча пропускается.
"""

import math
import sys

from PIL import Image, ImageDraw

from ..theme import C
from .widgets import _rgb

# атрибуты DwmSetWindowAttribute
DARK_MODE = 20                  # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 20H1+, 11)
BORDER_COLOR = 34               # DWMWA_BORDER_COLOR (Windows 11)
CAPTION_COLOR = 35              # DWMWA_CAPTION_COLOR
TEXT_COLOR = 36                 # DWMWA_TEXT_COLOR


def _colorref(c):
    r, g, b = _rgb(c)
    return r | g << 8 | b << 16


def is_dark(c):
    r, g, b = _rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b < 128


def _set(hwnd, attr, value):
    import ctypes
    v = ctypes.c_int(value)
    return ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0


def paint(win):
    """покрасить заголовок окна win (QWidget верхнего уровня) в текущую тему; окно зовёт это
    и при каждом показе (showEvent): цвет, заданный до первого показа, Windows забывает"""
    if sys.platform != "win32":
        return False
    try:
        hwnd = int(win.winId())
        _set(hwnd, DARK_MODE, int(is_dark(C["bg"])))
        _set(hwnd, CAPTION_COLOR, _colorref(C["bg"]))
        _set(hwnd, TEXT_COLOR, _colorref(C["text"]))
        _set(hwnd, BORDER_COLOR, _colorref(C["border"]))
        return True
    except Exception:                           # нет dwmapi или окно уже закрыто - заголовок останется обычным
        return False


def heart(size):
    """точки контура сердца в квадрате size x size"""
    pts = []
    for i in range(120):
        t = 2 * math.pi * i / 120
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((size / 2 + x * size / 40, size * 0.47 - y * size / 40))
    return pts


def icon_image(size, ss=4):
    """иконка: скруглённый квадрат цвета акцента с сердцем цвета текста на акценте"""
    s = size * ss
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), round(s * 0.24), fill=C["accent"])
    d.polygon(heart(s), fill=C["on_accent"])
    return im.resize((size, size), Image.LANCZOS)


def icon():
    """QIcon программы в цветах текущей темы (все размеры для заголовка и панели задач)"""
    from PySide6.QtGui import QIcon, QPixmap
    from .widgets import qimage
    ic = QIcon()
    for n in (16, 32, 64, 256):
        ic.addPixmap(QPixmap.fromImage(qimage(icon_image(n))))
    return ic


def set_icon(app):
    """иконка всех окон программы в цветах текущей темы (QApplication.setWindowIcon - и для уже открытых)"""
    app.setWindowIcon(icon())
