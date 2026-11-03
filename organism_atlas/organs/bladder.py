"""Мочевой пузырь: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""


from ..geometry import CX, P, sym
from ..render2d.organ import Org, finish, shade


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#d9ae6c"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("urinary",)                 # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

BLADDER_HALF = [(0, 363.5), (9, 364.5), (16, 369.5), (19, 378.5), (17.5, 388.5), (11.5, 395.5), (4.5, 399),
                (0, 399.5)]


def paint(Z, ss, seed=37):
    o = Org((CX - 24, 356, CX + 24, 410), Z, ss, seed)
    m = o.L("mask")
    m.poly(sym(BLADDER_HALF))
    m.tube([(CX, 396), (CX, 402), (CX, 407)], [5, 4.2, 3.8])            # мочеиспускательный канал
    mask = o.m("mask")
    fib = o.noise(2.6, 3, 1, stretch=(0.45, 1.8))
    big = o.noise(12, 2, 2)
    alb = o.fill("#dcae72")
    alb = alb * (1 + 0.035 * fib + 0.05 * big)[..., None]
    bump = 0.1 * fib + 0.08 * big
    rgba = shade(o, alb, bump, mask, spec=0.5, shin=16, amp=(4.5, 6.0), ambient=0.48)
    # сосуды на стенке пузыря
    a = o.ink("art")
    for s in (False, True):
        a.tube(P([(17, 384), (11, 380), (7, 373), (5, 367)], s), [1.4, 1.2, 1.0, 0.8])
        a.tube(P([(11, 380), (6, 386), (3, 392)], s), [1.0, 0.9, 0.7])
    rgba = a.over(rgba, "#c9575a", 0.45, amp=1.0, spec=0.2)
    return finish(o, rgba)
