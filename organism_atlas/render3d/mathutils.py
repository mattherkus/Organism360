"""Векторная математика для 3D."""

import numpy as np


def unit(v):
    v = np.asarray(v, np.float64)
    return v / (np.linalg.norm(v) + 1e-12)


def cr_nd(pts, n=12):
    """Катмулл-Ром в любой размерности"""
    p = np.asarray(pts, float)
    m = len(p)
    out = []
    for i in range(m - 1):
        a, b, c, d = p[max(i - 1, 0)], p[i], p[i + 1], p[min(i + 2, m - 1)]
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t ** 2 +
                          (-a + 3 * b - 3 * c + d) * t ** 3))
    out.append(p[-1][None])
    return np.vstack(out)
