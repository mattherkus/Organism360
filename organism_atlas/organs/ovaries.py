"""Яичники: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра.
Есть только на женской схеме (SEX)."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#ecc0b2"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("reproductive", "endocrine") # системы органов (первая - главная): тема и вопросы викторины
SEX = "female"                         # орган есть только у одного пола (настройка «Схема тела»)


# --------------------------------------------------------------- 2D: рисунок на схеме тела

OVARY = [(23, 351), (27, 348.5), (32, 349.5), (35, 353.5), (34, 358), (29.5, 360), (24.5, 358.5), (22, 355)]


def paint(Z, ss, seed=67):
    o = Org((CX - 40, 342, CX + 40, 366), Z, ss, seed)
    m = o.L("mask")
    for s in (False, True):
        m.poly(P(OVARY, s))
    lig = o.ink("lig")                                            # собственная связка яичника - к матке
    for s in (False, True):
        lig.tube(P([(14, 352), (18.5, 354), (23, 355)], s), [1.8, 1.7, 1.6])
    mask = o.m("mask")
    edge, dome = o.cells(2.0, 1, border=0.3)                      # фолликулы под оболочкой
    fine = o.noise(1.6, 2, 2)
    alb = np.broadcast_to(hex2rgb("#ebbcae"), o.shape + (3,)).copy()
    alb = alb * (1 + 0.04 * fine + 0.04 * dome)[..., None]
    alb = alb * (1 - 0.06 * edge[..., None])
    bump = 0.12 * dome - 0.06 * edge + 0.03 * fine
    rgba = shade(o, alb, bump, mask, soft=(2.0, 3.5), spec=0.45, shin=16, amp=(2.0, 2.4), ambient=0.5)
    rgba = lig.over(rgba, "#e6b3a4", 0.9, amp=1.0, spec=0.3, edge_dark=0.3)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/ovaries.json)

def parts():
    """3D-модель: примитивы из models/ovaries.json"""
    return load_parts("ovaries")
