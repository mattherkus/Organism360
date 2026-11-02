"""Сборка тела по слоям: кожа (объём и кромка), мышцы, скелет, вены, артерии.

Каждый слой - RGBA с прямой альфой, поэтому его можно скрыть или сделать прозрачнее, не пересчитывая
остальные. Фон (по теме оформления) и свечение вокруг тела лежат под слоями, растворение у нижнего края
(ниже стоп) - над ними; compose() собирает всё в одну картинку."""

import math

import numpy as np

from ..colors import hex2rgb
from ..config import ART_C, BG, BONE_C, MUSCLE_C, RIM_LIGHT, VEIN_C
from ..geometry import CX, H, W
from ..render2d.layers import Ink, Layer
from ..render2d.lighting import lighting
from ..render2d.noise import gblur
from .muscles import muscles
from .silhouette import silhouette
from .skeleton import skeleton
from .vessels import vessels


FADE = 14          # высота растворения нижнего края схемы (тело в полный рост: стопы кончаются выше)
GLOW_Y, GLOW_R = 230, 420     # пятно фона за телом: середина (за грудью) и вертикальный радиус


BG_HI = "#1a3547"   # светлое пятно фона за телом (тёмная тема)


# на скольких пикселях схемы (при Z = 1) у её краёв гаснут пятно фона и свечение вокруг тела: тогда край схемы
# ровно цвета фона окна и шва не видно. Свечение тела у края и так слабое, а голова почти у верхнего края -
# поэтому ему полоса узкая, чтобы не срезать ореол над головой
EDGE_FADE = 60
EDGE_FADE_GLOW = 10


def edge_window(Z, shape=None, band=EDGE_FADE):
    """множитель 0..1: у самых краёв схемы 0, дальше band пикселей схемы от края - 1 (плавно)"""
    h, w = shape or (int(math.ceil(H * Z)), int(math.ceil(W * Z)))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum(np.minimum(xx + 0.5, w - 0.5 - xx), np.minimum(yy + 0.5, h - 0.5 - yy)) / Z
    k = np.clip(d / band, 0, 1)
    return k * k * (3 - 2 * k)


def glow_weight(Z, shape=None):
    """доля светлого пятна в фоне: 1 за грудью, к краям схемы 0; shape - (h, w) картинки"""
    h, w = shape or (int(math.ceil(H * Z)), int(math.ceil(W * Z)))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx / Z - CX) / 250, (yy / Z - GLOW_Y) / GLOW_R)
    return np.clip(1 - r, 0, 1) ** 1.6 * edge_window(Z, (h, w))


def background(Z, bg=BG, hi=BG_HI, t=None):
    """фон схемы: цвет bg с пятном hi за телом; t - готовый glow_weight(Z)"""
    t = glow_weight(Z) if t is None else t
    bg, hi = hex2rgb(bg), hex2rgb(hi)
    return bg[None, None, :] * (1 - t[..., None]) + hi[None, None, :] * t[..., None]


BODY_LAYERS = ("skin", "muscles", "skeleton", "veins", "arteries")     # слои тела снизу вверх, их можно скрывать
DEFAULT_LAYERS = ("skin", "skeleton", "veins", "arteries")   # видны при запуске: мышцы включают в панели «Слои»


