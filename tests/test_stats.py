"""Статистика и карта знаний по progress.json - без окна."""

import unittest

import numpy as np

from organism_atlas import stats
from organism_atlas.atlas import Atlas
from organism_atlas.geometry import CX


def card(box, seen, wrong):
    return {"box": box, "seen": seen, "wrong": wrong}


DATA = {
    "results": [
        {"date": "2026-11-01T10:00", "mode": "find", "total": 10, "first_try": 8, "seconds": 60},
        {"date": "2026-11-02T10:00", "mode": "find", "total": 10, "first_try": 6, "seconds": 90},
        {"date": "2026-11-02T11:00", "mode": "order", "total": 4, "first_try": 4, "seconds": 30},
    ],
    "cards": {
        "find:heart": card(4, 4, 0), "name:heart": card(1, 1, 1),    # дошло до коробки 4 - выучено
        "find:liver": card(1, 3, 2),                                 # одни ошибки - слабо
        "mix:lungs": card(2, 2, 0),                                  # учу
        "body:femur": card(5, 5, 0), "order:food": card(5, 5, 0),     # не органы - не считаются
    },
}


class StatsTests(unittest.TestCase):
    def test_summary(self):
        s = stats.summary(DATA)
        self.assertEqual((s["games"], s["questions"], s["right"], s["percent"], s["minutes"]), (3, 24, 18, 75, 3))

    def test_by_mode_and_system(self):
        self.assertEqual(stats.by_mode(DATA), [("find", 2, 20, 14), ("order", 1, 4, 4)])
        systems = dict((s, (seen, ok)) for s, seen, ok in stats.by_system(DATA, ["heart", "liver", "lungs"]))
        self.assertEqual(systems["circulatory"], (5, 4))
        self.assertEqual(systems["digestive"], (3, 1))
        self.assertEqual(systems["respiratory"], (2, 2))

    def test_mastery_and_weak(self):
        self.assertEqual(stats.mastery(DATA), {"heart": "learned", "liver": "weak", "lungs": "learning"})
        self.assertEqual(stats.weakest(DATA, ["heart", "liver", "lungs"]), [("liver", 3, 1), ("heart", 5, 4)])
        self.assertEqual(stats.trend(DATA), [("2026-11-01T10:00", "find", 80), ("2026-11-02T10:00", "find", 60),
                                             ("2026-11-02T11:00", "order", 100)])

    def test_empty(self):
        empty = {"results": [], "cards": {}}
        self.assertIsNone(stats.summary(empty)["percent"])
        self.assertEqual((stats.by_mode(empty), stats.mastery(empty), stats.trend(empty)), ([], {}, []))


class TintTests(unittest.TestCase):
    def test_tint_respects_cover_and_hidden(self):
        """тонировка - по видимому рисунку: орган без цвета закрывает тонировку того, что под ним"""
        Z = 0.7
        a = Atlas(Z)
        red = (1.0, 0.0, 0.0)
        im = np.asarray(a.tint({"heart": red, "lungs": (0.0, 1.0, 0.0)}))
        hx, hy = int((CX + 20) * Z), int(230 * Z)                     # сердце
        lx, ly = int((CX - 45) * Z), int(200 * Z)                     # лёгкое
        self.assertGreater(im[hy, hx, 3], 100)
        self.assertGreater(im[hy, hx, 0], 200)
        self.assertGreater(im[ly, lx, 1], 200)
        im = np.asarray(a.tint({"liver": red}))
        sx, sy = int((CX - 28) * Z), int(243 * Z)                     # лёгкое поверх печени - без цвета
        self.assertEqual(a.organ_at(sx, sy), "lungs")
        self.assertLess(im[sy, sx, 3], 30)
        self.assertGreater(im[int(280 * Z), int((CX - 40) * Z), 3], 100)   # открытая часть печени - в цвете
        a.set_hidden({"heart"})
        self.assertLess(np.asarray(a.tint({"heart": red}))[hy, hx, 3], 10)


if __name__ == "__main__":
    unittest.main()
