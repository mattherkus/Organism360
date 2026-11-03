"""Щитовидная железа: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""


from ..geometry import CX, P
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#c2564e"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("endocrine",)               # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

LOBE = [(5.5, 114), (8.5, 110), (11.5, 113.5), (14, 121), (14.5, 129), (12.5, 135), (8.5, 137.5), (5.5, 135.5),
        (4, 127.5), (4.5, 119.5)]                                   # правая половина; левая зеркальная


def paint(Z, ss, seed=23):
    o = Org((CX - 22, 104, CX + 22, 142), Z, ss, seed)
    m = o.L("mask")
    for s in (False, True):
        m.poly(P(LOBE, s))
    m.tube(P([(-6.5, 130.5), (0, 132), (6.5, 130.5)]), [5.5, 5, 5.5])    # перешеек
    o.L("isth").tube(P([(-5, 131), (0, 132.5), (5, 131)]), [3, 2.8, 3])
    mask = o.m("mask")
    isth = o.m("isth", 1.2)
    edge, dome = o.cells(3.0, 1, border=0.18)
    fine = o.noise(1.8, 2, 2)
    alb = o.fill("#bd4d48")
    alb = alb * (1 + 0.04 * fine + 0.06 * o.noise(9, 2, 3))[..., None]
    alb = alb * (1 - 0.08 * edge[..., None])
    alb = alb * (1 - 0.12 * isth[..., None])                       # перешеек тоньше и темнее
    bump = 0.08 * dome - 0.15 * edge + 0.03 * fine - 0.6 * isth
    rgba = shade(o, alb, bump, mask, spec=0.5, shin=16, amp=(2.6, 3.4), ambient=0.48)
    # верхние щитовидные артерии и вены
    a = o.ink("art")
    v = o.ink("vein")
    for s in (False, True):
        a.tube(P([(13, 105), (12, 110), (10.5, 114)], s), [1.8, 1.6, 1.3])
        v.tube(P([(13.5, 135), (16, 139), (17, 142)], s), [2.0, 2.0, 2.0])
    rgba = v.over(rgba, "#4a7bc6", 0.95, amp=1.6, spec=0.3)
    rgba = a.over(rgba, "#d1404a", 0.95, amp=1.6, spec=0.35)
    return finish(o, rgba)
