"""Тимус (вилочковая железа): цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#d79a9c"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("immune", "endocrine")      # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

# две доли за грудиной, перед крупными сосудами и верхом сердца; у взрослого тимус небольшой
RLOBE = [(-2, 147), (-6, 149), (-9, 156), (-10, 166), (-9, 176), (-6, 185), (-2, 188), (0, 182), (0, 160)]
LLOBE = [(1, 151), (5, 149), (9, 154), (12, 164), (13, 175), (11, 186), (6, 191), (2, 188), (0.5, 176),
         (0.5, 160)]


def paint(Z, ss, seed=47):
    o = Org((CX - 16, 140, CX + 18, 198), Z, ss, seed)
    m = o.L("mask")
    m.poly(P(RLOBE))
    m.poly(P(LLOBE))
    o.L("split").line(P([(0.3, 150), (0.3, 168), (0.6, 186)]), 0.9)   # щель между долями
    mask = o.m("mask")
    split = o.m("split", 0.5)
    edge, dome = o.cells(2.6, 3, border=0.22)                         # дольки
    fine = o.noise(1.6, 2, 1)
    fat = np.clip(o.noise(6, 2, 2) * 0.9 + 0.1, 0, 1)                 # у взрослого - прослойки жира
    alb = o.fill("#d49a98")
    alb = alb * (1 - 0.35 * fat[..., None]) + hex2rgb("#ecd7a4") * (0.35 * fat[..., None])
    alb = alb * (1 + 0.04 * fine)[..., None] * (1 - 0.12 * edge[..., None])
    alb = alb * (1 - 0.35 * split[..., None])
    bump = 0.1 * dome - 0.18 * edge + 0.03 * fine - 0.8 * split
    rgba = shade(o, alb, bump, mask, spec=0.4, shin=14, amp=(2.4, 3.2), ambient=0.5)
    return finish(o, rgba)
