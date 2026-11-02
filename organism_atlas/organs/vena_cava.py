"""Полые вены: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра.

Верхняя полая вена (с впадающими в неё плечеголовными венами) приносит кровь в правое предсердие сверху,
нижняя - снизу, от ног и органов живота. Лежат под сердцем, но над лёгкими; нижняя полая вена проходит
за печенью и другими органами живота (BEHIND).
"""

import numpy as np

from ..geometry import CX, P
from ..models import load_parts
from ..render2d.organ import Org, finish


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#4d7fcb"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("circulatory",)             # системы органов (первая - главная): тема и вопросы викторины
# органы перед полыми венами, хотя они ниже в стопке слоёв (organs.BEHIND)
BEHIND = ("diaphragm", "liver", "gallbladder", "stomach", "pancreas", "spleen", "intestines",
          "appendix", "rectum", "kidneys", "adrenals", "bladder", "uterus", "ovaries", "prostate")


# --------------------------------------------------------------- 2D: рисунок на схеме тела

SVC = [(-8, 210), (-9, 188), (-10, 162), (-10, 148)]                  # верхняя полая вена
SVC_W = [10, 9.5, 9, 8]
BRACHIOCEPHALIC = (([(-10, 154), (-22, 149), (-34, 150)], [6.5, 6, 5.4]),               # правая плечеголовная
                   ([(-10, 156), (8, 152), (22, 149), (34, 150)], [6, 5.6, 5.2, 4.8]))   # левая - через грудь
# нижняя полая вена: от слияния общих подвздошных вен (чуть ниже и правее деления аорты) вверх, за печенью,
# в правое предсердие
CONFLUENCE = (-4, 332)
IVC = [CONFLUENCE, (-6, 312), (-6, 296), (-6.5, 275), (-7, 262), (-6, 246)]
IVC_W = [9, 9.5, 10, 10.5, 10.5, 11]
HEPATIC = (([(-7, 258), (-18, 254), (-28, 252)], [4.2, 3.6, 3.0]),      # печёночные вены
           ([(-7, 256), (2, 252), (10, 252)], [3.8, 3.2, 2.6]))


def paint(Z, ss, seed=43):
    o = Org((CX - 42, 140, CX + 42, 380), Z, ss, seed)
    v = o.ink("veins")
    v.tube(P(IVC), IVC_W)
    for path, widths in HEPATIC:
        v.tube(P(path), widths)
    for path, widths in BRACHIOCEPHALIC:
        v.tube(P(path), widths)
    v.tube(P(SVC), SVC_W)
    o.L("mask")                                                    # рамка органа (origin) - по маске
    rgba = v.over(np.zeros(o.shape + (4,), np.float32), "#4d7fcb", 0.97, amp=3.4, spec=0.35, edge_dark=0.4)
    return finish(o, rgba)


# --------------------------------------------------------------- 3D: модель (данные в models/vena_cava.json)

def parts():
    """3D-модель: примитивы из models/vena_cava.json"""
    return load_parts("vena_cava")
