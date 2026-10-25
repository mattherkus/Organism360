"""Реалистичное освещение 3D-просмотра (стиль realistic в look.json).

Считаем в линейном цвете и в конце переводим в sRGB через filmic tone mapping (ACES по яркости),
чтобы блики не выгорали в белые пятна, а оттенок ткани не менялся. Мягкие ткани:
  * просвечивание (аппроксимация SSS): «обёрнутый» диффуз, сильнее в красном канале, и красноватый
    свет, затекающий в тень;
  * влажный блеск: нормированный Блинн-Фонг с шероховатостью, которая меняется по поверхности
    (влажные и подсохшие участки), плюс отражение мягкой процедурной среды (небо/пол);
  * пятнистость цвета и сеть мелких сосудов на серозных оболочках.
"""

import math

import numpy as np

from ..colors import hex2rgb
from .look import material
from .mathutils import unit
from .textures import fbm3, tile_veins, triplanar

VEIN_TINT = np.array([0.62, 0.38, 0.55], np.float32)   # сосуды темнее и синее ткани (в линейном цвете)
MOTTLE_TINT = np.array([0.86, 0.74, 0.80], np.float32)  # тёмные пятна чуть уходят в лиловый


def srgb_to_linear(c):
    return np.power(np.clip(c, 0, 1), 2.2)


def aces(x):
    """filmic-кривая (аппроксимация ACES, Narkowicz), вход и выход - линейные значения"""
    return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def tonemap(lin):
    """кривая применяется к яркости, а цвет масштабируется целиком: оттенок ткани сохраняется
    (поканальная кривая уводит насыщенные красные в оранжевый). Пересвет мягко уходит в белый."""
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    out = lin * (aces(lum) / (lum + 1e-6))[:, None]
    over = np.clip(out.max(1, keepdims=True) - 1, 0, None)          # вылет за 1: подмешиваем белый
    return np.clip(out + over * 0.5, 0, 1)


def light_dirs(look, cam, right, up):
    """направления света из look.json (в осях камеры) в мировые"""
    out = {}
    for name in ("key", "fill", "rim"):
        d = look["lights"][name]["dir"]
        out[name] = unit(d[0] * right + d[1] * up + d[2] * cam)
    return out


def detail(look, mats, P, N, mv, alb):
    """пятнистость и сосудистая сеть поверх альбедо (линейный цвет); возвращает новое альбедо"""
    veins_tile = None
    for m_id, mt in enumerate(mats):
        sel = mv == m_id
        if not sel.any():
            continue
        prm = material(look, mt["tex"])
        Ps, a = P[sel], alb[sel]
        if prm["mottle"]:
            m = np.clip(0.5 + 0.9 * fbm3(Ps, 1.3, 3, 31 + m_id), 0, 1)[:, None]
            a = a * (1 + prm["mottle"] * (0.6 - m)) * (1 - prm["mottle"] * m * (1 - MOTTLE_TINT))
        if prm["veins"]:
            if veins_tile is None:
                veins_tile = tile_veins()
            v = triplanar(veins_tile, Ps, N[sel], 0.45)
            v = v * np.clip(0.5 + fbm3(Ps, 0.9, 2, 47 + m_id), 0, 1)        # сеть гуще в одних местах
            a = a * (1 - prm["veins"] * v[:, None] * (1 - VEIN_TINT))
        alb[sel] = a
    return alb


