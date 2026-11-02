"""Кости и мышцы: реестр, маски для клика по разметке рисунка, тексты карточек."""

import unittest

import numpy as np

from organism_atlas import i18n, structures
from organism_atlas.atlas import Atlas
from organism_atlas.geometry import CX
from organism_atlas.organs import ORGANS

Z = 0.7
POINTS = {"humerus": (CX + 82, 245), "skull": (CX, 30), "femur": (CX + 40, 440), "sternum": (CX, 200),
          "ribs": (CX - 55, 226), "carpals": (CX + 103, 381), "metacarpals": (CX + 105, 408),
          "phalanges": (CX + 111, 440), "scapula": (CX + 61, 200), "patella": (CX - 27, 514),
          "tibia": (CX + 26, 600), "fibula": (CX - 35, 610), "foot": (CX + 24, 695)}
MUSCLE_POINTS = {"biceps": (CX + 82, 245), "rectus_abdominis": (CX + 12, 330), "deltoid": (CX + 84, 172),
                 "sartorius": (CX + 40, 432), "tibialis_anterior": (CX + 32, 590), "gastrocnemius": (CX - 10, 590),
                 "fibularis_longus": (CX + 41, 600), "vastus_medialis": (CX + 14, 488), "scalenes": (CX + 21, 136),
                 "intercostals": (CX + 58, 210)}


class RegistryTests(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(set(structures.STRUCTURES), set(structures.BONES) | set(structures.MUSCLES))
        self.assertEqual(set(structures.HIT_ORDER), set(structures.STRUCTURES))
        self.assertFalse(set(structures.STRUCTURES) & set(ORGANS))        # ключи не путаются с органами
        self.assertEqual(structures.keys("bone"), list(structures.BONES))

    def test_every_part_is_marked_in_the_drawing(self):
        """каждая кость и мышца отмечена в body/skeleton.py или body/muscles.py (K.part)"""
        self.assertEqual(set(structures.record()), set(structures.STRUCTURES))

    def test_texts(self):
        for code in ("ru", "en"):
            sec = i18n._load(code)["structures"]
            self.assertEqual(set(sec), set(structures.STRUCTURES), code)
            for key, d in sec.items():
                for field in ("name", "desc", "location"):
                    self.assertTrue(d.get(field), (code, key, field))
                self.assertGreaterEqual(len(d["facts"]), 2, (code, key))
        ru, en = i18n._load("ru")["structures"], i18n._load("en")["structures"]
        for key in structures.STRUCTURES:
            self.assertEqual(set(ru[key]["facts"]), set(en[key]["facts"]), key)
            fields = ("type", "parts", "joints", "muscles") if structures.kind(key) == "bone" else \
                ("origin", "insertion", "action", "nerve", "blood")
            for sec in (ru, en):
                self.assertEqual(tuple(sec[key]["details"]), fields, key)
                self.assertTrue(all(sec[key]["details"].values()), key)
            self.assertTrue(i18n._load("la")["structures"][key]["name"], key)
        self.assertEqual(i18n.name("femur"), "Бедренная кость")
        self.assertEqual(i18n.subtitle("femur"), "Femur")

    def test_links_to_bones(self):
        pieces = [k for _, k in i18n.links("Справа от позвоночника, за грудиной") if k]
        self.assertEqual(pieces, ["spine", "sternum"])


class MaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atlas = Atlas(Z)

    def test_masks_follow_the_drawing(self):
        """маски частей лежат там, где нарисован их слой тела"""
        a = self.atlas
        for key, d in a.structures().items():
            layer = a.body[structures.LAYER_OF[structures.kind(key)]]
            (ox, oy), (h, w) = d["origin"], d["hit"].shape
            inside = d["hit"] > 0.5
            self.assertTrue(inside.any(), key)
            alpha = layer[oy:oy + h, ox:ox + w, 3][inside[:layer.shape[0] - oy, :layer.shape[1] - ox]]
            self.assertGreater(np.mean(alpha > 0), 0.9, key)

    def test_structure_at(self):
        a = Atlas(Z, (self.atlas.body, self.atlas.org))
        for key, (x, y) in POINTS.items():
            self.assertEqual(a.structure_at(x * Z, y * Z), key)
        self.assertIsNone(a.structure_at(5, 5))
        a.set_layers(("skin", "muscles"))                       # кости скрыты - ловятся мышцы
        for key, (x, y) in MUSCLE_POINTS.items():
            self.assertEqual(a.structure_at(x * Z, y * Z), key)
        a.set_layers(("skin",))
        self.assertIsNone(a.structure_at(*(v * Z for v in POINTS["humerus"])))

    def test_highlight(self):
        im, _pos = self.atlas.overlay("humerus", "hover")
        self.assertGreater(np.asarray(im)[..., 3].max(), 200)
        _ax, ay = self.atlas.anchor("femur")
        self.assertGreater(ay, 350 * Z)                          # подпись - у верхнего края бедра


if __name__ == "__main__":
    unittest.main()
