"""Заметки и закладки (notes.py): файл, пустые заметки, порядок закладок, испорченный файл."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from organism_atlas import notes


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name, "sub", "notes.json")
        env = mock.patch.dict(os.environ, {"ORGANISM_ATLAS_NOTES": str(self.file)})
        env.start()
        self.addCleanup(env.stop)

    def test_notes(self):
        self.assertEqual(notes.load(), {"notes": {}, "starred": []})
        notes.set_note("heart", "Четыре камеры  \n")
        self.assertEqual(notes.note("heart"), "Четыре камеры")              # хвостовые пробелы не хранятся
        notes.set_note("heart", "   ")                                      # пустая заметка удаляется
        self.assertEqual(notes.note("heart"), "")
        self.assertNotIn("heart", notes.load()["notes"])
        notes.set_note("liver", "x" * (notes.MAX_LEN + 50))
        self.assertEqual(len(notes.note("liver")), notes.MAX_LEN)

    def test_stars(self):
        self.assertTrue(notes.toggle_star("liver"))
        self.assertTrue(notes.toggle_star("femur"))
        self.assertEqual(notes.starred(), ["liver", "femur"])              # в порядке добавления
        self.assertFalse(notes.toggle_star("liver"))
        self.assertEqual(notes.starred(), ["femur"])
        self.assertTrue(notes.is_starred("femur"))

    def test_load_is_a_copy_and_sees_file_changes(self):
        """файл разбирается один раз, но load() отдаёт копию и замечает, что файл переписали"""
        notes.toggle_star("liver")
        notes.load()["starred"].append("heart")
        self.assertEqual(notes.starred(), ["liver"])
        self.file.write_text('{"notes": {"heart": "x"}}', encoding="utf-8")
        self.assertEqual(notes.load(), {"notes": {"heart": "x"}, "starred": []})

    def test_broken_file(self):
        self.file.parent.mkdir(parents=True)
        for broken in ("{", "[1, 2]", '{"notes": [1], "starred": {"a": 1}}', '{"notes": {"heart": 5}}'):
            self.file.write_text(broken, encoding="utf-8")
            self.assertEqual(notes.load(), {"notes": {}, "starred": []}, broken)


if __name__ == "__main__":
    unittest.main()