def shade(look, mats, P, N, alb_srgb, gloss, mv, cam, right, up, occ, vis, draft=False):
    """цвет точек поверхности в sRGB 0..1.
    alb_srgb - альбедо (sRGB), gloss - блеск части из модели, occ - затенённость AO 0..1,
    vis - освещённость ключевым светом с учётом теней 0..1 (None - без теней);
    draft - черновик при вращении: без мелких деталей, которые на ходу всё равно не видны"""
    n = len(P)
    lt = look["lights"]
    dirs = light_dirs(look, cam, right, up)
    V = cam.astype(np.float32)
    alb = srgb_to_linear(alb_srgb)
    if not draft:
        alb = detail(look, mats, P, N, mv, alb)

    # параметры материала по точкам
    sss = np.zeros(n, np.float32)
    wet = np.zeros(n, np.float32)
    rough = np.zeros(n, np.float32)
    for m_id, mt in enumerate(mats):
        sel = mv == m_id
        if not sel.any():
            continue
        prm = material(look, mt["tex"])
        sss[sel] = prm["sss"]
        w = prm["wetness"] if draft else np.clip(prm["wetness"] * (0.75 + 0.6 * fbm3(P[sel], 2.4, 2, 61 + m_id)), 0, 1)
        wet[sel] = w
        dry, damp = prm["roughness"]
        rough[sel] = dry + (damp - dry) * w

    gfac = np.clip(gloss / 0.4, 0.3, 1.6)                 # блеск части из модели: влажнее/суше
    ndv = np.clip(N @ V, 1e-4, 1)
    wrap = sss[:, None] * np.array([0.9, 0.42, 0.30], np.float32)       # красный проникает глубже
    bleed = sss[:, None] * np.array([0.42, 0.14, 0.09], np.float32)     # свет, затекающий в тень
    diffuse = np.zeros((n, 3), np.float32)
    spec = np.zeros((n, 3), np.float32)
    f0 = look["specular"]["f0"]
    for name in ("key", "fill", "rim"):
        L = dirs[name].astype(np.float32)
        col = srgb_to_linear(hex2rgb(lt[name]["color"])) * lt[name]["intensity"]
        ndl = N @ L
        w_ = wrap if name != "rim" else 0.0          # контровой свет не заворачивает на лицевую сторону
        d = np.clip((ndl[:, None] + w_) / (1 + w_), 0, 1)
        if name == "key" and vis is not None:
            v = vis[:, None]
            d = d * (v + (1 - v) * bleed)
        diffuse += d * col[None, :]
        # блик: нормированный Блинн-Фонг, показатель из шероховатости, френель Шлика
        Hh = L + V
        Hh = Hh / (np.linalg.norm(Hh) + 1e-9)
        ndh = np.clip(N @ Hh, 0, 1)
        expo = np.clip(2.0 / (rough ** 2 + 1e-4) - 2.0, 2, 4000)
        fr = f0 + (1 - f0) * (1 - max(float(Hh @ V), 0.0)) ** 5
        s = fr * (expo + 8) / (8 * math.pi) * ndh ** expo * np.clip(ndl, 0, 1)
        if name == "key" and vis is not None:
            s = s * vis
        spec += (s * gfac * look["specular"]["gain"] * (0.35 + 0.65 * wet))[:, None] * col[None, :]

    # окружение: полусфера неба/пола для рассеянного света и отражений
    sky, ground = srgb_to_linear(hex2rgb(lt["sky"])), srgb_to_linear(hex2rgb(lt["ground"]))
    world_up = np.array([0, 0, 1], np.float32)
    t = (0.5 + 0.5 * (N @ world_up))[:, None]
    amb = (ground[None, :] * (1 - t) + sky[None, :] * t) * lt["ambient"] * (1 - look["ao"]["strength"] * occ)[:, None]
    R = 2 * ndv[:, None] * N - V[None, :]
    tr = np.clip(0.5 + 0.5 * (R @ world_up), 0, 1)[:, None]
    env = ground[None, :] * (1 - tr) + sky[None, :] * tr ** 0.6
    fr_v = f0 + (1 - f0) * (1 - ndv) ** 5
    env_w = look["specular"]["env"] * fr_v * (1 - rough) ** 2 * (0.3 + 0.7 * wet) * gfac * (1 - 0.6 * occ)

    lin = alb * (diffuse * (1 - 0.35 * look["ao"]["strength"] * occ)[:, None] + amb) + spec + env * env_w[:, None]
    return np.power(tonemap(lin * look["exposure"]), 1 / 2.2)
