"""Схема тела по слоям: слои тела, органы, маски попадания, подсветка. Не зависит от Tk.

Стек снизу вверх: фон темы со свечением вокруг тела, кожа (skin), скелет (skeleton), вены (veins),
артерии (arteries), растворение ног у нижнего края (fade), затем органы в порядке ORDER.
Слои хранятся отдельно (uint8, RGBA с прямой альфой), поэтому скрыть слой или орган можно без
перерисовки остальных; composite() собирает картинку целиком.
"""

import numpy as np
from PIL import Image

from . import atlas_cache
from .body.base import BG_HI, BODY_LAYERS, background, build_layers, compose, glow_weight, over
from .config import BG
from .config import TARGET_C
from .organs import ORDER, PAINT
from .render2d.noise import gblur

BODY_ARRAYS = ("glow", "skin", "skin_hi", "skeleton", "veins", "arteries", "fade")
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
        self.visible = BODY_LAYERS       # видимые слои тела
        self._bg = (BG, BG_HI)           # цвета фона (тема)
        self._base = None
        self._show = {}                  # заготовки для base при текущем фоне: кожа с фоном, растворение
        self._glow = None
        self._cache = {}
        self._layers = {}

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

    def composite(self, bg=BG, hi=BG_HI, visible=BODY_LAYERS, skin_opacity=1.0, organs=None):
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

    @property
    def base(self):
        """готовая картинка Pillow для показа: фон темы, видимые слои тела и нескрытые органы.
        Собирается быстро (на каждый щелчок в панели слоёв): кожа с фоном считается в numpy один раз,
        кости, сосуды, растворение ног и органы кладутся средствами Pillow. От composite() отличается
        только округлением (на 1-2 уровня из 255)"""
        if self._base is None:
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
                if k not in self.hidden:
                    im, pos = self.layer(k)
                    out.paste(im, pos, im)
            self._base = out
        return self._base

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
