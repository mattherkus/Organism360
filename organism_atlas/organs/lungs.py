"""Лёгкие: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import math

import numpy as np

from ..colors import hex2rgb, mixa
from ..geometry import CX, P, cr_spline, pip
from ..render2d.noise import gblur, upsample, worley
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#e58aa0"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("respiratory",)             # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

RLUNG = [(-30, 140), (-17, 146), (-8, 164), (-6, 190), (-6, 215), (-8, 234), (-14, 244), (-30, 248),
         (-46, 246), (-57, 236), (-62, 212), (-61, 184), (-54, 160), (-44, 146)]
LLUNG = [(30, 143), (17, 148), (9, 166), (8, 186), (22, 198), (29, 220), (27, 238), (19, 250), (31, 254),
         (46, 250), (56, 238), (60, 214), (58, 184), (50, 160), (42, 148)]


def bronchial_tree(rng, inside):
    segs = []

    def grow(p, ang, ln, w, depth):
        x, y = p
        pts, ws = [(x, y)], [w]
        a = ang
        for i in range(3):
            a += rng.normal(0, 0.10)
            x += math.sin(a) * ln / 3
            y += math.cos(a) * ln / 3
            pts.append((x, y))
            ws.append(w * (1 - 0.06 * (i + 1)))
        if depth > 0 and not inside((x, y)):
            return
        segs.append((pts, ws))
        if w < 0.95 or depth > 5:
            return
        for da in (-0.62, 0.55):
            grow(pts[-1], a + da + rng.normal(0, 0.14), ln * 0.80, w * 0.70, depth + 1)

    carina = (CX, 172)
    # правый главный бронх и доли
    grow(carina, -0.55, 24, 7.2, -1)
    grow((CX - 13, 184), -2.15, 24, 4.6, 0)
    grow((CX - 13, 184), -0.15, 26, 4.8, 0)
    grow((CX - 16, 205), -1.15, 22, 3.6, 0)
    # левый главный бронх и доли
    grow(carina, 0.95, 28, 6.6, -1)
    grow((CX + 17, 188), 2.25, 24, 4.4, 0)
    grow((CX + 17, 188), 0.25, 30, 4.6, 0)
    return segs


def paint(Z, ss, seed=3):
    o = Org((CX - 76, 96, CX + 76, 278), Z, ss, seed)
    rng = np.random.default_rng(seed)
    R, Lf = P(RLUNG), P(LLUNG)
    o.L("mask").poly(R)
    o.L("mask").poly(Lf)
    # междолевые щели
    g = o.L("groove")
    for pts in ([(-60, 176), (-48, 200), (-34, 226), (-22, 248)], [(-8, 192), (-30, 196), (-55, 200)],
                [(56, 170), (46, 200), (36, 230), (24, 254)]):
        g.line(P(pts), 1.9)
    mask = o.m("mask")
    shp = o.shape
    grv = o.m("groove", 0.7)
    core = gblur(mask, 11 * Z)
    c_edge, c_core = hex2rgb("#f0a6b8"), hex2rgb("#d9738f")
    alb = mixa(c_edge, c_core, np.clip(core * 1.5, 0, 1))
    n1, n2 = o.noise(17, 3, 1), o.noise(2.6, 2, 2)
    n3 = np.clip(o.noise(26, 2, 3) - 0.8, 0, 2)
    ch, cw_ = int(shp[0] / Z * 3) + 2, int(shp[1] / Z * 3) + 2
    f1, f2 = worley((ch, cw_), 5.6 * 3, seed + 40)
    edge_m = upsample(1 - np.clip((f2 - f1) / (0.26 * 5.6 * 3), 0, 1), shp)
    dome = upsample(1 - np.clip(f1 / (0.8 * 5.6 * 3), 0, 1), shp)
    alb = alb * (1 + 0.05 * n1 + 0.03 * n2)[..., None]
    alb = alb * (1 - 0.22 * n3[..., None] * np.array([0.5, 0.9, 0.7], np.float32))
    alb = alb * (1 - 0.11 * edge_m[..., None])
    alb = alb * (1 - 0.38 * grv[..., None])
    bump = 0.06 * n2 + 0.15 * n1 + 0.30 * dome - 0.45 * edge_m - 2.2 * grv
    rgba = shade(o, alb, bump, mask, spec=0.25, shin=14, amp=(5.0, 8.0))

    # бронхи (трахея - отдельный орган, organs/trachea.py)
    inside = lambda pt: pip(pt, cr_spline(R, True)) or pip(pt, cr_spline(Lf, True))
    tree = o.ink("bronchi")
    for (pts, ws) in bronchial_tree(rng, inside):
        tree.tube(pts, ws)
    rgba = tree.over(rgba, "#e6eef3", 0.95, amp=2.8, spec=0.35, edge_dark=0.35)
    hit = np.maximum(rgba[..., 3], gblur(tree.cov.get(), 0.6 * Z))
    return finish(o, rgba, hit)
