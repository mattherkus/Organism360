import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from organism_atlas import jsonstore, notes, progress


class JsonStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_write_and_decode(self):
        p = self.dir / "sub" / "x.json"
        self.assertTrue(jsonstore.write(p, {"a": "ё"}))
        self.assertEqual(jsonstore.decode(jsonstore.read_bytes(p)), {"a": "ё"})
        self.assertEqual(sorted(f.name for f in p.parent.iterdir()), ["x.json"])      # .tmp не остался
        self.assertEqual(jsonstore.decode(None), {})

    def test_busy_file_is_retried(self):
        """на Windows файл ненадолго держит антивирус: os.replace пробуется ещё раз"""
        p = self.dir / "x.json"
        real = os.replace
        calls = []

        def busy_once(a, b):
            calls.append(a)
            if len(calls) == 1:
                raise PermissionError("busy")
            return real(a, b)

        with mock.patch.object(jsonstore.os, "replace", busy_once), mock.patch.object(jsonstore.time, "sleep"):
            self.assertTrue(jsonstore.write(p, {"a": 1}))
        self.assertEqual(len(calls), 2)
        with mock.patch.object(jsonstore.os, "replace", side_effect=PermissionError), \
                mock.patch.object(jsonstore.time, "sleep"):
            self.assertFalse(jsonstore.write(p, {"a": 2}))             # так и не освободился - не падаем
        self.assertEqual(jsonstore.decode(p.read_bytes()), {"a": 1})
        self.assertFalse((self.dir / "x.json.tmp").exists())

    def test_unwritable_place(self):
        blocker = self.dir / "file"
        blocker.write_text("x")
        self.assertFalse(jsonstore.write(blocker / "x.json", {}))

    def test_broken_progress_is_kept_aside(self):
        """испорченный progress.json: история пустая, но сам файл не пропадает при следующей записи"""
        p = self.dir / "p.json"
        p.write_bytes(b'{"results": [ {"mode": "find"')
        with mock.patch.dict(os.environ, {"ORGANISM_ATLAS_PROGRESS": str(p)}):
            self.assertEqual(progress.load()["results"], [])
            progress.mark("find", "heart", True)
        self.assertEqual((self.dir / "p.json.bad").read_bytes(), b'{"results": [ {"mode": "find"')
        self.assertIn("find:heart", jsonstore.decode(p.read_bytes())["cards"])

    def test_zeroed_notes_are_not_kept(self):
        """файл из одних нулей (питание пропало при записи) спасать нечего: копии нет"""
        p = self.dir / "n.json"
        p.write_bytes(bytes(32))
        with mock.patch.dict(os.environ, {"ORGANISM_ATLAS_NOTES": str(p)}):
            self.assertEqual(notes.load(), {"notes": {}, "starred": []})
        self.assertFalse((self.dir / "n.json.bad").exists())


if __name__ == "__main__":
    unittest.main()
