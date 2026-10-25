"""Проектные координаты тела (W, H, CX) и геометрические примитивы: сплайны, трубки, полигоны."""

import math

import numpy as np


W, H, CX = 380, 500, 190          # размер схемы в «проектных» единицах и ось тела
                                  # (обрезана на середине бёдер: ниже органов нет, зато торс крупнее)


def P(pts, flip=False):
    """список (dx, y) -> абсолютные точки; flip зеркалит относительно оси"""
    s = -1 if flip else 1
    return [(CX + s * dx, y) for dx, y in pts]


def cr_spline(pts, closed=False, n=14):
    """Катмулл-Ром: плотная гладкая ломаная через опорные точки."""
    pts = [tuple(map(float, p)) for p in pts]
    m = len(pts)
    if m < 3 and not closed:
        if m == 1:
            return pts
        (x0, y0), (x1, y1) = pts
        return [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n)] + [pts[-1]]
    out = []
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        if closed:
            a, b, c, d = pts[(i - 1) % m], pts[i], pts[(i + 1) % m], pts[(i + 2) % m]
        else:
            a = pts[max(i - 1, 0)]
            b, c = pts[i], pts[i + 1]
            d = pts[min(i + 2, m - 1)]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * b[j] + (-a[j] + c[j]) * t +
                                    (2 * a[j] - 5 * b[j] + 4 * c[j] - d[j]) * t2 +
                                    (-a[j] + 3 * b[j] - 3 * c[j] + d[j]) * t3) for j in (0, 1)))
    if not closed:
        out.append(pts[-1])
    return out


def smooth_scalar(vals, n=14):
    """сплайн по скалярам (ширины) с тем же числом отсчётов, что и cr_spline(open)."""
    v = [float(x) for x in vals]
    m = len(v)
    out = []
    for i in range(m - 1):
        a, b, c, d = v[max(i - 1, 0)], v[i], v[i + 1], v[min(i + 2, m - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t +
                              (-a + 3 * b - 3 * c + d) * t ** 3))
    out.append(v[-1])
    return out


def tube_outline(pts, widths, n=14):
    """Контур трубки переменной толщины вдоль сглаженной осевой линии."""
    c = cr_spline(pts, n=n)
    w = smooth_scalar(widths, n=n) if not np.isscalar(widths) else [widths] * len(c)
    left, right = [], []
    for i, (x, y) in enumerate(c):
        x0, y0 = c[max(i - 1, 0)]
        x1, y1 = c[min(i + 1, len(c) - 1)]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        h = max(w[i], 0.01) / 2
        left.append((x + nx * h, y + ny * h))
        right.append((x - nx * h, y - ny * h))
    return left + right[::-1], c, w


def rrect(cx, cy, w, h, r=2.5):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    return [(x0 + r, y0), (x1 - r, y0), (x1, y0 + r), (x1, y1 - r), (x1 - r, y1), (x0 + r, y1),
            (x0, y1 - r), (x0, y0 + r)]


def sym(pts):
    """правая половина (dx, y) сверху вниз -> замкнутый контур целиком"""
    right = [(CX + dx, y) for dx, y in pts]
    left = [(CX - dx, y) for dx, y in reversed(pts)]
    return right + left


def pip(pt, poly):
    x, y = pt
    ins = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi:
            ins = not ins
        j = i
    return ins
