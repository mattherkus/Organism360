"""Схема тела по слоям: слои тела, органы, маски попадания, подсветка. Не зависит от Tk.

Стек снизу вверх: фон темы со свечением вокруг тела, кожа (skin), мышцы (muscles), скелет (skeleton), вены (veins),
артерии (arteries), растворение ног у нижнего края (fade), затем органы в порядке ORDER.
Слои хранятся отдельно (uint8, RGBA с прямой альфой), поэтому скрыть слой или орган можно без
перерисовки остальных; composite() собирает картинку целиком.
"""

import math

import numpy as np
from PIL import Image

from . import atlas_cache
from .body.base import BG_HI, BODY_LAYERS, DEFAULT_LAYERS, background, build_layers, compose, glow_weight, over
from .config import BG
from .config import TARGET_C
from .organs import ORDER, PAINT
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
        self._bg = (BG, BG_HI)           # цвета фона (тема)
        self._base = None
        self._show = {}                  # заготовки для base при текущем фоне: кожа с фоном, растворение
        self._glow = None
        self._cache = {}
        self._layers = {}
        self._under = None               # (прямоугольник, подложка анимации): всё, что под лёгкими

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
        for k in ORDER:
            if k in organs:
                d = self.org[k]
                (ox, oy), (h, w) = d["origin"], d["rgba"].shape[:2]
                over(out[oy:oy + h, ox:ox + w], d["rgba"].astype(np.float32) / 255)
        return Image.fromarray(to_u8(out))

    def _assemble(self, organs):
        """фон темы, видимые слои тела и органы organs (по порядку ORDER) средствами Pillow"""
        skin = "skin" in self.visible
        if skin not in self._show:
            # свечение и кромка кожи не выражаются прямой альфой, поэтому кожа - вместе с фоном
            out = compose(self.body, self._back(*self._bg), ("skin",) if skin else (), fade=False)
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
                im, pos = self.layer(k)
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
        self.base                                        # пересобрать вид, если он сменился
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
            im, (x, y) = self.layer(k)
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
            # обратное отображение: точка куска -> точка слоя органа (с долями пикселя: без дрожания)
            data = (1 / sx, 0, px - x + (x0 - px) / sx, 0, 1 / sy, py - y + (y0 - py) / sy)
            moved = im.convert("RGBa").transform(out.size, Image.AFFINE, data, Image.BILINEAR).convert("RGBA")
            out.paste(moved, (0, 0), moved)
        return out, (x0, y0)

    def set_background(self, bg, hi):
        """подставить фон схемы (цвета #rrggbb из темы); возвращает новую self.base"""
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

    @classmethod
    def cached(cls, Z, cache_dir=atlas_cache.CACHE_DIR):
        """схема из кэша на диске, а если её там нет - нарисовать и сохранить"""
        Z = atlas_cache.zoom_key(Z)
        data = atlas_cache.load(Z, ORDER, cache_dir)
        if data is not None:
            return cls(Z, data)
        atlas = cls(Z)
        atlas_cache.save(Z, atlas.body, atlas.org, cache_dir)
        return atlas

    # --- видимость органов
    def set_hidden(self, organs):
        """какие органы скрыты (не рисуются и не ловят клик); подсветка зависит от того, кто кого закрывает,
        поэтому её кэш сбрасывается"""
        organs = frozenset(organs)
        if organs != self.hidden:
            self.hidden = organs
            self._cache.clear()
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
            if 0 <= xi < w and 0 <= yi < h and d["hit"][yi, xi] > 0.5:
                return k
        return None

    def _cover(self, key, pad=0):
        """насколько орган перекрыт видимыми органами, лежащими выше него; pad - запас вокруг рамки органа"""
        d = self.org[key]
        x0, y0 = d["origin"][0] - pad, d["origin"][1] - pad
        h, w = d["hit"].shape[0] + 2 * pad, d["hit"].shape[1] + 2 * pad
        cov = np.zeros((h, w), np.float32)
        for k in ORDER[ORDER.index(key) + 1:]:
            if k in self.hidden:
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

    def overlay(self, key, kind):
        """RGBA-картинка подсветки и её положение. kind: hover / target / ok / bad"""
        if (key, kind) not in self._cache:
            self._cache[(key, kind)] = self._make(key, kind)
        return self._cache[(key, kind)]

    def _lum(self, key):
        """средняя яркость органа (0..1) по его видимым пикселям"""
        d = self.org[key]
        m = d["hit"] > 0.5
        if not m.any():
            return 0.0
        return float((d["rgba"][..., :3][m].astype(np.float32) / 255 @ np.array([0.2126, 0.7152, 0.0722])).mean())

    def _make(self, key, kind):
        Z = self.Z
        d = self.org[key]
        # рамка органа - вплотную к нему: свечение и контур снаружи не поместились бы, а у узкого органа
        # (трахея) их съедало бы и гашение у края. Поэтому подсветка - на рамке с запасом pad со всех сторон
        pad = int(np.ceil(HALO * Z))
        m = np.pad(d["hit"], pad)
        h, w = m.shape
        vis = 1.0 - np.clip(self._cover(key, pad), 0, 1)
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
