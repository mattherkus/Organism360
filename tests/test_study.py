"""Без окна: поиск органа, экскурсии, серия дней и достижения, названия частей 3D-моделей."""

import datetime
import unittest

from organism_atlas import achievements, i18n, tours
from organism_atlas.models import has_mesh, read_mesh_model
from organism_atlas.organs import ORGANS, for_body, search

DAY = datetime.date(2026, 10, 27)


class SearchTests(unittest.TestCase):
    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE

    def test_by_name_on_any_language(self):
        keys = list(ORGANS)
        self.assertEqual(search(keys, "сердц"), ["heart"])
        self.assertEqual(search(keys, "HEART"), ["heart"])
        self.assertEqual(search(keys, "hepar"), ["liver"])               # латынь
        self.assertEqual(search(keys, "легк"), ["lungs"])                # ё = е
        self.assertEqual(search(keys, "  "), keys)                       # пустая строка - все
        self.assertEqual(search(keys, "абракадабра"), [])

    def test_by_system_name(self):
        found = search(list(ORGANS), "дыхател")
        self.assertEqual(set(found), {"lungs", "trachea"})
        i18n.set_lang("en")
        self.assertEqual(set(search(list(ORGANS), "respir")), {"lungs", "trachea"})

    def test_only_given_keys(self):
        self.assertEqual(search(for_body("male"), "матк"), [])
        self.assertEqual(search(for_body("female"), "матк"), ["uterus"])


class TourTests(unittest.TestCase):
    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE

    def test_routes_use_known_organs(self):
        for name, keys in tours.TOURS.items():
            self.assertTrue(set(keys) <= set(ORGANS), name)
            self.assertEqual(len(keys), len(set(keys)), name)

    def test_body_filters_route(self):
        self.assertEqual(tours.steps("water", "male"), ["kidneys", "bladder", "prostate"])
        self.assertEqual(tours.steps("water", "female"), ["kidneys", "bladder"])
        self.assertNotIn("ovaries", tours.steps("control", "male"))
        for body in ("male", "female"):
            self.assertEqual(tours.available(body), list(tours.TOURS))

    def test_texts_in_russian_and_english(self):
        for code in ("ru", "en"):
            data = i18n._load(code)["tours"]
            self.assertEqual(set(data), set(tours.TOURS), code)
            for name, keys in tours.TOURS.items():
                self.assertTrue(data[name]["title"] and data[name]["intro"], (code, name))
                self.assertEqual(set(data[name]["steps"]), set(keys), (code, name))

    def test_story_falls_back_to_card(self):
        self.assertEqual(tours.story("air", "brain"), i18n.organ("brain", "desc"))
        i18n.set_lang("la")                                   # у латыни экскурсий нет: текст прошлого языка
        self.assertEqual(tours.title("food"), "Путь пищи")

    def test_topics_are_systems(self):
        from organism_atlas.organs import SYSTEMS
        self.assertTrue(set(tours.TOPICS.values()) <= set(SYSTEMS))


def game(date, total=10, first_try=None, **kw):
    r = {"date": date.isoformat() + "T12:00", "mode": "find", "level": "medium", "timer": 0, "set": "all",
         "total": total, "first_try": total if first_try is None else first_try}
    r.update(kw)
    return r


class AchievementTests(unittest.TestCase):
    def data(self, results=(), cards=None):
        return {"results": list(results), "cards": cards or {}}

    def test_streak(self):
        days = [DAY - datetime.timedelta(days=i) for i in (0, 1, 2, 5, 6)]
        d = self.data(game(x) for x in days)
        self.assertEqual(achievements.streak(d, DAY), 3)
        self.assertEqual(achievements.streak(d, DAY + datetime.timedelta(days=1)), 3)   # сегодня ещё не играл
        self.assertEqual(achievements.streak(d, DAY + datetime.timedelta(days=2)), 0)
        self.assertEqual(achievements.best_streak(d), 3)
        self.assertEqual(achievements.streak(self.data(), DAY), 0)
        self.assertEqual(achievements.best_streak(self.data([{"date": "кривая"}])), 0)

    def test_conditions(self):
        self.assertEqual(achievements.earned(self.data()), [])
        d = self.data([game(DAY, total=5, first_try=4)])
        self.assertEqual(achievements.earned(d), ["first"])
        d["results"].append(game(DAY, total=10, level="hard", timer=10))
        self.assertEqual(achievements.earned(d), ["first", "perfect", "hard", "speed"])
        d["results"] += [game(DAY, mode=m) for m in ("name", "facts", "mix")]
        self.assertIn("all_modes", achievements.earned(d))
        d["results"].append(game(DAY, total=18, first_try=3, set="missed"))
        self.assertIn("marathon", achievements.earned(d))
        self.assertNotIn("fixer", achievements.earned(d))            # ошибки повторил, но с ошибками
        d["results"].append(game(DAY, total=3, set="missed"))
        self.assertIn("fixer", achievements.earned(d))

    def test_cards(self):
        cards = {"find:%s" % k: {"box": 4, "seen": 1, "wrong": 0} for k in list(ORGANS)[:18]}
        earned = achievements.earned(self.data(cards=cards))
        self.assertIn("scholar", earned)
        self.assertIn("memory", earned)
        cards = {"find:%s" % k: {"box": 1, "seen": 2, "wrong": 2} for k in ORGANS}
        self.assertEqual(achievements.earned(self.data(cards=cards)), [])

    def test_new_ones(self):
        before = self.data([game(DAY, total=5, first_try=4)])
        after = self.data(before["results"] + [game(DAY, total=5)])
        self.assertEqual(achievements.new_ones(before, after), ["perfect"])
        self.assertEqual(achievements.new_ones(after, after), [])

    def test_texts(self):
        for code in ("ru", "en"):
            ui = i18n._load(code)["ui"]
            for key in achievements.KEYS:
                self.assertTrue(ui.get("ach_" + key) and ui.get("ach_%s_desc" % key), (code, key))


class PartNameTests(unittest.TestCase):
    def test_every_part_of_multipart_models_has_a_name(self):
        """у модели из нескольких частей у каждой части есть название (иначе её нет в списке частей)"""
        for code in ("ru", "en"):
            parts = i18n._load(code)["parts"]
            for key in ORGANS:
                if not has_mesh(key):
                    continue
                groups = [g["group"] for g in read_mesh_model(key)["groups"]]
                if len(groups) > 1:
                    self.assertEqual(set(parts.get(key, {})), set(groups), (code, key))


if __name__ == "__main__":
    unittest.main()
