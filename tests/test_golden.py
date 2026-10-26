"""Сравнение с эталонами tests/golden (их делает tools/make_golden.py; подгонять эталоны под новый
результат нельзя - сначала разберитесь, почему картинка изменилась)."""

import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from organism_atlas.atlas import Atlas
from organism_atlas.body.base import BODY_LAYERS, DEFAULT_LAYERS
from organism_atlas.organs import ORDER, ORGANS

GOLDEN = Path(__file__).with_name("golden")
TOL = 1                       # уровней на канал: округление при раздельном хранении слоев


def png(path):
    return np.asarray(Image.open(path)).astype(np.int16)


def max_diff(a, b):
    return int(np.abs(np.asarray(a).astype(np.int16) - b).max())


class Golden2DTests(unittest.TestCase):
    atlases = {}

    @classmethod
    def atlas(cls, Z):
        if Z not in cls.atlases:
            cls.atlases[Z] = Atlas(Z)
        return cls.atlases[Z]

    def check_zoom(self, Z):
        d = GOLDEN / "2d" / ("z%.1f" % Z)
        a = self.atlas(Z)
        base = a.composite(visible=DEFAULT_LAYERS, organs=())
        self.assertLessEqual(max_diff(base, png(d / "base.png")), TOL, "схема без органов")
        muscles = a.composite(visible=BODY_LAYERS, organs=())
        self.assertLessEqual(max_diff(muscles, png(d / "muscles.png")), TOL, "схема без органов, с мышцами")
        self.assertLessEqual(max_diff(a.composite(), png(d / "full.png")), TOL, "схема целиком")
        origins = json.loads((d / "origins.json").read_text(encoding="utf-8"))
        for k in ORDER:
            with self.subTest(organ=k, Z=Z):
                g = d / (k + ".png")
                self.assertTrue(g.exists(), "нет эталона органа")
                self.assertEqual(list(a.org[k]["origin"]), origins[k])
                self.assertTrue(np.array_equal(a.org[k]["rgba"], png(g).astype(np.uint8)), "орган изменился")

    def test_zoom_1(self):
        self.check_zoom(1.0)

    def test_zoom_07(self):
        self.check_zoom(0.7)


class Golden3DTests(unittest.TestCase):
    def test_models(self):
        from tools.make_golden import VIEW_3D
        from organism_atlas.render3d.scene import Scene3D
        for p in sorted((GOLDEN / "3d").glob("*.png")):
            with self.subTest(organ=p.stem):
                im = Scene3D(ORGANS[p.stem]["parts"]()).render(VIEW_3D["w"], VIEW_3D["h"], VIEW_3D["az"], VIEW_3D["el"])
                self.assertEqual(max_diff(im, png(p)), 0)


if __name__ == "__main__":
    unittest.main()
