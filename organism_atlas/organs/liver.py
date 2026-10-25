"""Печень: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#8a3a2c"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("digestive",)               # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

LIVER = [(-58, 256), (-46, 246), (-28, 240), (-8, 243), (12, 252), (28, 260), (38, 268), (32, 276), (14, 284),
         (-4, 292), (-26, 298), (-46, 295), (-58, 284), (-64, 270)]


def paint(Z, ss, seed=7):
    o = Org((CX - 76, 228, CX + 52, 330), Z, ss, seed)
    o.L("liver").poly(P(LIVER))
    m = o.L("mask")
    m.poly(P(LIVER))
    mask = o.m("mask")
    o.L("lig").line(P([(5, 244), (2, 264), (-2, 291)]), 2.2)
    o.L("lig2").line(P([(-44, 250), (-38, 268), (-29, 288)]), 1.4)
    lig = o.m("lig", 0.8) + 0.5 * o.m("lig2", 0.7)
    alb = np.broadcast_to(hex2rgb("#97402f"), o.shape + (3,)).copy()
    n1, n2 = o.noise(22, 3, 1), o.noise(2.4, 2, 2)
    # лёгкий градиент: ярче правая доля, темнее к низу
    yy = np.mgrid[0:o.shape[0], 0:o.shape[1]][0] / Z / (330 - 228)
    alb = alb * (1.12 - 0.35 * yy)[..., None] * (1 + 0.05 * n1 + 0.025 * n2)[..., None]
    alb = alb * (1 - 0.35 * np.clip(lig, 0, 1)[..., None])
    bump = 0.10 * n1 + 0.04 * n2 - 1.8 * np.clip(lig, 0, 1)
    rgba = shade(o, alb, bump, mask, spec=0.6, shin=11, amp=(5.0, 9.0), ambient=0.45)
    # проток жёлчного пузыря (сам пузырь - отдельный орган, organs/gallbladder.py)
    duct = o.ink("duct")
    duct.tube(P([(-22, 296), (-14, 290), (-8, 288)]), [2.4, 2.4, 2.2])
    rgba = duct.over(rgba, "#7bc050", 0.9, amp=1.5)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/liver.json)

def parts():
    """3D-модель: примитивы из models/liver.json"""
    return load_parts("liver")
