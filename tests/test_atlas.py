import math
import unittest

import numpy as np

from organism_atlas.atlas import Atlas
from organism_atlas.body.base import BODY_LAYERS, DEFAULT_LAYERS
from organism_atlas.geometry import CX, H, W
from organism_atlas.organs import ORDER, ORGANS, PAINT, SYSTEMS, for_body, other_sex

Z = 0.7
# точки, которые однозначно попадают в один орган
HIT_POINTS = {"brain": (CX, 50), "heart": (CX + 20, 230), "lungs": (CX - 45, 200), "liver": (CX - 40, 280),
              "stomach": (CX + 35, 275), "kidneys": (CX - 31, 335), "intestines": (CX + 5, 330),
              "thyroid": (CX + 10, 124), "spleen": (CX + 58, 272), "pancreas": (CX + 20, 314),
              "bladder": (CX, 385), "esophagus": (CX + 13, 100), "trachea": (CX, 116), "adrenals": (CX + 28, 292),
              "appendix": (CX - 33, 399), "rectum": (CX, 422), "uterus": (CX, 348), "ovaries": (CX + 29, 355),
              "prostate": (CX, 405), "aorta": (CX + 28, 172), "vena_cava": (CX - 13, 175), "thymus": (CX + 5, 170),
              "pituitary": (CX, 66.5), "diaphragm": (CX - 63.5, 259), "lymph_nodes": (CX + 61, 169),
              "spinal_cord": (CX + 82, 214)}


class RegistryTests(unittest.TestCase):
    def test_registry_is_consistent(self):
        self.assertEqual(set(ORGANS), set(ORDER))
        self.assertEqual(set(PAINT), set(ORDER))
        for key, o in ORGANS.items():
            for field in ("color", "parts", "systems", "sex"):
                self.assertIn(field, o, key)
            self.assertTrue(o["systems"] and set(o["systems"]) <= set(SYSTEMS), key)
            self.assertIn(o["sex"], (None, "female", "male"), key)


class AtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atlas = Atlas(Z)

    def test_behind(self):
        """нижняя полая вена лежит выше печени в стопке, но за ней: печень её закрывает и ловит клик,
        а скрыли печень - видна и ловит клик вена"""
        from organism_atlas.organs import BEHIND
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        x, y = (CX - 6) * Z, 275 * Z
        self.assertIn("liver", BEHIND["vena_cava"])
        self.assertGreater(ORDER.index("vena_cava"), ORDER.index("liver"))
        self.assertEqual(a.organ_at(x, y), "liver")
        d = a.org["vena_cava"]
        px, py = int(x) - d["origin"][0], int(y) - d["origin"][1]
        self.assertGreater(d["rgba"][py, px, 3], 200)                    # вена там нарисована...
        self.assertLess(np.asarray(a.shown("vena_cava")[0])[py, px, 3], 10)   # ...но вырезана под печенью
        self.assertEqual(a.composite().getpixel((int(x), int(y))),
                         a.composite(organs=[k for k in ORDER if k != "vena_cava"]).getpixel((int(x), int(y))))
        # печень не закрыта веной (вена выше, но за ней): подсветка печени в этом месте видна
        cov = a._cover("liver")
        lx, ly = int(x) - a.org["liver"]["origin"][0], int(y) - a.org["liver"]["origin"][1]
        self.assertLess(cov[ly, lx], 0.1)
        a.set_hidden({"liver"})
        self.assertEqual(a.organ_at(x, y), "vena_cava")
        self.assertGreater(np.asarray(a.shown("vena_cava")[0])[py, px, 3], 200)

    def test_base_image_size(self):
        self.assertEqual(self.atlas.base.size, (math.ceil(W * Z), math.ceil(H * Z)))

    def test_organ_at(self):
        for key, (x, y) in HIT_POINTS.items():
            self.assertEqual(self.atlas.organ_at(x * Z, y * Z), key)
        self.assertIsNone(self.atlas.organ_at(10, 20))

    def test_background_follows_theme(self):
        """фон схемы меняется по теме, а сам рисунок органов остаётся прежним"""
        heart = tuple(int(v * Z) for v in HIT_POINTS["heart"])
        try:
            light = self.atlas.set_background("#ffffff", "#ffffff")
            self.assertEqual(light.getpixel((2, 2)), (255, 255, 255))      # угол - чистый фон
            organ = light.getpixel(heart)
            dark = self.atlas.set_background("#000000", "#000000")
            self.assertEqual(dark.getpixel((2, 2)), (0, 0, 0))
            self.assertEqual(dark.getpixel(heart), organ)                  # орган фон не просвечивает
        finally:
            self.atlas.set_background("#0e1a22", "#1a3547")

    def test_same_background_keeps_image(self):
        """тот же фон ещё раз - картинка не пересобирается (его ставят и поток сборки схемы, и окно)"""
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        base = a.set_background("#0e1a22", "#1a3547")
        self.assertIs(a.set_background("#0e1a22", "#1a3547"), base)
        self.assertIsNot(a.set_background("#000000", "#000000"), base)

    def test_warm_overlays(self):
        """подсветка, посчитанная заранее в фоне, та же, что по запросу; если органы за это время скрыли
        или показали, посчитанная заранее не берётся"""
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        a.set_hidden(other_sex("female"))
        a.warm().join()
        a.overlay("heart", "hover")                      # забирает всё, что посчитано заранее
        self.assertEqual({k for k, _kind in a._cache}, set(for_body("female")))
        for k in ("lungs", "trachea"):
            self.assertTrue(np.array_equal(np.asarray(a.overlay(k, "hover")[0]), np.asarray(a._make(k, "hover")[0])))
        b = Atlas(Z, (self.atlas.body, self.atlas.org))
        b.warm().join()
        b.set_hidden({"lungs"})                           # печень больше не закрыта лёгкими
        liver = b.overlay("liver", "hover")[0]
        self.assertEqual(set(b._cache), {("liver", "hover")})
        self.assertTrue(np.array_equal(np.asarray(liver), np.asarray(b._make("liver", "hover")[0])))

    def test_layers_and_hidden_organs(self):
        """скрытый слой или орган пропадает с картинки, а скрытый орган ещё и не ловит клик"""
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        full = np.asarray(a.base).copy()
        x, y = (int(v * Z) for v in HIT_POINTS["heart"])
        a.set_hidden({"heart"})
        self.assertNotEqual(a.organ_at(x, y), "heart")
        self.assertFalse(np.array_equal(np.asarray(a.base)[y, x], full[y, x]))
        a.set_hidden(())
        self.assertTrue(np.array_equal(np.asarray(a.base), full))
        a.set_layers(("skin", "veins", "arteries"))
        no_bones = np.asarray(a.base)
        self.assertFalse(np.array_equal(no_bones, full))
        self.assertEqual(a.visible, ("skin", "veins", "arteries"))
        a.set_layers(DEFAULT_LAYERS)
        self.assertTrue(np.array_equal(np.asarray(a.base), full))
        a.set_layers(BODY_LAYERS)                          # мышцы по умолчанию скрыты: с ними картинка другая
        self.assertEqual(a.visible, BODY_LAYERS)
        self.assertFalse(np.array_equal(np.asarray(a.base), full))

    def test_other_sex_organs_hidden(self):
        """на мужской схеме нет матки и яичников, на женской - предстательной железы"""
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        for sex, gone, present in (("male", "uterus", "prostate"), ("female", "prostate", "uterus")):
            a.set_hidden(other_sex(sex))
            self.assertNotIn(gone, for_body(sex))
            self.assertIn(present, for_body(sex))
            self.assertEqual(a.organ_at(*(v * Z for v in HIT_POINTS[present])), present)
            self.assertNotEqual(a.organ_at(*(v * Z for v in HIT_POINTS[gone])), gone)

    def test_animation_frames(self):
        """в покое кусок анимации совпадает со схемой; на ударе сердце меньше, на вдохе лёгкие больше"""
        from organism_atlas.atlas import BEAT, BREATH, breathing, heartbeat
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        im, (x, y) = a.anim_frame(0.0)
        x0, y0, x1, y1 = a.anim_box()
        self.assertEqual((x, y, x + im.width, y + im.height), (x0, y0, x1, y1))
        base = np.asarray(a.base.crop((x0, y0, x1, y1))).astype(int)
        self.assertLessEqual(np.abs(np.asarray(im).astype(int) - base).max(), 2)
        for t in (BEAT * 0.16, BREATH / 2):
            self.assertGreater(np.abs(np.asarray(a.anim_frame(t)[0]).astype(int) - base).max(), 40)
        self.assertLess(heartbeat(BEAT * 0.16), 1)
        self.assertEqual(heartbeat(BEAT * 0.8), 1)
        self.assertGreater(breathing(BREATH / 2)[1], breathing(0)[1])
        for k in ("heart", "lungs"):                     # прямоугольник анимации накрывает оба органа
            d = a.org[k]
            ox, oy = d["origin"]
            h, w = d["rgba"].shape[:2]
            self.assertTrue(x0 <= ox and y0 <= oy and ox + w <= x1 and oy + h <= y1, k)
        a.set_hidden({"heart", "lungs"})
        self.assertIsNone(a.anim_frame(0.0))
        a.set_hidden(set())
        # сердце и лёгкие растягиваются вокруг своей точки опоры - так же, как общим аффинным преобразованием
        # слоя целиком (кадр считает только прямоугольник органа и через resize - так быстрее). resize при
        # сжатии сердца чуть сглаживает его край, поэтому сравниваем не до уровня, а в среднем: сдвиг органа
        # на пиксель дал бы разницу в несколько уровней в среднем
        from PIL import Image
        from organism_atlas.atlas import HEART_BASE
        for t in (BEAT * 0.16, BREATH / 2, BREATH / 2 + BEAT * 0.1):
            im, (x0, y0) = a.anim_frame(t)
            ref = a._under[1].copy()
            scale = {"heart": (heartbeat(t),) * 2, "lungs": breathing(t)}
            for k in ORDER[ORDER.index("lungs"):]:
                layer, (x, y) = a.shown(k)          # орган из BEHIND - с вырезом под органами перед ним
                w, h = layer.size
                if k not in scale:
                    ref.paste(layer, (x - x0, y - y0), layer)
                    continue
                sx, sy = scale[k]
                px, py = x + w / 2, y + (h * HEART_BASE if k == "heart" else 0)
                data = (1 / sx, 0, px - x + (x0 - px) / sx, 0, 1 / sy, py - y + (y0 - py) / sy)
                layer = layer.convert("RGBa").transform(ref.size, Image.AFFINE, data, Image.BILINEAR).convert("RGBA")
                ref.paste(layer, (0, 0), layer)
            diff = np.abs(np.asarray(im).astype(int) - np.asarray(ref).astype(int))
            self.assertLessEqual(np.percentile(diff, 99), 3, t)
            self.assertLess(diff.mean(), 0.5, t)
        a.set_hidden({"lungs"})
        im, pos = a.anim_frame(0.0)
        self.assertLess(im.width, x1 - x0)                # остался только прямоугольник сердца

    def test_overlays(self):
        for key in ORGANS:
            for kind in ("hover", "target", "ok", "bad"):
                im, (ox, oy) = self.atlas.overlay(key, kind)
                self.assertEqual(im.mode, "RGBA")

    def test_light_narrow_organ_highlight(self):
        """трахея светлая и узкая: подсветка на рамке с запасом (свечение не обрезано краем рамки органа)
        и заметно закрашивает сам орган"""
        from organism_atlas.atlas import HALO
        d = self.atlas.org["trachea"]
        im, (ox, oy) = self.atlas.overlay("trachea", "target")
        a = np.asarray(im)[..., 3].astype(np.float32) / 255
        x0, y0 = d["origin"][0] - ox, d["origin"][1] - oy
        h, w = d["hit"].shape
        self.assertGreaterEqual(min(x0, y0), HALO * Z)
        self.assertEqual(im.size, (w + 2 * x0, h + 2 * y0))
        open_ = (d["hit"] > 0.5) & (self.atlas._cover("trachea") < 0.1)        # видимая часть трахеи
        self.assertGreater(a[y0:y0 + h, x0:x0 + w][open_].mean(), 0.3)


if __name__ == "__main__":
    unittest.main()
