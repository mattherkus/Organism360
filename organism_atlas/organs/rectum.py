"""Прямая кишка: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра.

Продолжает сигмовидную кишку (organs/intestines.py); спереди её закрывает мочевой пузырь."""


from ..geometry import CX, P
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#c97462"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("digestive",)               # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

PATH = [(2, 384), (1, 395), (0, 405), (0, 414), (0, 422), (0, 429)]
WIDTHS = [11, 13, 17, 18, 13, 7]       # расширение внизу - ампула, ниже - анальный канал


def paint(Z, ss, seed=59):
    o = Org((CX - 14, 376, CX + 14, 436), Z, ss, seed)
    o.L("mask").tube(P(PATH), WIDTHS)
    f = o.L("fold")                                               # поперечные складки
    for y, w in ((402, 6.5), (411, 8.0), (419, 7.0)):
        f.line([(CX - w, y + 1.5), (CX, y), (CX + w, y + 1.5)], 1.6)
    mask = o.m("mask")
    fold = o.m("fold", 0.8)
    fib = o.noise(2.6, 3, 1, stretch=(0.5, 1.8))
    big = o.noise(9, 2, 2)
    alb = o.fill("#cf7a66")
    alb = alb * (1 + 0.04 * fib + 0.05 * big)[..., None]
    alb = alb * (1 - 0.3 * fold[..., None])
    bump = 0.06 * fib + 0.06 * big - 1.2 * fold
    rgba = shade(o, alb, bump, mask, soft=(2.5, 5.0), spec=0.4, shin=14, amp=(3.0, 4.0), ambient=0.48)
    return finish(o, rgba)
