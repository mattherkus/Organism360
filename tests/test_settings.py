import os
import tempfile
import unittest
from pathlib import Path

from organism_atlas import i18n, settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name, "sub", "settings.json")
        self.old_env = os.environ.get("ORGANISM_ATLAS_SETTINGS")
        os.environ["ORGANISM_ATLAS_SETTINGS"] = str(self.file)

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("ORGANISM_ATLAS_SETTINGS", None)
        else:
            os.environ["ORGANISM_ATLAS_SETTINGS"] = self.old_env
        i18n._current = i18n._previous = i18n.BASE
        self.tmp.cleanup()

    def test_no_file_gives_defaults(self):
        self.assertEqual(settings.load(), {})

    def test_save_creates_folder_and_merges(self):
        settings.save(lang="en")
        settings.save(previous_lang="ru")
        self.assertEqual(settings.load(), {"lang": "en", "previous_lang": "ru"})

    def test_broken_file_is_ignored(self):
        self.file.parent.mkdir(parents=True)
        for text in ("{oops", "[1, 2]", ""):
            self.file.write_text(text, encoding="utf-8")
            self.assertEqual(settings.load(), {}, text)
        settings.save(lang="en")                     # и поверх испорченного файла можно записать
        self.assertEqual(settings.load(), {"lang": "en"})

    def test_restore_latin_keeps_previous_language(self):
        i18n.set_lang("en")
        i18n.set_lang("la")
        settings.save(lang=i18n.current(), previous_lang=i18n.previous())
        i18n._current = i18n._previous = i18n.BASE   # «перезапуск»
        saved = settings.load()
        i18n.restore(saved.get("lang"), saved.get("previous_lang"))
        self.assertEqual((i18n.current(), i18n.t("card_facts")), ("la", "Facts"))

    def test_restore_ignores_unknown_language(self):
        i18n.restore("xx", "en")
        self.assertEqual(i18n.current(), "ru")
        i18n.restore(None)
        self.assertEqual(i18n.current(), "ru")
        i18n.restore("en", "xx")
        self.assertEqual((i18n.current(), i18n.previous()), ("en", "ru"))


if __name__ == "__main__":
    unittest.main()
