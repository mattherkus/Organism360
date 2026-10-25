"""Масштаб интерфейса (DPI Windows) и выбор размера схемы под экран."""

import math
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


ZOOM_STEP = 0.05                  # масштаб схемы меняется ступеньками: меньше перерисовок и файлов кэша
ZOOM_MIN, ZOOM_MAX = 0.5, 3.0
SIDE_W = 340 + 190 + 2 * 24 + 80  # карточка справа, панель слоёв слева и отступы (в пикселях при масштабе 1)


def fit_zoom(w, h):
    """наибольший масштаб схемы (с шагом ZOOM_STEP), при котором она влезает в w x h пикселей"""
    z = min(w / W, h / H)
    z = math.floor(z / ZOOM_STEP + 1e-6) * ZOOM_STEP
    return round(max(ZOOM_MIN, min(z, ZOOM_MAX)), 4)


def pick_zoom(root):
    """Масштаб схемы при запуске: как можно крупнее, но чтобы окно влезло в экран."""
    avail_h = 0.88 * root.winfo_screenheight() - 150 * _scale
    avail_w = 0.94 * root.winfo_screenwidth() - SIDE_W * _scale
    return fit_zoom(avail_w, avail_h)
