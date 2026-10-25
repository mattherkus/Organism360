import math
import unittest

import numpy as np

from organism_atlas.atlas import Atlas
from organism_atlas.body.base import BODY_LAYERS
from organism_atlas.geometry import CX, H, W
from organism_atlas.organs import ORDER, ORGANS, PAINT, SYSTEMS, for_body, other_sex

Z = 0.7
# точки, которые однозначно попадают в один орган
HIT_POINTS = {"brain": (CX, 50), "heart": (CX + 20, 230), "lungs": (CX - 45, 200), "liver": (CX - 40, 280),
              "stomach": (CX + 35, 275), "kidneys": (CX - 31, 335), "intestines": (CX + 5, 330),
              "thyroid": (CX + 10, 124), "spleen": (CX + 58, 272), "pancreas": (CX + 20, 314),
              "bladder": (CX, 385), "esophagus": (CX + 13, 100), "trachea": (CX, 116), "adrenals": (CX + 28, 292),
              "appendix": (CX - 33, 399), "rectum": (CX, 422), "uterus": (CX, 348), "ovaries": (CX + 29, 355),
              "prostate": (CX, 405)}


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
        a.set_layers(BODY_LAYERS)
        self.assertTrue(np.array_equal(np.asarray(a.base), full))

    def test_other_sex_organs_hidden(self):
        """на мужской схеме нет матки и яичников, на женской - предстательной железы"""
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        for sex, gone, present in (("male", "uterus", "prostate"), ("female", "prostate", "uterus")):
            a.set_hidden(other_sex(sex))
            self.assertNotIn(gone, for_body(sex))
            self.assertIn(present, for_body(sex))
            self.assertEqual(a.organ_at(*(v * Z for v in HIT_POINTS[present])), present)
            self.assertNotEqual(a.organ_at(*(v * Z for v in HIT_POINTS[gone])), gone)

    def test_overlays(self):
        for key in ORGANS:
            for kind in ("hover", "target", "ok", "bad"):
                im, (ox, oy) = self.atlas.overlay(key, kind)
                self.assertEqual(im.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
