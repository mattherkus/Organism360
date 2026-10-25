import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from organism_atlas import models
from organism_atlas.models import load_parts, load_procedural, read_model
from organism_atlas.organs import ORGANS
from organism_atlas.render3d.scene import Scene3D

# вывод старых функций parts() из Python-кода, снятый перед переносом моделей в JSON
BEFORE = json.loads((Path(__file__).parent / "fixtures" / "parts_before_json_migration.json")
                    .read_text(encoding="utf-8"))
# с тех пор жёлчный пузырь (зелёная сфера) вынесен из печени в отдельную модель - больше ничего не менялось
_GALL = [p for p in BEFORE["liver"] if p["k"] == "e" and p["color"] == "#4f8a3c"]
BEFORE["liver"] = [p for p in BEFORE["liver"] if p not in _GALL]
BEFORE["gallbladder"] = _GALL
TEXTURES = {"smooth", "lung", "gyri", "folia", "liver", "muscle", "gland", "bowel"}
COMMON = {"type", "color", "texture", "gloss"}
FIELDS = {"ellipsoid": COMMON | {"center", "radii"}, "tube": COMMON | {"path", "radius"}}
OPTIONAL = {"rings", "hause"}
VIEWS = [(-62, 18, 1.0, 2, 1), (30, -40, 1.6, 3, 1), (150, 70, 0.6, 1, 2)]   # az, el, zoom, ss, step


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_point(v):
    return isinstance(v, list) and len(v) == 3 and all(is_num(x) for x in v)


class ModelFilesTests(unittest.TestCase):
    """схема файлов models/*.json: ловит ошибки при ручной правке"""

    def test_every_organ_has_a_model_file_and_no_extra_files(self):
        files = {p.stem for p in Path(models.__file__).with_name("models").glob("*.json")}
        self.assertEqual(files, set(ORGANS))

    def test_schema(self):
        for key in ORGANS:
            data = read_model(key)
            self.assertEqual(set(data), {"parts"}, key)
            self.assertIsInstance(data["parts"], list, key)
            self.assertTrue(data["parts"], key)
            for i, p in enumerate(data["parts"]):
                where = "%s #%d" % (key, i)
                self.assertIn(p.get("type"), FIELDS, where)
                need = FIELDS[p["type"]]
                self.assertEqual(need - set(p), set(), where + ": нет полей")
                self.assertEqual(set(p) - need - OPTIONAL, set(), where + ": лишние поля")
                self.assertRegex(p["color"], re.compile(r"^#[0-9a-f]{6}$"), where)
                self.assertIn(p["texture"], TEXTURES, where)
                self.assertTrue(is_num(p["gloss"]) and 0 <= p["gloss"] <= 1, where)
                for f in OPTIONAL & set(p):
                    self.assertTrue(is_num(p[f]) and p[f] >= 0, where + " " + f)
                if p["type"] == "ellipsoid":
                    self.assertTrue(is_point(p["center"]), where)
                    self.assertTrue(is_point(p["radii"]), where)
                    self.assertTrue(all(r > 0 for r in p["radii"]), where)
                else:
                    self.assertIsInstance(p["path"], list, where)
                    self.assertGreaterEqual(len(p["path"]), 2, where)
                    self.assertTrue(all(is_point(pt) for pt in p["path"]), where)
                    rad = p["radius"] if isinstance(p["radius"], list) else [p["radius"]]
                    self.assertTrue(rad and all(is_num(r) and r > 0 for r in rad), where)

    def test_broken_file_names_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "models").mkdir()
            Path(tmp, "models", "xx.json").write_text('{"parts": [\n  {"type": "tube",}\n]}', encoding="utf-8")
            with mock.patch.object(models.resources, "files", return_value=Path(tmp)):
                with self.assertRaisesRegex(ValueError, r"models/xx\.json, строка 2"):
                    read_model("xx")


class SameAsBeforeTests(unittest.TestCase):
    """перенос процедурных моделей в JSON их не изменил (они остаются резервом к анатомическим).
    Органы, добавленные позже, в фикстуре не записаны"""

    def test_same_number_of_parts(self):
        self.assertLessEqual(set(BEFORE), set(ORGANS))
        for key in BEFORE:
            self.assertEqual(len(load_procedural(key)), len(BEFORE[key]), key)

    def test_same_primitives(self):
        for key in BEFORE:
            self.assertEqual(load_procedural(key), BEFORE[key], key)

    def test_pixel_identical_render(self):
        for key in BEFORE:
            for az, el, zoom, ss, step in VIEWS:
                old = Scene3D(BEFORE[key]).render(160, 120, az, el, zoom=zoom, ss=ss, step=step)
                new = Scene3D(load_procedural(key)).render(160, 120, az, el, zoom=zoom, ss=ss, step=step)
                self.assertTrue(np.array_equal(np.asarray(old), np.asarray(new)), (key, az, el))


class LoadPartsTests(unittest.TestCase):
    def test_registry_uses_load_parts(self):
        sig = lambda parts: [(p["k"], p["color"], p["tex"]) for p in parts]
        for key, o in ORGANS.items():
            self.assertEqual(sig(o["parts"]()), sig(load_parts(key)), key)

    def test_file_read_once_and_copies_are_independent(self):
        models._cache.clear()
        with mock.patch.object(models, "read_model", wraps=models.read_model) as rd:
            a = load_procedural("heart")
            b = load_procedural("heart")
        self.assertEqual(rd.call_count, 1)
        a[0]["color"] = "#000000"
        a[0]["c"][0] = 99
        self.assertEqual(load_procedural("heart"), b)
        self.assertNotEqual(b[0]["color"], "#000000")


if __name__ == "__main__":
    unittest.main()
