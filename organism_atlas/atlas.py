"""Схема тела по слоям: слои тела, органы, маски попадания, подсветка. Не зависит от Tk.

Стек снизу вверх: фон темы со свечением вокруг тела, кожа (skin), мышцы (muscles), скелет (skeleton), вены (veins),
артерии (arteries), растворение ног у нижнего края (fade), затем органы в порядке ORDER.
Слои хранятся отдельно (uint8, RGBA с прямой альфой), поэтому скрыть слой или орган можно без
перерисовки остальных; composite() собирает картинку целиком.
"""

import math
import queue
import threading

import numpy as np
from PIL import Image

from . import atlas_cache, structures
from .body.base import BG_HI, BODY_LAYERS, DEFAULT_LAYERS, background, build_layers, compose, glow_weight, over
from .config import BG
from .config import TARGET_C
from .organs import BEHIND, ORDER, PAINT
from .render2d.noise import gblur

BODY_ARRAYS = ("glow", "skin", "skin_hi", "muscles", "skeleton", "veins", "arteries", "fade")
# «живая» схема: сердце бьётся, лёгкие дышат. Слой органа масштабируется по времени (маски попадания не меняются)
BEAT = 60 / 72                  # период сердцебиения, с (72 удара в минуту)
SYSTOLE = 0.32                  # доля периода, за которую сердце сжимается и расслабляется
BEAT_DEPTH = 0.045              # насколько сердце сжимается (доля размера)
BREATH = 4.5                    # период дыхания, с
BREATH_DEPTH = (0.015, 0.035)   # насколько лёгкие расширяются вширь и вниз на вдохе
HEART_BASE = 0.35               # где у слоя сердца основание (доля высоты сверху): к нему оно сжимается
ANIMATED = ("lungs", "heart")
PAD = 4                         # прозрачная рамка вокруг слоя сердца и лёгких для анимации: хватает до сжатия в 0.75
HALO = 14                       # запас вокруг органа под свечение подсветки (в пикселях схемы при Z = 1)
LIGHT_FROM = 0.6                # с какой средней яркости орган считается светлым (контур подсветки насыщеннее)


def build_atlas(Z):
    """Рисует слои тела и органы. Возвращает ({слой тела: float-массив}, {орган: {rgba, hit, origin}})."""
    ss_b = 4 if Z <= 1.5 else 3          # суперсэмплинг: тело
    ss_o = 6 if Z <= 1.5 else 4          # суперсэмплинг: органы (мелкие детали)
    body = build_layers(Z, ss_b)
    organs = {k: PAINT[k](Z, ss_o) for k in ORDER}
    return body, organs


def to_u8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


