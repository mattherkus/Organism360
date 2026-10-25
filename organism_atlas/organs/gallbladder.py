"""Жёлчный пузырь: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра.

Раньше был нарисован внутри печени (organs/liver.py); проток пузыря по-прежнему рисуется с печенью."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..models import load_parts
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#5fa13f"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("digestive",)               # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

GALL = [(-22, 292), (-28, 299), (-30, 309), (-26, 317), (-20, 314), (-17, 304)]


def paint(Z, ss, seed=41):
    o = Org((CX - 38, 284, CX - 9, 324), Z, ss, seed)
    o.L("mask").poly(P(GALL))
    mask = o.m("mask")
    n1, n2 = o.noise(22, 3, 1), o.noise(2.4, 2, 2)
    # темнее цвета карточки: внутри печени пузырь был темнее за счёт её объёмного освещения
    alb = hex2rgb("#3d7024")[None, None, :] * (1 + 0.06 * n1)[..., None]
    bump = 0.10 * n1 + 0.04 * n2
    rgba = shade(o, alb, bump, mask, spec=0.6, shin=11, amp=(3.0, 4.0), ambient=0.45)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/gallbladder.json)

def parts():
    """3D-модель: анатомическая сетка models/mesh/gallbladder.*, иначе примитивы models/gallbladder.json"""
    return load_parts("gallbladder")
