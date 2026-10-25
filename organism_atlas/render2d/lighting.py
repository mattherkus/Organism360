"""Модель освещения по карте высот."""

import numpy as np


def lighting(height, light=(-0.45, -0.65, 0.62), ambient=0.5, spec=0.3, shin=28, relief=1.0):
    """Модель освещения по карте высот: возвращает (diffuse, specular) float [0..1]."""
    gy, gx = np.gradient(height.astype(np.float32))
    nx, ny, nz = -gx * relief, -gy * relief, np.ones_like(gx)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / ln, ny / ln, nz / ln
    L = np.array(light, np.float32)
    L /= np.linalg.norm(L)
    dif = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    Hh = L + np.array([0, 0, 1], np.float32)
    Hh /= np.linalg.norm(Hh)
    sp = np.clip(nx * Hh[0] + ny * Hh[1] + nz * Hh[2], 0, 1) ** shin
    return ambient + (1 - ambient) * dif, sp * spec
