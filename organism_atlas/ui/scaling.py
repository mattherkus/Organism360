"""Масштаб интерфейса и выбор размера схемы под экран.

Размеры в коде интерфейса - в пикселях при масштабе 100 %: px() умножает их на масштаб из настроек.
Масштаб экрана Windows (125-200 %) Qt учитывает сам: логический пиксель на таком экране крупнее, а схема
и 3D рисуются в настоящих пикселях экрана (devicePixelRatio), поэтому остаются чёткими."""

import math

from ..geometry import H, W

_scale = 1.0          # масштаб интерфейса из настроек (100 %, 125 %, ...)


def set_scale(value):
    global _scale
    _scale = value


def get_scale():
    return _scale


def px(v):
    return int(round(v * _scale))


def fs(points):
    """размер шрифта в пунктах с учётом масштаба интерфейса"""
    return points * _scale


ZOOM_STEP = 0.05                  # масштаб схемы меняется ступеньками: меньше перерисовок и файлов кэша
ZOOM_MIN, ZOOM_MAX = 0.5, 3.0
SIDE_W = 340 + 190 + 2 * 24 + 80  # карточка справа, панель слоёв слева и отступы (в пикселях при масштабе 1)


def fit_zoom(w, h):
    """наибольший масштаб схемы (с шагом ZOOM_STEP), при котором она влезает в w x h пикселей"""
    z = min(w / W, h / H)
    z = math.floor(z / ZOOM_STEP + 1e-6) * ZOOM_STEP
    return round(max(ZOOM_MIN, min(z, ZOOM_MAX)), 4)


def pick_zoom(screen_w, screen_h, dpr=1.0):
    """масштаб схемы при запуске (в пикселях экрана): как можно крупнее, но чтобы окно влезло в экран
    размером screen_w x screen_h логических пикселей"""
    avail_h = (0.88 * screen_h - 150 * _scale) * dpr
    avail_w = (0.94 * screen_w - SIDE_W * _scale) * dpr
    return fit_zoom(avail_w, avail_h)
