"""Заголовок окна в цветах темы и своя иконка вместо пёрышка Tk.

Заголовок остаётся системным (перетаскивание, прилипание к краям экрана, кнопка на панели задач работают
как обычно), но Windows 11 красит его по просьбе программы (DwmSetWindowAttribute): фон - цвет фона окна,
текст и рамка - из темы. Windows 10 умеет только тёмный заголовок, остальное молча пропускается.
"""

import math
import sys
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from ..theme import C

# атрибуты DwmSetWindowAttribute
DARK_MODE = 20                  # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 20H1+, 11)
BORDER_COLOR = 34               # DWMWA_BORDER_COLOR (Windows 11)
CAPTION_COLOR = 35              # DWMWA_CAPTION_COLOR
TEXT_COLOR = 36                 # DWMWA_TEXT_COLOR

_icons = []                     # PhotoImage иконки: держим ссылку, иначе Tk её потеряет


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


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
    """покрасить заголовок окна win (Tk или Toplevel) в текущую тему - сейчас и каждый раз, когда окно
    появляется на экране: цвет, заданный до первого показа, Windows забывает"""
    if sys.platform != "win32":
        return
    if not getattr(win, "_titlebar", False):
        win._titlebar = True
        win.bind("<Map>", lambda e: e.widget is win and _apply(win), add="+")
    _apply(win)


def _apply(win):
    try:
        hwnd = int(win.wm_frame(), 16)          # внешнее окно с заголовком (создаёт его, если ещё нет)
        _set(hwnd, DARK_MODE, int(is_dark(C["bg"])))
        _set(hwnd, CAPTION_COLOR, _colorref(C["bg"]))
        _set(hwnd, TEXT_COLOR, _colorref(C["text"]))
        _set(hwnd, BORDER_COLOR, _colorref(C["border"]))
    except Exception:                           # нет dwmapi или окно уже закрыто - заголовок останется обычным
        pass


def paint_all(root):
    """покрасить главное окно и все открытые дочерние окна (после смены темы)"""
    paint(root)
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            paint(w)


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


def set_icon(root):
    """иконка всех окон программы (заголовок и панель задач) в цветах текущей темы; уже открытые - тоже"""
    global _icons
    try:
        icons = [ImageTk.PhotoImage(icon_image(n), master=root) for n in (64, 32, 16)]
        root.iconphoto(True, *icons)               # True - и для окон, которые откроются потом
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.iconphoto(False, *icons)
        _icons = icons
    except tk.TclError:
        pass
