"""Материалы поверхности: цвет и рельеф по типу текстуры."""

import numpy as np

from .textures import fbm3, tile_labyrinth, tile_worley, triplanar


def surface(mat, P, N, sl):
    """возвращает (множитель альбедо (n,3), высота (n,)) для материала"""
    base = mat["color"]
    tex = mat["tex"]
    n = len(P)
    mult = np.ones(n, np.float32)
    tint = np.ones((n, 3), np.float32)
    h = np.zeros(n, np.float32)
    if tex == "smooth":
        mult += 0.03 * fbm3(P, 2.0, 2, 1)
    elif tex == "lung":
        mult += 0.055 * fbm3(P, 3.0, 3, 2) + 0.028 * fbm3(P, 16, 2, 3)
        mult -= 0.14 * np.clip(fbm3(P, 2.0, 2, 4) - 0.9, 0, 2)
        wor = triplanar(tile_worley(), P, N, 0.55)
        mult -= 0.14 * (1 - wor)
        h = 0.05 * wor
    elif tex == "gyri":
        lab = triplanar(tile_labyrinth(), P, N, 0.42)
        sul = np.clip((-lab - 0.10) * 1.6, 0, 1)
        mult += 0.04 * np.clip((lab + 0.15) * 1.2, 0, 1) - 0.45 * sul
        tint = np.where(sul[:, None] > 0, np.array([1.0, 0.90, 0.93], np.float32) ** sul[:, None], tint)
        h = -0.075 * sul
    elif tex == "folia":
        f = np.exp(-(np.sin(P[:, 2] * 17 + 1.2 * fbm3(P, 2.2, 2, 6)) / 0.38) ** 2)
        mult -= 0.30 * f
        h = -0.03 * f
    elif tex == "liver":
        mult += 0.045 * fbm3(P, 1.8, 2, 7) + 0.015 * fbm3(P, 9, 2, 8)
    elif tex == "muscle":
        m = fbm3(P, 4.2, 3, 9)
        mult += 0.035 * m
        h = 0.004 * m
    elif tex == "gland":
        wor = triplanar(tile_worley(), P, N, 0.32)
        mult += 0.04 * fbm3(P, 3.0, 2, 11) - 0.20 * (1 - wor)
        h = 0.035 * wor
    elif tex == "bowel":
        mult += 0.035 * fbm3(P, 5, 2, 10)
    if mat["rings"]:
        mult *= 1 - 0.30 * np.abs(np.sin(sl * np.pi / mat["rings"])) ** 5
        h = h - 0.012 * np.abs(np.sin(sl * np.pi / mat["rings"])) ** 5
    if mat["hause"]:
        fold = np.abs(np.cos(sl * np.pi / 0.5)) ** 14
        mult *= 1 - 0.34 * fold
        h = h - 0.03 * fold
    return (base[None, :] * mult[:, None] * tint), h
