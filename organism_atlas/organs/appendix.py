"""Аппендикс (червеобразный отросток): цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#d98a5f"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("digestive", "immune")      # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

# отходит от купола слепой кишки (начало толстой кишки в organs/intestines.py) и свисает в малый таз
PATH = [(-39, 388), (-36, 396), (-31.5, 402.5), (-27, 407), (-24, 413)]
WIDTHS = [6.0, 5.4, 5.0, 4.8, 4.6]


def paint(Z, ss, seed=53):
    o = Org((CX - 46, 380, CX - 16, 420), Z, ss, seed)
    o.L("mask").tube(P(PATH), WIDTHS)
    mask = o.m("mask")
    n1, n2 = o.noise(6, 2, 1), o.noise(1.8, 2, 2)
    alb = np.broadcast_to(hex2rgb("#dd9269"), o.shape + (3,)).copy()
    alb = alb * (1 + 0.05 * n1 + 0.03 * n2)[..., None]
    bump = 0.08 * n1 + 0.03 * n2
    rgba = shade(o, alb, bump, mask, soft=(1.5, 3.0), spec=0.5, shin=16, amp=(1.8, 2.2), ambient=0.5)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/appendix.json)

def parts():
    """3D-модель: примитивы из models/appendix.json"""
    return load_parts("appendix")
