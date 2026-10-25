"""Масштаб интерфейса (DPI Windows) и выбор размера схемы под экран."""

import sys

from ..geometry import H, W


_scale = 1.0          # масштаб интерфейса на экранах с «увеличением» Windows


def set_scale(value):
    global _scale
    _scale = value


def get_scale():
    return _scale


def px(v):
    return int(round(v * _scale))


def enable_dpi_awareness():
    """Просим Windows не растягивать окно: картинка остаётся чёткой при масштабе 125–200 %."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def pick_zoom(root):
    """Сколько пикселей экрана приходится на единицу схемы: как можно крупнее, но чтобы окно влезло."""
    avail_h = 0.88 * root.winfo_screenheight() - 150 * _scale
    avail_w = 0.94 * root.winfo_screenwidth() - (340 + 2 * 24 + 60) * _scale    # минус карточка и отступы
    return max(0.68, min(avail_h / H, avail_w / W, 3.0))
