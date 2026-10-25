"""Бесшовные тайлы и 3D-шум для поверхностей органов."""

import math

import numpy as np


def blur_fft(a, s):
    """периодическое гауссово размытие через FFT"""
    f = np.fft.fftfreq(a.shape[0])[:, None] ** 2 + np.fft.fftfreq(a.shape[1])[None, :] ** 2
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (np.pi * s) ** 2 * f))).astype(np.float32)


_TILES = {}


def tile_labyrinth(n=192):
    """бесшовный лабиринтный узор (для извилин мозга)"""
    if "lab" not in _TILES:
        rng = np.random.default_rng(5)
        u = rng.standard_normal((n, n)).astype(np.float32)
        for _ in range(18):
            u = np.tanh(7.0 * (blur_fft(u, 1.7) - blur_fft(u, 3.6)))
        _TILES["lab"] = blur_fft(u, 0.7)
    return _TILES["lab"]


def tile_worley(n=192, cells=14):
    """бесшовные клетки Вороного (дольки лёгких): 0 на границах клеток, 1 в центре"""
    if "wor" not in _TILES:
        rng = np.random.default_rng(9)
        pts = rng.random((cells, cells, 2))
        cs = n / cells
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        gy, gx = (yy / cs).astype(np.int32), (xx / cs).astype(np.int32)
        f1 = np.full((n, n), 1e9, np.float32)
        f2 = f1.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = gy + dy, gx + dx
                px = (nx + pts[ny % cells, nx % cells, 0]) * cs
                py = (ny + pts[ny % cells, nx % cells, 1]) * cs
                d = np.hypot(xx - px, yy - py)
                f2 = np.minimum(f2, np.maximum(f1, d))
                f1 = np.minimum(f1, d)
        _TILES["wor"] = np.clip((f2 - f1) / (0.32 * cs), 0, 1).astype(np.float32)
    return _TILES["wor"]


def tile_veins(n=256):
    """бесшовная сеть мелких сосудов: 1 на сосуде, 0 вне. Сосуды - линии уровня гладкого шума
    двух масштабов: крупные извилистые стволы и редкие тонкие веточки между ними"""
    if "veins" not in _TILES:
        rng = np.random.default_rng(13)

        def field(s):
            f = blur_fft(rng.standard_normal((n, n)).astype(np.float32), s)
            return f / (f.std() + 1e-9)

        trunks = np.exp(-(field(7.0) / 0.07) ** 2)
        twigs = np.exp(-(field(3.0) / 0.09) ** 2) * np.clip(field(12.0) + 0.2, 0, 1)
        _TILES["veins"] = np.maximum(trunks, 0.55 * twigs).astype(np.float32)
    return _TILES["veins"]


def sample(tex, u, v):
    n = tex.shape[0]
    x, y = (u % 1.0) * n, (v % 1.0) * n
    x0, y0 = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    fx, fy = x - x0, y - y0
    x0, y0 = x0 % n, y0 % n
    x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy) +
            tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)


def triplanar(tex, P, N, scale):
    w = np.abs(N) ** 4
    w /= w.sum(-1, keepdims=True) + 1e-9
    q = P * scale
    return (w[:, 0] * sample(tex, q[:, 1], q[:, 2]) + w[:, 1] * sample(tex, q[:, 0], q[:, 2]) +
            w[:, 2] * sample(tex, q[:, 0], q[:, 1]))


def fbm3(p, f, octs=3, seed=0):
    """гладкий псевдошум в 3D (суммы синусов), приблизительно единичный разброс"""
    rng = np.random.default_rng(seed)
    out = np.zeros(len(p), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octs):
        for _ in range(4):
            d = rng.normal(size=3)
            d /= np.linalg.norm(d)
            out += amp * np.sin(p @ d.astype(np.float32) * (f * 2 ** o * rng.uniform(0.85, 1.2)) +
                                rng.uniform(0, 6.283))
        tot += amp * amp
        amp *= 0.55
    return out / math.sqrt(tot * 2.0)
