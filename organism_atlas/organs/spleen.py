"""Селезёнка: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#7b2f55"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("immune",)                  # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

# лежит слева за желудком, под нижними рёбрами; вогнутой стороной к желудку
SPLEEN = [(50, 243), (57, 244.5), (62.5, 251), (65.5, 261), (65.5, 273), (63, 284), (58, 291.5), (52, 293),
          (48.5, 288), (48.5, 280), (47.5, 270), (46, 259), (46.5, 249)]


def paint(Z, ss, seed=29):
    o = Org((CX + 38, 234, CX + 74, 302), Z, ss, seed)
    o.L("mask").poly(P(SPLEEN))
    o.L("notch").line(P([(62.5, 251), (59.5, 254)]), 1.3)              # вырезки на верхнем крае
    o.L("notch").line(P([(65.5, 263), (62, 265)]), 1.1)
    mask = o.m("mask")
    notch = o.m("notch", 0.6)
    fine = o.noise(2.0, 2, 1)
    big = o.noise(12, 2, 2)
    alb = np.broadcast_to(hex2rgb("#7e3253"), o.shape + (3,)).copy()
    alb = alb * (1 + 0.035 * fine + 0.07 * big)[..., None]
    alb = alb * (1 - 0.4 * notch[..., None])
    bump = 0.05 * fine + 0.12 * big - 1.4 * notch
    rgba = shade(o, alb, bump, mask, spec=0.55, shin=14, amp=(4.0, 6.5), ambient=0.46)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/spleen.json)

def parts():
    """3D-модель: примитивы из models/spleen.json"""
    return load_parts("spleen")
