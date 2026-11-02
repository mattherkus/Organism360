"""Слои с суперсэмплингом: Layer (маска) и Ink (линейные объекты с картой высоты)."""

import math

import numpy as np
from PIL import Image, ImageDraw

from ..colors import hex2rgb
from ..geometry import cr_spline, tube_outline
from .lighting import lighting
from .noise import gblur


class Layer:
    """Одноканальная маска 'L' в проектных координатах. Рисуем в SS раз крупнее,
    затем усредняем блоками SS*SS: это честное сглаживание по площади покрытия."""

    def __init__(self, box, Z, ss):
        x0, y0, x1, y1 = box
        self.Z, self.ss = Z, ss
        self.px0, self.py0 = int(math.floor(x0 * Z)), int(math.floor(y0 * Z))
        self.w = int(math.ceil(x1 * Z)) - self.px0
        self.h = int(math.ceil(y1 * Z)) - self.py0
        self.img = Image.new("L", (self.w * ss, self.h * ss), 0)
        self.d = ImageDraw.Draw(self.img)
        self.k = Z * ss

    def t(self, pts):
        k, ss = self.k, self.ss
        return [((x * k) - self.px0 * ss, (y * k) - self.py0 * ss) for x, y in pts]

    def poly(self, pts, v=255, smooth=True, closed=True):
        if smooth:
            pts = cr_spline(pts, closed=True)
        self.d.polygon(self.t(pts), fill=v)

    def raw(self, pts, v=255):
        self.d.polygon(self.t(pts), fill=v)

    def ellipse(self, cx, cy, rx, ry, v=255):
        (a, b), (c, d) = self.t([(cx - rx, cy - ry), (cx + rx, cy + ry)])
        self.d.ellipse((a, b, c, d), fill=v)

    def disc(self, x, y, r, v=255):
        self.ellipse(x, y, r, r, v)

    def line(self, pts, width, v=255, smooth=True):
        """толстая линия с круглыми концами"""
        c = cr_spline(pts) if smooth else list(pts)
        tp = self.t(c)
        wpx = max(width * self.k, 1.0)
        self.d.line(tp, fill=v, width=int(round(wpx)), joint="curve")
        r = wpx / 2
        for (x, y) in (tp[0], tp[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=v)

    def tube(self, pts, widths, v=255, n=14):
        outline, c, w = tube_outline(pts, widths, n=n)
        self.d.polygon(self.t(outline), fill=v)
        for i in (0, len(c) - 1):
            (x, y) = self.t([c[i]])[0]
            r = w[i] * self.k / 2
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=v)

    def tube_profile(self, pts, widths, steps=7, v=255, n=14):
        """трубка с цилиндрическим профилем высоты: концентрические штрихи, светлее к оси"""
        for s in range(steps):
            f = 1 - s / steps
            ww = [max(x * f, 0.2) for x in (widths if not np.isscalar(widths) else [widths] * len(pts))]
            o, c2, w2 = tube_outline(pts, ww, n=n)
            val = int(v * (s + 1) / steps)
            self.d.polygon(self.t(o), fill=val)
            for i in (0, len(c2) - 1):
                (x, y) = self.t([c2[i]])[0]
                r = w2[i] * self.k / 2
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=val)

    def get(self):
        """готовая сглаженная маска float32 [0..1]"""
        im = self.img.reduce(self.ss) if self.ss > 1 else self.img
        return np.asarray(im, dtype=np.float32) / 255.0

    @property
    def origin(self):
        return self.px0, self.py0


class Ink:
    """линейные объекты: покрытие + карта высоты (цилиндрический профиль)"""

    def __init__(self, box, Z, ss):
        self.cov = Layer(box, Z, ss)
        self.hgt = Layer(box, Z, ss)
        self.Z = Z

    def tube(self, pts, widths, n=14):
        self.cov.tube(pts, widths, n=n)
        self.hgt.tube_profile(pts, widths, n=n)

    def line(self, pts, width, smooth=True):
        self.tube(pts, [width] * len(pts))

    def part(self, name):
        """дальше рисуется кость или мышца name (structures.py строит по этим отметкам маски для клика);
        на сам рисунок не влияет"""

    def disc(self, x, y, r):
        self.cov.disc(x, y, r)
        for s in range(6):
            self.hgt.disc(x, y, r * (1 - s / 6), int(255 * (s + 1) / 6))

    def poly(self, pts, smooth=True):
        self.cov.poly(pts, smooth=smooth)
        self.hgt.poly(pts, 150, smooth=smooth)

    def cut(self, cx, cy, rx, ry):
        self.cov.ellipse(cx, cy, rx, ry, 0)
        self.hgt.ellipse(cx, cy, rx, ry, 0)

    def shaded(self, color, amp=3.0, spec=0.25, ambient=0.55, edge_dark=0.0, shin=18, gain=1.25):
        Z = self.Z
        cov = self.cov.get()
        hg = gblur(self.hgt.get(), 0.7 * Z) * amp * Z
        dif, sp = lighting(hg, ambient=ambient, spec=spec, shin=shin)
        col = hex2rgb(color)[None, None, :] * dif[..., None] * gain + sp[..., None]
        if edge_dark:
            e = np.clip((1 - gblur(cov, 1.0 * Z)) * cov * 2.0, 0, 1)
            col = col * (1 - edge_dark * e[..., None])
        return cov, np.clip(col, 0, 1)

    def paint(self, base, color, alpha, Z, amp=3.0, spec=0.25, ox=0, oy=0, ambient=0.55, edge_dark=0.0):
        cov, col = self.shaded(color, amp, spec, ambient, edge_dark)
        a = (cov * alpha)[..., None]
        h, w = cov.shape
        base[oy:oy + h, ox:ox + w] = base[oy:oy + h, ox:ox + w] * (1 - a) + col * a
        return a[..., 0]                       # непрозрачность: сколько закрыто под рисунком

    def over(self, rgba, color, alpha=1.0, **kw):
        """наложить на RGBA-кадр органа (прямая альфа)"""
        cov, col = self.shaded(color, **kw)
        return over_rgba(rgba, col, cov * alpha)


def over_rgba(rgba, col, a):
    ra = rgba[..., 3]
    na = a + ra * (1 - a)
    rgb = (col * a[..., None] + rgba[..., :3] * (ra * (1 - a))[..., None]) / np.maximum(na, 1e-5)[..., None]
    return np.dstack([rgb, na])
