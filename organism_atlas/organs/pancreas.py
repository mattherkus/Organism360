"""Поджелудочная железа: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.noise import gblur
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#e8b07c"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("digestive", "endocrine")   # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

# головка лежит в изгибе двенадцатиперстной кишки, хвост доходит до селезёнки
HEAD = [(-10, 306), (-17, 303.5), (-23, 308), (-25, 318), (-22, 328), (-15, 331), (-8, 327), (-6, 318)]
BODY = [(-10, 318), (0, 316), (14, 315), (28, 312), (42, 305), (53, 297), (58, 292)]
BODY_W = [13, 12, 11, 10, 9, 7.5, 6]


def paint(Z, ss, seed=31):
    o = Org((CX - 30, 286, CX + 66, 336), Z, ss, seed)
    m = o.L("mask")
    m.poly(P(HEAD))
    m.tube(P(BODY), BODY_W)
    o.L("duct").line(P([(-17, 324), (-12, 319)] + BODY[1:-1]), 1.3)
    mask = o.m("mask")
    duct = o.m("duct", 1.0) * gblur(mask, 2.0 * Z)
    edge, dome = o.cells(3.0, 1, border=0.18)
    fine = o.noise(1.6, 2, 2)
    alb = np.broadcast_to(hex2rgb("#ecb688"), o.shape + (3,)).copy()
    alb = alb * (1 + 0.04 * fine + 0.05 * o.noise(10, 2, 3))[..., None]
    alb = alb * (1 - 0.1 * edge[..., None]) * (1 - 0.15 * duct[..., None])
    bump = 0.1 * dome - 0.2 * edge + 0.04 * fine - 0.5 * duct
    rgba = shade(o, alb, bump, mask, spec=0.4, shin=14, amp=(3.2, 4.5), ambient=0.48)
    # селезёночные артерия и вена вдоль верхнего края
    v = o.ink("vein")
    v.tube(P([(-4, 311), (14, 309.5), (30, 306), (43, 299), (55, 290)]), [3.2, 3.0, 2.8, 2.6, 2.4])
    a = o.ink("art")
    a.tube(P([(-2, 308), (8, 306.5), (16, 309), (25, 305), (34, 304), (42, 297), (51, 292), (57, 287)]),
           [2.2, 2.1, 2.0, 2.0, 1.9, 1.8, 1.7, 1.6])
    rgba = v.over(rgba, "#4a7bc6", 0.95, amp=1.8, spec=0.3, edge_dark=0.3)
    rgba = a.over(rgba, "#d1404a", 0.95, amp=1.8, spec=0.35, edge_dark=0.3)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/pancreas.json)

def parts():
    """3D-модель: примитивы из models/pancreas.json"""
    return load_parts("pancreas")
