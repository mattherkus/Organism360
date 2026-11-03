"""Гипофиз: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX
from ..render2d.noise import gblur
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#e0905a"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("endocrine",)               # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

# горошина под основанием мозга (в турецком седле), на ножке-воронке от гипоталамуса
CENTER = (CX, 66.5)
HIT_PAD = 1.6                          # запас вокруг для попадания мышью: орган очень маленький


def paint(Z, ss, seed=53):
    o = Org((CX - 10, 54, CX + 10, 76), Z, ss, seed)
    cx, cy = CENTER
    m = o.L("mask")
    m.ellipse(cx, cy, 4.6, 3.6)                                       # передняя и задняя доли
    m.tube([(cx, cy - 2), (cx, cy - 6.5), (cx, cy - 9)], [2.2, 1.8, 2.4])      # воронка
    o.L("post").ellipse(cx + 1.6, cy + 0.2, 2.2, 2.6)                 # задняя доля - светлее
    mask = o.m("mask")
    post = o.m("post", 0.5)
    fine = o.noise(1.2, 2, 1)
    alb = o.fill("#df8d5c")
    alb = alb * (1 - 0.5 * post[..., None]) + hex2rgb("#f0c9a0") * (0.5 * post[..., None])
    alb = alb * (1 + 0.05 * fine)[..., None]
    rgba = shade(o, alb, 0.04 * fine, mask, soft=(1.6, 3.2), amp=(2.2, 2.4), spec=0.55, shin=18, ambient=0.5,
                 edge_dark=0.35)
    hit = np.clip(gblur(mask, HIT_PAD * Z) * 3.0, 0, 1)
    return finish(o, rgba, np.maximum(rgba[..., 3], hit))
