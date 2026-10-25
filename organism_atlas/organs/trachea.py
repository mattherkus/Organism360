"""Трахея: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра.

Раньше была нарисована вместе с лёгкими (organs/lungs.py); бронхи по-прежнему рисуются с лёгкими."""

import numpy as np

from ..geometry import CX
from ..models import load_parts
from ..render2d.layers import over_rgba
from ..render2d.organ import Org, finish


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#cfdbe2"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("respiratory",)             # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

TOP, CARINA = 102, 172                 # от гортани до разделения на главные бронхи


def paint(Z, ss, seed=3):
    o = Org((CX - 10, TOP - 6, CX + 10, CARINA + 6), Z, ss, seed)
    tr = o.ink("trachea")
    tr.tube([(CX, TOP), (CX, 140), (CX, CARINA)], [12, 12, 12])
    rings = o.L("rings")                                          # хрящевые полукольца
    for y in np.arange(TOP + 2, CARINA, 3.4):
        rings.line([(CX - 5.2, y), (CX + 5.2, y)], 1.15, smooth=False)
    rg = o.m("rings", 0.45)
    cov, col = tr.shaded("#dfe8ee", amp=4.5, spec=0.4, edge_dark=0.45)
    col = col * (1 - 0.34 * rg[..., None])
    rgba = over_rgba(np.zeros(o.shape + (4,), np.float32), col, cov * 0.97)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/trachea.json)

def parts():
    """3D-модель: примитивы из models/trachea.json"""
    return load_parts("trachea")
