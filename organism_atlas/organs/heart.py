"""Сердце: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb, mixa
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.noise import gblur
from ..render2d.organ import Org, finish, shade
from . import aorta, vena_cava


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#c8323a"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("circulatory",)             # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

HEART = [(-11, 203), (-3, 196), (9, 194), (22, 198), (33, 208), (38, 224), (36, 242), (29, 257), (21, 265),
         (11, 262), (1, 252), (-8, 240), (-13, 224), (-14, 211)]
LV = [(10, 200), (24, 198), (35, 208), (39, 225), (37, 244), (29, 259), (21, 267), (16, 250), (13, 228)]
RA = [(-15, 212), (-11, 203), (-3, 196), (4, 198), (7, 214), (5, 232), (-3, 243), (-10, 238), (-14, 224)]
RAUR = [(-4, 200), (-2, 192), (6, 190), (10, 196), (8, 204)]
LAUR = [(26, 201), (31, 196), (38, 201), (38, 211), (32, 214)]


def paint(Z, ss, seed=5):
    o = Org((CX - 56, 126, CX + 62, 284), Z, ss, seed)
    o.L("mask").poly(P(HEART))
    o.L("lv").poly(P(LV))
    o.L("ra").poly(P(RA))
    au = o.L("aur")
    au.poly(P(RAUR))
    au.poly(P(LAUR))
    mask = o.m("mask")
    # коронарные борозды и жир
    fat = o.L("fat")
    for pts, w in (([(5, 201), (6, 216), (4, 232), (-2, 244)], 3.6), ([(10, 203), (14, 224), (18, 244), (21, 262)], 3.6),
                   ([(12, 200), (24, 199), (36, 206)], 3.2), ([(8, 238), (2, 252), (-2, 258)], 3.0)):
        fat.line(P(pts), w)
    o.L("groove").line(P([(10, 203), (14, 224), (18, 244), (21, 262)]), 1.5)
    o.L("groove").line(P([(5, 201), (6, 216), (4, 232), (-2, 244)]), 1.5)
    n_fat = o.noise(5, 2, 7)
    fatm = np.clip(o.m("fat", 0.6) * (1.25 + 0.5 * n_fat), 0, 1)
    base, lv, ra = hex2rgb("#bd2c35"), hex2rgb("#971c2a"), hex2rgb("#cf5662")
    alb = mixa(base, lv, np.clip(o.m("lv", 1.6) * 1.1, 0, 1))
    alb = mixa(alb, ra, np.clip(o.m("ra", 1.6), 0, 1) * 0.85)
    alb = mixa(alb, hex2rgb("#d4606a"), np.clip(o.m("aur", 0.8), 0, 1) * 0.9)
    fib = o.noise(3.2, 3, 4, stretch=(0.35, 1.7))
    big = o.noise(15, 3, 5)
    alb = alb * (1 + 0.07 * fib + 0.05 * big)[..., None]
    fcol = hex2rgb("#eccc82") * (1 + 0.08 * o.noise(2.5, 2, 9))[..., None]
    alb = alb * (1 - 0.85 * fatm[..., None]) + fcol * (0.85 * fatm[..., None])
    grv = o.m("groove", 0.6)
    alb = alb * (1 - 0.3 * grv[..., None])
    bump = 0.28 * fib + 0.7 * fatm * (0.5 + 0.5 * n_fat) - 1.2 * grv
    rgba = shade(o, alb, bump, mask, spec=0.5, shin=20, amp=(5.5, 8.5), ambient=0.46)

    # сосуды сердца. Дуга аорты и полые вены - отдельные органы (aorta, vena_cava) под сердцем:
    # правая лёгочная артерия проходит за восходящей аортой и верхней полой веной - там её не рисуем
    pa_r = o.ink("pa_r")
    pa_r.tube(P([(20, 190), (6, 184), (-10, 186), (-22, 192)]), [7.5, 7, 6.5, 5.5])
    for lay in (pa_r.cov, pa_r.hgt):
        lay.tube(P(aorta.ASCENDING), aorta.ASCENDING_W, v=0)
        lay.tube(P(vena_cava.SVC), vena_cava.SVC_W, v=0)
    rgba = pa_r.over(rgba, "#6c7fc2", 0.97, amp=3.2, spec=0.35, edge_dark=0.4)
    pt = o.ink("pt")
    pt.tube(P([(18, 207), (19, 195), (22, 186)]), [12, 11.5, 11])
    pt.tube(P([(22, 187), (33, 182), (44, 187)]), [8, 7.2, 6.4])
    rgba = pt.over(rgba, "#7a86cf", 0.98, amp=3.6, spec=0.4, edge_dark=0.4)
    # коронарные артерии
    cor = o.ink("cor")
    cor.tube(P([(9, 205), (13, 222), (17, 242), (20, 260)]), [2.4, 2.3, 2.0, 1.4])
    cor.tube(P([(13, 214), (24, 219), (34, 230)]), [1.9, 1.7, 1.2])
    cor.tube(P([(16, 232), (28, 238), (34, 246)]), [1.7, 1.5, 1.1])
    cor.tube(P([(2, 207), (-8, 211), (-11, 224), (-8, 238), (-1, 248)]), [2.4, 2.2, 2.0, 1.8, 1.3])
    cor.tube(P([(-11, 222), (-4, 226), (3, 230)]), [1.6, 1.4, 1.0])
    cor.tube(P([(10, 204), (22, 202), (34, 209)]), [2.2, 2.0, 1.4])
    rgba = cor.over(rgba, "#ff5a4c", 0.95, amp=2.0, spec=0.4, gain=1.1)
    allv = np.clip(gblur(pa_r.cov.get() + pt.cov.get(), 0.5 * Z), 0, 1)
    return finish(o, rgba, np.maximum(rgba[..., 3], allv))


# --------------------------------------------------------------- 3D: модель (данные в models/heart.json)

def parts():
    """3D-модель: примитивы из models/heart.json"""
    return load_parts("heart")
