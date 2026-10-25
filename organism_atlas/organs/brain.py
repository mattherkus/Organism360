"""Мозг: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb, mixa
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.noise import gblur, labyrinth, upsample
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#ea9fb6"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("nervous",)                 # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

def paint(Z, ss, seed=19):
    o = Org((CX - 44, 10, CX + 44, 112), Z, ss, seed)
    cer = [(0, 23), (13, 24), (23, 29), (28, 39), (29.5, 51), (28, 61), (24, 68), (17, 71), (10, 68), (5, 63),
           (0, 60)]
    cb = [(0, 62), (10, 63), (17, 67), (18, 73), (11, 78), (0, 80)]
    m = o.L("mask")
    sy = lambda h: [(CX + dx, y) for dx, y in h] + [(CX - dx, y) for dx, y in reversed(h)]
    m.poly(sy(cb))
    m.tube([(CX, 60), (CX, 78), (CX, 100)], [11, 9, 7.5])
    m.poly(sy(cer))
    o.L("cer").poly(sy(cer))
    o.L("cb").poly(sy(cb))
    mask = o.m("mask")
    shp = o.shape
    cerm = o.m("cer")
    cbm = np.clip(o.m("cb", 0.6) - o.m("cer", 0.6) * 1.0, 0, 1)
    stem = np.clip(mask - np.maximum(cerm, o.m("cb")), 0, 1)
    # извилины: лабиринтный узор (считаем в фиксированном разрешении, чтобы вид не зависел от масштаба)
    ch, cw_ = int(shp[0] / Z * 3) + 2, int(shp[1] / Z * 3) + 2
    lab = upsample(labyrinth((ch, cw_), 4.6 * 3, seed=seed + 2), shp)
    sul = np.clip((-lab - 0.10) * 1.6, 0, 1)
    ridge = np.clip((lab + 0.15) * 1.2, 0, 1)
    sul = gblur(sul, 0.35 * Z) * gblur(cerm, 0.5 * Z)
    # продольная щель и боковые борозды
    fis = o.L("fis")
    fis.line([(CX, 24), (CX, 42), (CX, 60)], 2.0)
    for s in (1, -1):
        fis.line(P([(28, 49), (21, 55), (13, 59)], s < 0), 1.7)
    fi = np.clip(o.m("fis", 0.5), 0, 1)
    # мозжечок: поперечные листки
    yy = np.mgrid[0:shp[0], 0:shp[1]][0].astype(np.float32)
    warp = 2.0 * o.noise(14, 2, 31)
    fol = np.exp(-(np.sin((yy / Z) * 1.6 + warp) / 0.38) ** 2) * cbm
    alb = np.broadcast_to(hex2rgb("#efb6c2"), shp + (3,)).copy()
    alb = mixa(alb, hex2rgb("#d58fa4"), cbm)
    alb = alb * (1 - stem[..., None]) + hex2rgb("#ecc9be") * stem[..., None]
    alb = alb * (1 + 0.035 * o.noise(12, 2, 5))[..., None]
    alb = alb * (1 + 0.07 * ridge[..., None] * cerm[..., None])
    alb = alb * (1 - 0.42 * sul[..., None]) * (1 - 0.30 * fol[..., None]) * (1 - 0.6 * fi[..., None])
    alb = alb * (np.array([1.0, 0.90, 0.93], np.float32)[None, None, :] ** (sul[..., None] * 1.5))
    bump = -1.8 * sul + 0.5 * ridge * cerm - 1.2 * fol - 2.6 * fi + 0.08 * o.noise(3, 2, 6)
    rgba = shade(o, alb, bump, mask, spec=0.36, shin=18, amp=(4.0, 6.0), ambient=0.5)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/brain.json)

def parts():
    """3D-модель: примитивы из models/brain.json"""
    return load_parts("brain")