def build_layers(Z=1.0, ss=4):
    """Слои тела. Возвращает словарь:
      glow     - свечение вокруг тела (HxWx3), прибавляется к фону; гаснет вместе с кожей;
      skin, skeleton, veins, arteries - RGBA (HxWx4) с прямой альфой, кладутся по порядку поверх фона;
      skin_hi  - добавка к коже (HxWx3): яркость кромки сверх 1, которую прямая альфа не хранит;
      fade     - столбец (H,) непрозрачности фона поверх всего тела: растворение у нижнего края;
      mask     - маска силуэта.
    compose() складывает их; при всех видимых слоях это та же картинка, что рисовалась одним куском."""
    box = (0, 0, W, H)
    h = int(math.ceil(H * Z))

    # --- силуэт
    L = Layer(box, Z, ss)
    silhouette(L)
    M = L.get()
    # внешнее свечение (снаружи силуэта, поверх фона)
    glow = gblur(M, 13 * Z)
    G = (hex2rgb("#2c7fb5") * 0.55)[None, None, :] * (glow * 0.55)[..., None]
    G = G + (hex2rgb("#2c7fb5") * 0.35)[None, None, :] * (gblur(M, 4 * Z) * 0.6)[..., None]
    # объёмная заливка: свет сверху-слева + мягкое затенение к краю
    big = gblur(M, 15 * Z) * 24 * Z
    dif, sp = lighting(big, ambient=0.42, spec=0.0, relief=1.0)
    inner = gblur(M, 6 * Z)
    body = hex2rgb("#243f55")[None, None, :] * (dif[..., None] * 1.12)
    body += hex2rgb("#4a7da3")[None, None, :] * (np.clip(inner - 0.55, 0, 1)[..., None] * 0.22)
    yy = (np.mgrid[0:M.shape[0], 0:M.shape[1]][0] / Z / H)[..., None]
    body *= (1.12 - 0.3 * yy)                               # к ногам чуть темнее
    # контур-подсветка (ярче со стороны света)
    edge = np.clip(M - gblur(M, 2.0 * Z) * 1.0, 0, 1) * 2.2
    gy, gx = np.gradient(gblur(M, 2.2 * Z))
    face = np.clip(-(gx * -0.55 + gy * -0.83) * 6, 0, 1)
    rim = np.clip(edge * (0.45 + 0.9 * face), 0, 1)
    # кожа - объём и кромка с непрозрачностью силуэта; свечение - снаружи, его доля (1 - M).
    # На полупрозрачной кромке цвет бывает ярче 1: прямая альфа его не хранит, поэтому избыток
    # (уже умноженный на M) идёт отдельной добавкой skin_hi - так сумма та же, что прежде одним куском
    x = np.clip(body, 0, 1) + hex2rgb(RIM_LIGHT)[None, None, :] * rim[..., None] * 0.9
    layers = {"glow": (G * ((1 - M) * edge_window(Z, M.shape, EDGE_FADE_GLOW))[..., None]).astype(np.float32),
              "skin": np.dstack([np.minimum(x, 1), M]).astype(np.float32),
              "skin_hi": (np.maximum(x - 1, 0) * M[..., None]).astype(np.float32)}

    # --- мышцы, кости и сосуды
    U = Ink(box, Z, ss)
    muscles(U)
    S = Ink(box, Z, ss)
    skeleton(S)
    A, V = Ink(box, Z, ss), Ink(box, Z, ss)
    vessels(A, V)
    for name, ink, color, alpha, amp, spec in (("muscles", U, MUSCLE_C, 0.5, 2.6, 0.3),
                                               ("skeleton", S, BONE_C, 0.34, 3.2, 0.35),
                                               ("veins", V, VEIN_C, 0.58, 2.4, 0.25),
                                               ("arteries", A, ART_C, 0.62, 2.4, 0.25)):
        cov, col = ink.shaded(color, amp, spec)
        layers[name] = np.dstack([col, cov * alpha]).astype(np.float32)
    # нижний край схемы плавно переходит в фон
    yy = (np.arange(h, dtype=np.float32) + 1) / Z            # +1: последняя строка - ровно цвет фона
    layers["fade"] = (np.clip((yy - (H - FADE)) / FADE, 0, 1) ** 1.5).astype(np.float32)
    layers["mask"] = M
    return layers


def over(dst, rgba, alpha=1.0):
    """положить RGBA с прямой альфой поверх dst (HxWx3, на месте); alpha - множитель непрозрачности"""
    a = rgba[..., 3:4] * alpha
    dst *= 1 - a
    dst += rgba[..., :3] * a
    return dst


def compose(layers, back, visible=DEFAULT_LAYERS, skin_opacity=1.0, fade=True):
    """схема без органов: фон back (HxWx3) + видимые слои тела. layers - из build_layers (float 0..1)
    или те же массивы в uint8 (тогда делятся на 255). fade=False - без растворения у нижнего края."""
    def f(a):
        return a.astype(np.float32) / 255 if a.dtype == np.uint8 else a

    skin = skin_opacity if "skin" in visible else 0.0
    out = back.astype(np.float32) + f(layers["glow"]) * skin
    for name in BODY_LAYERS:
        if name == "skin":
            over(out, f(layers["skin"]), skin)
            out += f(layers["skin_hi"]) * skin
        elif name in visible:
            over(out, f(layers[name]))
    if not fade:
        return out
    a = f(layers["fade"])[:, None, None]
    return out * (1 - a) + back * a
