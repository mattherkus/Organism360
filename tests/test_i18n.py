import datetime
import re
import string
import tempfile
import unittest
from pathlib import Path

from organism_atlas import i18n
from organism_atlas.organs import ORGANS, fact_of_day

FIELDS = ("name", "desc", "location", "facts", "diseases", "daily")
PKG = Path(i18n.__file__).parent


def placeholders(s):
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


class LangFilesTests(unittest.TestCase):
    """проверки, которые ловят ошибки при ручной правке lang/*.json"""

    def test_russian_is_complete(self):
        ru = i18n._load("ru")
        self.assertEqual(set(ru["organs"]), set(ORGANS))
        for key, o in ru["organs"].items():
            for field in FIELDS:
                self.assertTrue(o.get(field), (key, field))

    def test_every_ui_key_used_in_code_exists(self):
        used = set()
        for p in PKG.rglob("*.py"):
            used |= set(re.findall(r'\bt\("(\w+)"[,)]', p.read_text(encoding="utf-8")))
        # ключи, которые код собирает из частей: "mode_" + режим, "level_" + сложность и т. п.
        from organism_atlas.quiz import LEVELS, MODES
        used |= {"mode_" + m for m in ("study",) + MODES} | {"setup_desc_" + m for m in MODES}
        used |= {"level_" + v for v in LEVELS} | {"level_hint_" + v for v in LEVELS}
        used |= {"set_" + q for q in ("all", "missed", "due")}
        self.assertFalse(used - set(i18n._load("ru")["ui"]))

    def test_english_matches_russian(self):
        ru, en = i18n._load("ru"), i18n._load("en")
        self.assertEqual(set(en["ui"]), set(ru["ui"]))
        for k, s in ru["ui"].items():
            self.assertEqual(placeholders(en["ui"][k]), placeholders(s), k)
        self.assertEqual(set(en["organs"]), set(ORGANS))
        for key, o in en["organs"].items():
            self.assertEqual(set(o) - {"reviewed"}, set(FIELDS), key)

    def test_reviewed_flag(self):
        """reviewed - отметка «факты проверены специалистом»; ставит только специалист"""
        for code in ("ru", "en"):
            for key, o in i18n._load(code)["organs"].items():
                if "reviewed" in o:
                    self.assertIs(o["reviewed"], False, (code, key))

    def test_latin_names_for_all_organs(self):
        la = i18n._load("la")
        for key in ORGANS:
            self.assertTrue(la["organs"][key]["name"], key)

    def test_buttons_order(self):
        self.assertEqual(i18n.available()[:3], ["ru", "en", "la"])


class SwitchTests(unittest.TestCase):
    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE

    def test_switch_and_fallback(self):
        self.assertEqual(i18n.name("heart"), "Сердце")
        self.assertEqual(i18n.subtitle("heart"), "Cor")
        i18n.set_lang("en")
        self.assertEqual(i18n.name("heart"), "Heart")
        self.assertEqual(i18n.t("progress", n=1, total=11, errors=0), "Question 1 of 11  ·  Mistakes: 0")
        i18n.set_lang("la")                         # латынь: только названия, остальное с прошлого языка
        self.assertEqual(i18n.name("heart"), "Cor")
        self.assertEqual(i18n.subtitle("heart"), "Heart")
        self.assertEqual(i18n.organ("heart", "facts"), i18n._load("en")["organs"]["heart"]["facts"])
        self.assertEqual(i18n.t("card_facts"), "Facts")
        i18n.set_lang("ru")
        i18n.set_lang("la")
        self.assertEqual(i18n.t("card_facts"), "Факты")

    def test_missing_key_is_visible(self):
        self.assertEqual(i18n.t("no_such_key"), "no_such_key")

    def test_fact_of_day(self):
        d = datetime.date(2026, 10, 24)
        pool = i18n.organ("heart", "daily")
        facts = [fact_of_day("heart", d + datetime.timedelta(days=i)) for i in range(len(pool))]
        self.assertCountEqual(facts, pool)           # за len(pool) дней покажет каждый факт по разу
        self.assertEqual(fact_of_day("heart", d), fact_of_day("heart", d))


class BrokenFileTests(unittest.TestCase):
    def test_syntax_error_names_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "xx.json").write_text('{\n  "ui": {\n    "a": "b",\n  }\n}', encoding="utf-8")
            old = i18n.LANG_DIR
            i18n.LANG_DIR = Path(tmp)
            try:
                with self.assertRaisesRegex(ValueError, r"xx\.json, строка 3"):
                    i18n._load("xx")
            finally:
                i18n.LANG_DIR = old
                i18n._cache.pop("xx", None)


if __name__ == "__main__":
    unittest.main()
