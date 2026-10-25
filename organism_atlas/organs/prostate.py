"""Предстательная железа: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра.
Есть только на мужской схеме (SEX); охватывает начало мочеиспускательного канала под мочевым пузырём."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, sym
from ..models import load_parts
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#b77568"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("reproductive",)            # системы органов (первая - главная): тема и вопросы викторины
SEX = "male"                           # орган есть только у одного пола (настройка «Схема тела»)


# --------------------------------------------------------------- 2D: рисунок на схеме тела

HALF = [(0, 396.5), (5.5, 397), (9.5, 400), (10, 405), (7.5, 410), (3.5, 413), (0, 413.5)]


def paint(Z, ss, seed=71):
    o = Org((CX - 16, 390, CX + 16, 420), Z, ss, seed)
    o.L("mask").poly(sym(HALF))
    o.L("groove").line([(CX, 399), (CX, 412)], 1.4)               # срединная борозда между долями
    mask = o.m("mask")
    grv = o.m("groove", 0.8)
    edge, dome = o.cells(2.6, 1, border=0.22)
    fine = o.noise(1.8, 2, 2)
    alb = np.broadcast_to(hex2rgb("#bb796b"), o.shape + (3,)).copy()
    alb = alb * (1 + 0.04 * fine + 0.05 * o.noise(8, 2, 3))[..., None]
    alb = alb * (1 - 0.08 * edge[..., None]) * (1 - 0.25 * grv[..., None])
    bump = 0.07 * dome - 0.1 * edge + 0.03 * fine - 0.8 * grv
    rgba = shade(o, alb, bump, mask, soft=(2.5, 4.5), spec=0.45, shin=16, amp=(2.6, 3.2), ambient=0.48)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/prostate.json)

def parts():
    """3D-модель: примитивы из models/prostate.json"""
    return load_parts("prostate")
