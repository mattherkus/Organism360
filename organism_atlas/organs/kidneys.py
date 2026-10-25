"""Почки: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import math

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.noise import gblur
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#a2384a"                      # цвет органа на схеме и полоски в карточке


# --------------------------------------------------------------- 2D: рисунок на схеме тела

def bean(cx, cy, w, h, tilt_deg, mirror=False, dent=9.0, n=48):
    th = math.radians(tilt_deg)
    out = []
    for i in range(n):
        t = 2 * math.pi * i / n
        u, v = w / 2 * math.cos(t), h / 2 * math.sin(t)
        if u > 0:
            u -= dent * math.exp(-(v / (0.26 * h)) ** 2) * (u / (w / 2))
        x, y = u * math.cos(th) - v * math.sin(th), u * math.sin(th) + v * math.cos(th)
        out.append((cx + (-x if mirror else x), cy + y))
    return out


def paint(Z, ss, seed=17):
    o = Org((CX - 64, 284, CX + 64, 386), Z, ss, seed)
    kr = bean(CX - 31, 328, 27, 50, 12)
    kl = bean(CX + 32, 322, 27, 50, 12, mirror=True)
    m = o.L("mask")
    m.poly(kr)
    m.poly(kl)
    # жировая ткань в воротах почки
    o.L("hil").ellipse(CX - 22, 328, 5.5, 9.5)
    o.L("hil").ellipse(CX + 23, 322, 5.5, 9.5)
    mask = o.m("mask")
    hil = np.clip(o.m("hil", 1.2) * 1.2, 0, 1)
    alb = np.broadcast_to(hex2rgb("#ad3b4d"), o.shape + (3,)).copy()
    lob = o.noise(6.5, 2, 1)
    fine = o.noise(2.2, 2, 2)
    big = o.noise(20, 2, 3)
    alb = alb * (1 + 0.06 * lob + 0.03 * fine + 0.05 * big)[..., None]
    alb = alb * (1 - 0.55 * hil[..., None]) + (hex2rgb("#e2c783") * (1 + 0.05 * fine)[..., None]) * (0.55 * hil[..., None])
    bump = 0.10 * lob + 0.03 * fine
    rgba = shade(o, alb, bump, mask, spec=0.55, shin=14, amp=(5.0, 7.0), ambient=0.46)
    # мочеточники (уходят под мочевой пузырь)
    ur = o.ink("ur")
    ur.tube(P([(-23, 336), (-21, 354), (-17, 368), (-12, 378)]), [2.6, 2.4, 2.2, 2.0])
    ur.tube(P([(24, 330), (22, 352), (17, 368), (12, 378)]), [2.6, 2.4, 2.2, 2.0])
    rgba = ur.over(rgba, "#efdca2", 0.97, amp=1.8, spec=0.3, edge_dark=0.3)
    # почечные сосуды
    rv = o.ink("rv")
    rv.tube(P([(-21, 332), (-14, 332), (-7, 330)]), [4.4, 4.2, 3.8])
    rv.tube(P([(22, 326), (15, 326), (8, 324)]), [4.4, 4.2, 3.8])
    rgba = rv.over(rgba, "#4a7bc6", 0.97, amp=2.2, spec=0.35, edge_dark=0.35)
    ra = o.ink("ra")
    ra.tube(P([(-21, 324), (-14, 323), (-6, 322)]), [3.2, 3.0, 2.8])
    ra.tube(P([(22, 318), (15, 317), (7, 316)]), [3.2, 3.0, 2.8])
    rgba = ra.over(rgba, "#d1404a", 0.97, amp=2.2, spec=0.4, edge_dark=0.35)
    hitv = np.clip(gblur(ur.cov.get() + rv.cov.get() + ra.cov.get(), 0.5 * Z), 0, 1)
    return finish(o, rgba, np.maximum(rgba[..., 3], hitv))


# --------------------------------------------------------------- 3D: модель (данные в models/kidneys.json)

def parts():
    """3D-модель: примитивы из models/kidneys.json"""
    return load_parts("kidneys")
