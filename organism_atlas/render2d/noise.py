"""Размытие и процедурные шумы (numpy)."""

import numpy as np
from PIL import Image


def gblur(a, s):
    """гауссово размытие float-массива (быстро: большие сигмы считаем в уменьшенном виде)"""
    if s <= 0.05:
        return a
    if s > 5:
        f = int(s / 2.5)
        h, w = a.shape
        sm = Image.fromarray(a.astype(np.float32)).resize(
            (max(w // f, 2), max(h // f, 2)), Image.BILINEAR)
        sm = gblur(np.asarray(sm), s / f)
        return np.asarray(Image.fromarray(sm.astype(np.float32)).resize((w, h), Image.BICUBIC))
    r = int(3 * s) + 1
    x = np.arange(-r, r + 1)
    k = np.exp(-x * x / (2 * s * s))
    k /= k.sum()
    h, w = a.shape
    p = np.pad(a, ((0, 0), (r, r)), mode="edge")
    t = sum(k[i] * p[:, i:i + w] for i in range(len(k)))
    p = np.pad(t, ((r, r), (0, 0)), mode="edge")
    return sum(k[i] * p[i:i + h, :] for i in range(len(k)))


def fbm(shape, cell, octaves=4, seed=0, gain=0.5, stretch=(1.0, 1.0)):
    """фрактальный value-noise, нормированный к нулевому среднему и ед. разбросу.
    cell - размер самой крупной «ячейки» в пикселях; stretch растягивает узор (волокна)."""
    rng = np.random.default_rng(seed)
    h, w = shape
    out = np.zeros(shape, np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cy = max(cell * stretch[1] / (2 ** o), 1.2)
        cx = max(cell * stretch[0] / (2 ** o), 1.2)
        gh, gw = int(h / cy) + 4, int(w / cx) + 4
        g = rng.random((gh, gw), dtype=np.float32)
        im = Image.fromarray(g).resize((int(gw * cx), int(gh * cy)), Image.BICUBIC)
        out += amp * np.asarray(im)[:h, :w]
        tot += amp
        amp *= gain
    out /= tot
    return (out - out.mean()) / (out.std() + 1e-6)


def worley(shape, cell, seed=0):
    """клеточный шум Вороного: (F1, F2) - расстояния до ближайшей и второй точки, в пикселях"""
    rng = np.random.default_rng(seed)
    h, w = shape
    gh, gw = int(h / cell) + 3, int(w / cell) + 3
    pts = rng.random((gh, gw, 2)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gy = (yy / cell).astype(np.int32) + 1
    gx = (xx / cell).astype(np.int32) + 1
    f1 = np.full(shape, 1e9, np.float32)
    f2 = f1.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            px = ((gx + dx - 1) + pts[gy + dy, gx + dx, 0]) * cell
            py = ((gy + dy - 1) + pts[gy + dy, gx + dx, 1]) * cell
            d = np.hypot(xx - px, yy - py)
            f2 = np.minimum(f2, np.maximum(f1, d))
            f1 = np.minimum(f1, d)
    return f1, f2


def labyrinth(shape, lam, seed=0, iters=16):
    """лабиринтный узор (активатор-ингибитор): извилистые полосы с шагом ~lam пикселей"""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(shape).astype(np.float32)
    s1, s2 = lam * 0.17, lam * 0.36
    for _ in range(iters):
        u = np.tanh(2.6 * (gblur(u, s1) * 1.0 - gblur(u, s2) * 1.0) * 3.0)
    return u


def upsample(a, shape):
    """увеличить float-массив до нужной формы (бикубика)"""
    h, w = shape
    return np.asarray(Image.fromarray(a.astype(np.float32)).resize((w, h), Image.BICUBIC))
