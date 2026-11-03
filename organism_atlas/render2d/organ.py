"""Общие инструменты рисования органа: холст Org, затенение shade, упаковка результата finish."""

import numpy as np

from ..colors import hex2rgb
from .layers import Ink, Layer
from .lighting import lighting
from .noise import fbm, gblur, upsample, worley


class Org:
    def __init__(self, box, Z, ss, seed=1):
        self.box, self.Z, self.ss, self.seed = box, Z, ss, seed
        self.layers = {}

    def L(self, name):
        if name not in self.layers:
            self.layers[name] = Layer(self.box, self.Z, self.ss)
        return self.layers[name]

    def ink(self, name):
        if name not in self.layers:
            self.layers[name] = Ink(self.box, self.Z, self.ss)
        return self.layers[name]

    def m(self, name, blur=0.0):
        a = self.L(name).get()
        return gblur(a, blur * self.Z) if blur else a

    @property
    def shape(self):
        L = self.L("mask")
        return (L.h, L.w)

    @property
    def origin(self):
        return self.L("mask").origin

    def fill(self, color):
        """альбедо одного цвета (#rrggbb) на весь холст органа; копия - её можно менять"""
        return np.broadcast_to(hex2rgb(color), self.shape + (3,)).copy()

    def noise(self, cell, octaves=3, seed=0, stretch=(1, 1)):
        return fbm(self.shape, cell * self.Z, octaves, self.seed * 31 + seed, stretch=stretch)

    def cells(self, cell, seed=0, border=0.26):
        """дольки (клетки Вороного): (кромка долек 0..1, «купол» дольки 0..1).
        Считаются в фиксированном разрешении, чтобы рисунок не зависел от масштаба."""
        h, w = self.shape
        ch, cw = int(h / self.Z * 3) + 2, int(w / self.Z * 3) + 2
        f1, f2 = worley((ch, cw), cell * 3, self.seed * 31 + seed)
        edge = upsample(1 - np.clip((f2 - f1) / (border * cell * 3), 0, 1), (h, w))
        dome = upsample(1 - np.clip(f1 / (0.8 * cell * 3), 0, 1), (h, w))
        return edge, dome


def shade(o, albedo, bump, mask, soft=(5.0, 13.0), amp=(6.0, 7.0), ambient=0.48, spec=0.3, shin=24,
          edge_dark=0.5, relief=1.0, ink=(0.06, 0.05, 0.07), light=(-0.45, -0.65, 0.62)):
    Z = o.Z
    h = gblur(mask, soft[0] * Z) * amp[0] * Z + gblur(mask, soft[1] * Z) * amp[1] * Z + bump * Z
    dif, sp = lighting(h, ambient=ambient, spec=spec, shin=shin, relief=relief, light=light)
    rgb = albedo * dif[..., None] * 1.18 + sp[..., None]
    ao = np.clip(gblur(mask, 3.5 * Z) * 1.7 - 0.3, 0, 1)
    rgb *= (1 - edge_dark + edge_dark * ao)[..., None]
    edge = np.clip((1 - gblur(mask, 1.1 * Z)) * mask * 2.2, 0, 1)[..., None]
    rgb = rgb * (1 - 0.8 * edge) + np.array(ink, np.float32) * 0.8 * edge
    return np.dstack([np.clip(rgb, 0, 1), mask])


def finish(o, rgba, hit=None):
    hit = rgba[..., 3] if hit is None else hit
    return {"rgba": rgba.astype(np.float32), "hit": hit.astype(np.float32), "origin": o.origin}