class Atlas:
    """Схема тела целиком. Не зависит от Tk: отдаёт картинки Pillow."""

    def __init__(self, Z, data=None):
        """data - готовые ({слой тела: uint8}, {орган: {rgba uint8, hit, origin}}), например из кэша;
        без него схема рисуется заново"""
        self.Z = Z
        if data is None:
            body, organs = build_atlas(Z)
            data = ({k: to_u8(body[k]) for k in BODY_ARRAYS},
                    {k: {"rgba": to_u8(d["rgba"]), "hit": d["hit"].astype(np.float32), "origin": d["origin"]}
                     for k, d in organs.items()})
        self.body, self.org = data
        self.size = self.body["skin"].shape[1], self.body["skin"].shape[0]
        self.hidden = frozenset()        # скрытые органы: не ловят клик и не закрывают нижние
        self.visible = DEFAULT_LAYERS    # видимые слои тела
        self.skin_opacity = 1.0          # непрозрачность кожи (0 - кожи не видно, 1 - как нарисована)
        self._bg = (BG, BG_HI)           # цвета фона (тема)
        self._base = None
        self._show = {}                  # заготовки для base при текущем фоне: кожа с фоном, растворение
        self._glow = None
        self._cache = {}                 # {(орган, вид): подсветка} при текущих скрытых органах
        self._warm = queue.SimpleQueue() # подсветки, посчитанные заранее в фоне: (скрытые, (орган, вид), подсветка)
        self._gen = 0                    # номер расчёта заранее: сменился - прежний поток бросает работу
        self._layers = {}
        self._premul = {}                # слои сердца и лёгких для анимации: альфа умножена (RGBa), рамка PAD
        self._under = None               # (прямоугольник, подложка анимации): всё, что под лёгкими
        self._punched = {}               # {орган из BEHIND: (видимые закрывающие, слой с вырезом)}
        self._struct = None              # маски костей и мышц (structures.masks), считаются один раз

    # --- слои
    def layer(self, name):
        """слой по id (skin, skeleton, veins, arteries или ключ органа): (RGBA Pillow, origin)"""
        if name not in self._layers:
            if name in self.org:
                d = self.org[name]
                self._layers[name] = (Image.fromarray(d["rgba"], "RGBA"), tuple(d["origin"]))
            else:
                self._layers[name] = (Image.fromarray(self.body[name], "RGBA"), (0, 0))
        return self._layers[name]

    def behind_cover(self, key, hidden=None, pad=0):
        """насколько орган key (из BEHIND) закрыт видимыми органами, которые лежат ниже него в ORDER, но перед ним
        (0..1, в рамке органа с запасом pad); None - таких нет"""
        hidden = self.hidden if hidden is None else hidden
        front = [k for k in BEHIND.get(key, ()) if k not in hidden]
        if not front:
            return None
        d = self.org[key]
        x0, y0 = d["origin"][0] - pad, d["origin"][1] - pad
        h, w = d["hit"].shape[0] + 2 * pad, d["hit"].shape[1] + 2 * pad
        cov = np.zeros((h, w), np.float32)
        for k in front:
            e = self.org[k]
            ex, ey = e["origin"]
            eh, ew = e["rgba"].shape[:2]
            ax0, ay0 = max(x0, ex), max(y0, ey)
            ax1, ay1 = min(x0 + w, ex + ew), min(y0 + h, ey + eh)
            if ax1 <= ax0 or ay1 <= ay0:
                continue
            part = e["rgba"][ay0 - ey:ay1 - ey, ax0 - ex:ax1 - ex, 3].astype(np.float32) / 255
            sl = (slice(ay0 - y0, ay1 - y0), slice(ax0 - x0, ax1 - x0))
            cov[sl] = np.maximum(cov[sl], part)
        return cov

    def shown(self, key):
        """слой органа для показа (Pillow RGBA, origin): у органа из BEHIND вырезано то, что закрывают
        видимые органы перед ним"""
        if key not in BEHIND:
            return self.layer(key)
        front = frozenset(k for k in BEHIND[key] if k not in self.hidden)
        if key not in self._punched or self._punched[key][0] != front:
            im, pos = self.layer(key)
            cov = self.behind_cover(key)
            if cov is not None:
                arr = np.asarray(im).copy()
                arr[..., 3] = (arr[..., 3].astype(np.float32) * (1 - cov) + 0.5).astype(np.uint8)
                im = Image.fromarray(arr, "RGBA")
            self._punched[key] = (front, (im, pos))
        return self._punched[key][1]

    def _back(self, bg, hi):
        if self._glow is None:
            self._glow = glow_weight(self.Z, self.body["skin"].shape[:2])
        return background(self.Z, bg, hi, self._glow)

    def skin_image(self, bg=BG, hi=BG_HI, opacity=1.0):
        """нижний слой для показа: фон темы, свечение и кожа с прозрачностью opacity (0 - кожи нет).
        Свечение и добавка к кромке не выражаются прямой альфой, поэтому кожа отдаётся вместе с фоном."""
        out = compose(self.body, self._back(bg, hi), visible=("skin",), skin_opacity=opacity)
        return Image.fromarray(to_u8(out))

    def fade_image(self, bg=BG, hi=BG_HI):
        """растворение ног у нижнего края: цвет фона с непрозрачностью fade (RGBA)"""
        back = self._back(bg, hi)
        a = np.broadcast_to(self.body["fade"][:, None, None], back.shape[:2] + (1,))
        return Image.fromarray(np.dstack([to_u8(back), a]), "RGBA")

    def composite(self, bg=BG, hi=BG_HI, visible=DEFAULT_LAYERS, skin_opacity=1.0, organs=None):
        """схема целиком (Pillow RGB): видимые слои тела и органы organs (по умолчанию все, кроме скрытых)"""
        back = self._back(bg, hi)
        out = compose(self.body, back, visible, skin_opacity)
        organs = [k for k in ORDER if k not in self.hidden] if organs is None else organs
        hidden = frozenset(ORDER) - set(organs)
        for k in ORDER:
            if k in organs:
                d = self.org[k]
                (ox, oy), (h, w) = d["origin"], d["rgba"].shape[:2]
                rgba = d["rgba"].astype(np.float32) / 255
                cov = self.behind_cover(k, hidden) if k in BEHIND else None
                if cov is not None:
                    rgba[..., 3] *= 1 - cov
                over(out[oy:oy + h, ox:ox + w], rgba)
        return Image.fromarray(to_u8(out))

    def _assemble(self, organs):
        """фон темы, видимые слои тела и органы organs (по порядку ORDER) средствами Pillow"""
        skin = self.skin_opacity if "skin" in self.visible else 0.0
        if skin not in self._show:
            # свечение и кромка кожи не выражаются прямой альфой, поэтому кожа - вместе с фоном.
            # Храним только кожу текущей прозрачности (и без кожи): ползунок не копит картинки
            for k in [k for k in self._show if k not in ("fade", 0.0)]:
                del self._show[k]
            out = compose(self.body, self._back(*self._bg), ("skin",) if skin else (), skin_opacity=skin or 1.0,
                          fade=False)
            self._show[skin] = Image.fromarray(to_u8(out))
        if "fade" not in self._show:
            self._show["fade"] = self.fade_image(*self._bg)
        out = self._show[skin].copy()
        for name in BODY_LAYERS[1:]:
            if name in self.visible:
                im, pos = self.layer(name)
                out.paste(im, pos, im)
        out.paste(self._show["fade"], (0, 0), self._show["fade"])
        for k in ORDER:
            if k in organs:
                im, pos = self.shown(k)
                out.paste(im, pos, im)
        return out

    @property
    def base(self):
        """готовая картинка Pillow для показа: фон темы, видимые слои тела и нескрытые органы.
        Собирается быстро (на каждый щелчок в панели слоёв): кожа с фоном считается в numpy один раз,
        кости, сосуды, растворение ног и органы кладутся средствами Pillow. От composite() отличается
        только округлением (на 1-2 уровня из 255)"""
        if self._base is None:
            self._base = self._assemble([k for k in ORDER if k not in self.hidden])
            self._under = None                   # подложка анимации - от прежнего вида
        return self._base

    # --- анимация: сердце и лёгкие
    def anim_box(self):
        """(x0, y0, x1, y1) - прямоугольник схемы, который меняется при анимации (с запасом на вдох);
        None - сердце и лёгкие скрыты"""
        keys = [k for k in ANIMATED if k not in self.hidden]
        if not keys:
            return None
        boxes = []
        for k in keys:
            im, (x, y) = self.layer(k)
            w, h = im.size
            grow_x = w * BREATH_DEPTH[0] / 2 if k == "lungs" else 0
            grow_y = h * BREATH_DEPTH[1] if k == "lungs" else 0
            boxes.append((x - grow_x - 2, y - 2, x + w + grow_x + 2, y + h + grow_y + 2))
        x0, y0 = (max(0, int(math.floor(min(b[i] for b in boxes)))) for i in (0, 1))
        x1 = min(self.size[0], int(math.ceil(max(b[2] for b in boxes))))
        y1 = min(self.size[1], int(math.ceil(max(b[3] for b in boxes))))
        return x0, y0, x1, y1

    def anim_frame(self, t):
        """кусок схемы в момент t (секунды): (картинка, (x0, y0)) или None, если анимировать нечего.
        Подложка - всё, что лежит под лёгкими (считается один раз на вид схемы), сверху - лёгкие и сердце
        в своём масштабе и органы над ними"""
        self.base  # noqa: B018                          # пересобрать вид, если он сменился
        box = self.anim_box()
        if box is None:
            return None
        keys = [k for k in ANIMATED if k not in self.hidden]
        first = min(ORDER.index(k) for k in keys)
        if self._under is None or self._under[0] != box:
            below = [k for k in ORDER[:first] if k not in self.hidden]
            self._under = (box, self._assemble(below).crop(box))
        x0, y0, x1, y1 = box
        out = self._under[1].copy()
        scale = {"heart": (heartbeat(t),) * 2, "lungs": breathing(t)}
        for k in ORDER[first:]:
            if k in self.hidden:
                continue
            im, (x, y) = self.shown(k)
            w, h = im.size
            if x >= x1 or y >= y1 or x + w <= x0 or y + h <= y0:
                continue
            if k not in scale:
                out.paste(im, (x - x0, y - y0), im)
                continue
            sx, sy = scale[k]
            # сердце сжимается к основанию (там отходят крупные сосуды - дуга аорты почти не двигается),
            # лёгкие расширяются от верхушек вниз
            px, py = x + w / 2, y + (h * HEART_BASE if k == "heart" else 0)
            # куда ложится слой органа в этом масштабе (с запасом в пиксель на сглаживание): считаем только там,
            # а не по всему куску - маленькое сердце в большом прямоугольнике лёгких почти ничего не стоит
            rx0 = max(x0, math.floor(px + (x - px) * sx) - 1)
            ry0 = max(y0, math.floor(py + (y - py) * sy) - 1)
            rx1 = min(x1, math.ceil(px + (x + w - px) * sx) + 1)
            ry1 = min(y1, math.ceil(py + (y + h - py) * sy) + 1)
            if rx1 <= rx0 or ry1 <= ry0:
                continue
            if k not in self._premul:                    # альфу умножаем один раз, а не на каждом кадре
                self._premul[k] = Image.new("RGBa", (w + 2 * PAD, h + 2 * PAD))
                self._premul[k].paste(im.convert("RGBa"), (PAD, PAD))
            # какой прямоугольник слоя органа (с долями пикселя: без дрожания) растягивается в этот кусок.
            # Масштаб без поворота - это resize с рамкой источника: он вдвое быстрее общего transform
            u, v = px - x + (rx0 - px) / sx + PAD, py - y + (ry0 - py) / sy + PAD
            ow, oh = rx1 - rx0, ry1 - ry0
            src = self._premul[k]
            box = (max(0.0, u), max(0.0, v), min(src.width, u + ow / sx), min(src.height, v + oh / sy))
            moved = src.resize((ow, oh), Image.BILINEAR, box=box)
            moved = moved.convert("RGBA")
            out.paste(moved, (rx0 - x0, ry0 - y0), moved)
        return out, (x0, y0)

    def set_background(self, bg, hi):
        """подставить фон схемы (цвета #rrggbb из темы); возвращает self.base (пересобранную, если фон другой)"""
        if (bg, hi) != self._bg:
            self._bg = (bg, hi)
            self._show.clear()
            self._base = None
        return self.base

    def set_layers(self, visible):
        """какие слои тела видны (из BODY_LAYERS); картинка self.base пересоберётся при обращении"""
        visible = tuple(name for name in BODY_LAYERS if name in visible)
        if visible != self.visible:
            self.visible = visible
            self._base = None

    def set_skin_opacity(self, value):
        """непрозрачность кожи 0..1; картинка self.base пересоберётся при обращении"""
        value = round(max(0.0, min(1.0, value)), 2)
        if value != self.skin_opacity:
            self.skin_opacity = value
            self._base = None

    def anchor(self, key):
        """точка для подписи органа (x, y) в пикселях схемы: над серединой органа, у его верхнего края"""
        d = self._shape(key)
        ys, xs = np.nonzero(d["hit"] > 0.5)
        if not len(xs):
            return d["origin"][0] + d["hit"].shape[1] / 2, d["origin"][1]
        cx = float(xs.mean())
        col = ys[np.abs(xs - cx) <= max(2, 0.1 * (xs.max() - xs.min()))]      # верх органа над серединой
        return d["origin"][0] + cx, d["origin"][1] + float(col.min() if len(col) else ys.min())

    @classmethod
    def cached(cls, Z, cache_dir=atlas_cache.CACHE_DIR, prebuilt=atlas_cache.PREBUILT):
        """схема из кэша на диске (или готовая из сборки), а если её там нет - нарисовать и сохранить"""
        Z = atlas_cache.zoom_key(Z)
        data = atlas_cache.load(Z, ORDER, cache_dir, prebuilt)
        if data is not None:
            return cls(Z, data)
        atlas = cls(Z)
        atlas_cache.save(Z, atlas.body, atlas.org, cache_dir)
        return atlas

    @classmethod
    def preview(cls, Z, cache_dir=atlas_cache.CACHE_DIR, prebuilt=atlas_cache.PREBUILT):
        """схема масштаба Z, если она уже есть (кэш или сборка), иначе готовая схема из сборки ближайшего
        масштаба - её можно показать растянутой; None, если нет ни той, ни другой"""
        Z = atlas_cache.zoom_key(Z)
        data = atlas_cache.load(Z, ORDER, cache_dir, prebuilt)
        if data is not None:
            return cls(Z, data)
        found = atlas_cache.nearest(Z, ORDER, prebuilt)
        return None if found is None else cls(*found)

    # --- видимость органов
    def set_hidden(self, organs):
        """какие органы скрыты (не рисуются и не ловят клик); подсветка зависит от того, кто кого закрывает,
        поэтому её кэш сбрасывается"""
        organs = frozenset(organs)
        if organs != self.hidden:
            self.hidden = organs
            self._cache.clear()
            self._gen += 1
            self._base = None

    def organ_at(self, x, y):
        """какой видимый орган под точкой (x, y) в пикселях картинки; верхний слой имеет приоритет"""
        for k in reversed(ORDER):
            if k in self.hidden:
                continue
            d = self.org[k]
            ox, oy = d["origin"]
            h, w = d["hit"].shape
            xi, yi = int(x) - ox, int(y) - oy
            if 0 <= xi < w and 0 <= yi < h and d["hit"][yi, xi] > 0.5 and not self._in_front(k, x, y):
                return k
        return None

    def _in_front(self, key, x, y):
        """закрывает ли точку видимый орган, лежащий перед key, хотя и ниже него в ORDER (BEHIND)"""
        for k in BEHIND.get(key, ()):
            if k in self.hidden:
                continue
            d = self.org[k]
            ox, oy = d["origin"]
            h, w = d["hit"].shape
            xi, yi = int(x) - ox, int(y) - oy
            if 0 <= xi < w and 0 <= yi < h and d["hit"][yi, xi] > 0.5:
                return True
        return False

    def _cover(self, key, pad=0, hidden=None):
        """насколько орган перекрыт видимыми органами, лежащими выше него; pad - запас вокруг рамки органа,
        hidden - скрытые органы (по умолчанию текущие)"""
        hidden = self.hidden if hidden is None else hidden
        d = self._shape(key)
        x0, y0 = d["origin"][0] - pad, d["origin"][1] - pad
        h, w = d["hit"].shape[0] + 2 * pad, d["hit"].shape[1] + 2 * pad
        cov = np.zeros((h, w), np.float32)
        front = self.behind_cover(key, hidden, pad) if key in BEHIND else None
        if front is not None:                             # органы перед ним, хотя и ниже в ORDER
            cov = front
        above = ORDER[ORDER.index(key) + 1:] if key in self.org else ORDER   # кость или мышцу закрывают все органы
        for k in above:
            if k in hidden or key in BEHIND.get(k, ()):   # k лежит выше, но за этим органом
                continue
            e = self.org[k]
            ex, ey = e["origin"]
            eh, ew = e["hit"].shape
            ax0, ay0 = max(x0, ex), max(y0, ey)
            ax1, ay1 = min(x0 + w, ex + ew), min(y0 + h, ey + eh)
            if ax1 <= ax0 or ay1 <= ay0:
                continue
            part = e["hit"][ay0 - ey:ay1 - ey, ax0 - ex:ax1 - ex]
            sl = (slice(ay0 - y0, ay1 - y0), slice(ax0 - x0, ax1 - x0))
            cov[sl] = np.maximum(cov[sl], part)
        return cov

    # --- карта знаний: органы тонируются цветом уровня знания (stats.mastery)
    def tint(self, colors, strength=0.5):
        """слой поверх схемы (Pillow RGBA во всю схему): видимые органы из colors ({орган: (r, g, b) 0..1})
        закрашены своим цветом с непрозрачностью strength; органы без цвета закрывают тонировку тех, что под ними"""
        w, h = self.size
        rgb = np.zeros((h, w, 3), np.float32)              # с умноженной альфой
        a = np.zeros((h, w), np.float32)
        for k in ORDER:
            if k in self.hidden:
                continue
            im, (ox, oy) = self.shown(k)
            cov = np.asarray(im)[..., 3].astype(np.float32) / 255
            x0, y0 = max(0, ox), max(0, oy)
            x1, y1 = min(w, ox + cov.shape[1]), min(h, oy + cov.shape[0])
            if x1 <= x0 or y1 <= y0:
                continue
            cov = cov[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
            sl = (slice(y0, y1), slice(x0, x1))
            if k in colors:
                ca = cov * strength
                rgb[sl] = rgb[sl] * (1 - ca[..., None]) + np.asarray(colors[k], np.float32) * ca[..., None]
                a[sl] = a[sl] * (1 - ca) + ca
            else:
                rgb[sl] *= (1 - cov)[..., None]
                a[sl] *= 1 - cov
        out = rgb / np.maximum(a, 1e-5)[..., None]
        return Image.fromarray(to_u8(np.dstack([out, a])), "RGBA")

    # --- кости и мышцы (structures.py): ловят клик там, где нет органа, если их слой тела виден
    def structures(self):
        """{кость или мышца: {"hit", "origin"}}; считается при первом обращении (быстро: доли секунды)"""
        if self._struct is None:
            self._struct = structures.masks(self.Z)
        return self._struct

    def _shape(self, key):
        """маска попадания и положение органа или кости/мышцы"""
        return self.org[key] if key in self.org else self.structures()[key]

    def structure_at(self, x, y):
        """какая кость или мышца под точкой (x, y), если её слой тела виден; органы лежат выше - их проверяет
        organ_at, а здесь не проверяются"""
        layers = {kind for kind, layer in structures.LAYER_OF.items() if layer in self.visible}
        if not layers:
            return None
        found = self.structures()
        for k in structures.HIT_ORDER:
            if structures.kind(k) not in layers or k not in found:
                continue
            d = found[k]
            ox, oy = d["origin"]
            h, w = d["hit"].shape
            xi, yi = int(x) - ox, int(y) - oy
            if 0 <= xi < w and 0 <= yi < h and d["hit"][yi, xi] > 0.5:
                return k
        return None

    def overlay(self, key, kind):
        """RGBA-картинка подсветки и её положение. kind: hover / target / ok / bad"""
        while True:                                       # что успел посчитать warm(), если оно ещё годится
            try:
                hidden, done, item = self._warm.get_nowait()
            except queue.Empty:
                break
            if hidden == self.hidden:
                self._cache.setdefault(done, item)
        if (key, kind) not in self._cache:
            self._cache[(key, kind)] = self._make(key, kind)
        return self._cache[(key, kind)]

    def warm(self, kind="hover"):
        """посчитать заранее, в фоновом потоке, подсветку kind всех видимых органов (крупные - первыми): первое
        наведение на орган не ждёт её расчёта (на большом экране это десятки миллисекунд). Готовые забирает
        overlay(); скрыли или показали орган - прежний расчёт бросается, а его подсветки не берутся.
        Возвращает поток (тестам - дождаться его)"""
        self._gen += 1
        gen, hidden = self._gen, self.hidden
        keys = sorted((k for k in ORDER if k not in hidden and (k, kind) not in self._cache),
                      key=lambda k: -self.org[k]["hit"].size)

        def work():
            for k in keys:
                if self._gen != gen:
                    return
                self._warm.put((hidden, (k, kind), self._make(k, kind, hidden)))

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread

    def stop_warm(self):
        """бросить расчёт подсветки заранее: схема больше не нужна (окно перешло на другой масштаб)"""
        self._gen += 1

    def _lum(self, key):
        """средняя яркость органа (0..1) по его видимым пикселям"""
        d = self._shape(key)
        m = d["hit"] > 0.5
        if not m.any():
            return 0.0
        if "rgba" in d:
            rgb = d["rgba"][..., :3]
        else:                                             # кость или мышца: цвет - из её слоя тела
            (ox, oy), (h, w) = d["origin"], d["hit"].shape
            rgb = self.body[structures.LAYER_OF[structures.kind(key)]][oy:oy + h, ox:ox + w, :3]
            m = m[:rgb.shape[0], :rgb.shape[1]]
        return float((rgb[m].astype(np.float32) / 255 @ np.array([0.2126, 0.7152, 0.0722])).mean())

    def _make(self, key, kind, hidden=None):
        """подсветка органа key вида kind при скрытых органах hidden (по умолчанию текущих). Только читает
        схему, поэтому её можно считать в фоновом потоке (warm)"""
        Z = self.Z
        d = self._shape(key)
        # рамка органа - вплотную к нему: свечение и контур снаружи не поместились бы, а у узкого органа
        # (трахея) их съедало бы и гашение у края. Поэтому подсветка - на рамке с запасом pad со всех сторон
        pad = int(np.ceil(HALO * Z))
        m = np.pad(d["hit"], pad)
        h, w = m.shape
        vis = 1.0 - np.clip(self._cover(key, pad, hidden), 0, 1)
        g1 = gblur(m, 1.3 * Z)
        rim = np.clip((1 - g1) * m * 2.2 + g1 * (1 - m) * 2.4, 0, 1)
        glow = gblur(m, 3.4 * Z) * (1 - m)
        yy, xx = np.mgrid[0:h, 0:w]
        edge = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)).astype(np.float32)
        fade = np.clip(edge / (7.0 * Z), 0, 1)            # мягко гасим подсветку у края кадра
        # светлый орган (трахея, мочевой пузырь): почти белый контур на нём не виден - берём насыщенный
        # цвет подсветки и заливку плотнее. light: 0 - орган тёмный или средний, 1 - светлый
        light = float(np.clip((self._lum(key) - LIGHT_FROM) / 0.15, 0, 1))
        if kind == "hover":
            a = rim * 0.95 + glow * 0.55 + m * (0.10 + 0.25 * light)
            glow_c = np.array([0.55, 0.82, 1.0], np.float32)
            rim_c = np.array([1.0, 1.0, 1.0], np.float32) * (1 - light) + glow_c * 0.85 * light
            rgb = glow_c[None, None, :] * (1 - rim[..., None]) + rim_c[None, None, :] * rim[..., None]
        elif kind == "target":                            # орган-вопрос: тёплый контур, орган виден
            a = rim * 1.0 + glow * (0.75 + 0.2 * light) + m * (0.18 + 0.22 * light)
            col = np.array(TARGET_C, np.float32)
            rim_c = (col * 0.4 + 0.6) * (1 - light) + col * 0.85 * light
            rgb = col[None, None, :] * (1 - rim[..., None]) + rim_c[None, None, :] * rim[..., None]
        else:
            fill = np.array((0.18, 0.55, 0.34) if kind == "ok" else (0.78, 0.22, 0.19), np.float32)
            a = m * 0.82 + rim * 0.5 + glow * 0.4
            rim_c = fill * 0.45 + 0.55
            rgb = fill[None, None, :] * (1 - rim[..., None]) + rim_c[None, None, :] * rim[..., None]
        a = np.clip(a, 0, 1) * vis * fade
        arr = (np.dstack([np.clip(rgb, 0, 1), a]) * 255 + 0.5).astype(np.uint8)
        return Image.fromarray(arr), (d["origin"][0] - pad, d["origin"][1] - pad)


def heartbeat(t):
    """масштаб сердца в момент t: быстрое сжатие в начале каждого удара, потом покой"""
    phase = (t % BEAT) / BEAT
    if phase >= SYSTOLE:
        return 1.0
    return 1.0 - BEAT_DEPTH * math.sin(math.pi * phase / SYSTOLE) ** 2


def breathing(t):
    """масштаб лёгких (вширь, вниз) в момент t: плавный вдох и выдох"""
    b = 0.5 - 0.5 * math.cos(2 * math.pi * t / BREATH)
    return 1.0 + BREATH_DEPTH[0] * b, 1.0 + BREATH_DEPTH[1] * b
