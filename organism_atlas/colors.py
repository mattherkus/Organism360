"""Работа с цветом."""

import numpy as np


def hex2rgb(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255.0


def mixa(a, b, w):
    """смешать цвета: a,b - rgb(3,) или (h,w,3); w - (h,w) вес"""
    a = a if a.ndim == 3 else a[None, None, :]
    b = b if b.ndim == 3 else b[None, None, :]
    return a * (1 - w[..., None]) + b * w[..., None]
