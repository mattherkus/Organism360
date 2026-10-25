"""Кишечник: цвет, рисунок на схеме тела (2D) и модель для 3D-просмотра."""

import math

import numpy as np

from ..colors import hex2rgb
from ..geometry import CX, P, cr_spline, smooth_scalar
from ..models import load_parts
from ..render2d.layers import Layer, over_rgba
from ..render2d.noise import gblur
from ..render2d.organ import Org, finish


# --------------------------------------------------------------- цвет (тексты карточки: lang/*.json)
COLOR = "#e8a77f"                      # цвет органа на схеме и полоски в карточке
SYSTEMS = ("digestive",)               # системы органов (первая - главная): тема и вопросы викторины


# --------------------------------------------------------------- 2D: рисунок на схеме тела

def colon_path():
    # поперечная ободочная кишка опущена, чтобы над ней была видна поджелудочная железа
    pts = [(-44, 380), (-47, 356), (-49, 332), (-46, 314), (-38, 305), (-24, 311), (-8, 319), (10, 321),
           (28, 317), (44, 308), (52, 312), (53, 330), (51, 350), (47, 366), (38, 377), (26, 382), (15, 376),
           (7, 383), (2, 392)]
    widths = [24, 22, 21, 20, 18, 17, 17, 17, 17, 17, 16, 15, 15, 14, 13, 12.5, 12, 11.5, 11]
    return pts, widths


def small_bowel_path(rng):
    pts = [(-16, 333)]
    rows = 8
    for r in range(rows):
        y = 329 + r * 8.3 + rng.uniform(-1.2, 1.2)
        x0, x1 = -31 + rng.uniform(-4, 2), 33 + rng.uniform(-4, 3)
        xs = np.linspace(x0, x1, 7)
        if r % 2:
            xs = xs[::-1]
        ph = rng.uniform(0, 6.28)
        for i, x in enumerate(xs):
            pts.append((x + rng.normal(0, 2.0), y + 4.2 * math.sin(i * 1.05 + ph) + rng.normal(0, 1.4)))
        if r < rows - 1:
            ex = xs[-1] + (5.5 if xs[-1] > 0 else -5.5)
            pts.append((ex, y + 4.15))
    out = []
    for x, y in pts:                        # плавное смещение всей петли
        out.append((x + 4.4 * math.sin(0.11 * y + 1.3) + 2.4 * math.sin(0.17 * x + 0.4 * y),
                    y + 3.4 * math.sin(0.09 * x + 2.1) + 2.0 * math.sin(0.15 * y + 0.2 * x)))
    return out


def paint(Z, ss, seed=13):
    o = Org((CX - 72, 280, CX + 72, 408), Z, ss, seed)
    rng = np.random.default_rng(seed)
    cp, cw = colon_path()
    cp = P(cp)
    # тонкая кишка
    si = o.ink("si")
    sp_ = P(small_bowel_path(rng))
    si.tube(sp_, [8.8 + 0.7 * math.sin(i * 0.9) for i in range(len(sp_))])
    duo = P([(-15, 287), (-24, 298), (-31, 313), (-27, 328), (-14, 333)])
    si.tube(duo, [8, 8, 8, 8, 8])
    # заполнение брыжейки между петлями
    cavity = np.clip((gblur(si.cov.get(), 3.4 * Z) - 0.28) * 4.5, 0, 1)
    cavity = gblur(cavity, 0.8 * Z)
    # толстая кишка с гаустрами
    dense = cr_spline(cp, n=8)
    wd = smooth_scalar(cw, n=8)
    col = o.ink("colon")
    seg = []
    arc = 0.0
    wl = []
    for i, (x, y) in enumerate(dense):
        if i:
            arc += math.hypot(x - dense[i - 1][0], y - dense[i - 1][1])
        wl.append(wd[i] * (1 + 0.075 * math.sin(arc * 2 * math.pi / 14.0)))
    col.tube(dense, wl, n=1)
    # складки гаустр поперёк
    fl = o.L("folds")
    arc = 0.0
    nextf = 7.0
    for i in range(1, len(dense) - 1):
        arc += math.hypot(dense[i][0] - dense[i - 1][0], dense[i][1] - dense[i - 1][1])
        if arc >= nextf:
            nextf += 14.0
            x0, y0 = dense[i - 1]
            x1, y1 = dense[i + 1]
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy) or 1
            nx, ny = -dy / ln, dx / ln
            h = wd[i] * 0.46
            fl.line([(dense[i][0] - nx * h, dense[i][1] - ny * h), (dense[i][0] + nx * h, dense[i][1] + ny * h)],
                    1.4, smooth=False)
    fold = o.m("folds", 0.6)

    o.layers["mask"] = Layer(o.box, Z, ss)           # только для origin / формы
    rgba = np.zeros(o.shape + (4,), np.float32)
    # фон-брыжейка
    cav_rgb = np.broadcast_to(hex2rgb("#74363c"), o.shape + (3,)).copy()
    cav_rgb *= (1 + 0.06 * o.noise(7, 2, 1))[..., None]
    rgba = over_rgba(rgba, cav_rgb, cavity * 0.96)
    # тонкая кишка
    rgba = si.over(rgba, "#f4a8a0", 1.0, amp=4.2, spec=0.5, ambient=0.5, edge_dark=0.55, shin=16, gain=1.2)
    # шум на тонкой кишке не нужен, добавим «влажный» вид через спек
    cov, ccol = col.shaded("#d27a50", amp=5.2, spec=0.42, ambient=0.5, edge_dark=0.6, shin=15, gain=1.2)
    ccol = ccol * (1 - 0.55 * fold[..., None])
    ccol = ccol * (1 + 0.05 * o.noise(5, 2, 3))[..., None]
    rgba = over_rgba(rgba, np.clip(ccol, 0, 1), cov)
    hit = np.maximum(rgba[..., 3], cavity)
    return finish(o, rgba, hit)


# --------------------------------------------------------------- 3D: модель (данные в models/intestines.json)

def parts():
    """3D-модель: примитивы из models/intestines.json"""
    return load_parts("intestines")
