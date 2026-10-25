import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from organism_atlas import atlas, atlas_cache
from organism_atlas.atlas import Atlas
from organism_atlas.organs import ORDER

Z = 0.7


def no_build(*_a, **_kw):
    raise AssertionError("схема должна была прочитаться из кэша, а не рисоваться")


class AtlasCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = atlas.build_atlas(Z)          # рисуем один раз; дальше подставляем готовое
        cls.fresh = Atlas(Z)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        patcher = mock.patch.object(atlas, "build_atlas", return_value=self.raw)
        self.build = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        return sorted(p.name for p in self.dir.iterdir())

    def assertSameAtlas(self, a, b):
        self.assertTrue(np.array_equal(np.asarray(a.base), np.asarray(b.base)))
        for k in ORDER:
            self.assertEqual(a.org[k]["origin"], b.org[k]["origin"], k)
            self.assertTrue(np.array_equal(a.org[k]["hit"], b.org[k]["hit"]), k)
            self.assertEqual(a.org[k]["hit"].dtype, b.org[k]["hit"].dtype, k)
            self.assertTrue(np.array_equal(a.org[k]["rgba"], b.org[k]["rgba"]), k)
        for name in a.body:
            self.assertTrue(np.array_equal(a.body[name], b.body[name]), name)

    def test_second_load_reads_cache_and_matches_fresh_render(self):
        first = Atlas.cached(Z, self.dir)
        self.assertEqual(len(self.files()), 1)
        with mock.patch.object(atlas, "build_atlas", no_build):
            second = Atlas.cached(Z, self.dir)
        self.assertSameAtlas(second, self.fresh)
        self.assertSameAtlas(first, self.fresh)
        im1, pos1 = second.overlay("heart", "hover")
        im2, pos2 = self.fresh.overlay("heart", "hover")
        self.assertEqual(pos1, pos2)
        self.assertTrue(np.array_equal(np.asarray(im1), np.asarray(im2)))

    def test_other_zoom_is_separate_entry(self):
        Atlas.cached(Z, self.dir)
        Atlas.cached(0.68, self.dir)
        self.assertEqual(self.build.call_count, 2)
        self.assertEqual(len(self.files()), 2)

    def test_corrupt_file_is_rebuilt(self):
        Atlas.cached(Z, self.dir)
        (self.dir / self.files()[0]).write_bytes(b"not a zip")
        again = Atlas.cached(Z, self.dir)
        self.assertSameAtlas(again, self.fresh)
        with mock.patch.object(atlas, "build_atlas", no_build):
            Atlas.cached(Z, self.dir)                          # и испорченный файл перезаписан

    def test_new_version_rebuilds_and_removes_old_files(self):
        with mock.patch.object(atlas_cache, "version", return_value="old"):
            Atlas.cached(Z, self.dir)
        self.assertTrue(self.files()[0].startswith("atlas-old-"))
        Atlas.cached(Z, self.dir)
        self.assertEqual(len(self.files()), 1)
        self.assertFalse(self.files()[0].startswith("atlas-old-"))

    def test_version_depends_on_drawing_code(self):
        v = atlas_cache.version()
        self.assertEqual(v, atlas_cache.version())
        real = Path.read_bytes

        def edited(p):
            data = real(p)
            return data + b"\n# edit" if p.name == "heart.py" else data

        with mock.patch.object(Path, "read_bytes", edited):
            self.assertNotEqual(atlas_cache.version(), v)

    def test_unwritable_cache_dir_still_works(self):
        blocker = self.dir / "file"
        blocker.write_text("x")
        a = Atlas.cached(Z, blocker / "sub")                   # каталог создать нельзя
        self.assertSameAtlas(a, self.fresh)
        self.assertEqual(self.files(), ["file"])


if __name__ == "__main__":
    unittest.main()
