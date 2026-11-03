import os
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

    def test_old_zooms_are_pruned(self):
        """масштабов в кэше не больше KEEP; удаляются те, что дольше всего не читались"""
        zooms = [0.5 + 0.05 * i for i in range(atlas_cache.KEEP + 2)]
        for i, z in enumerate(zooms):
            Atlas.cached(z, self.dir)
            if i == 0:
                first = atlas_cache._path(z, self.dir, atlas_cache.version())
                os.utime(first, (1, 1))                  # давно не читался
            if i == atlas_cache.KEEP - 1:
                Atlas.cached(zooms[0], self.dir)         # прочитали снова - он опять свежий
        self.assertEqual(len(self.files()), atlas_cache.KEEP)
        self.assertIn(first.name, self.files())
        self.assertNotIn(atlas_cache._path(zooms[1], self.dir, atlas_cache.version()).name, self.files())

    def test_corrupt_file_is_rebuilt(self):
        Atlas.cached(Z, self.dir)
        (self.dir / self.files()[0]).write_bytes(b"not a zip")
        again = Atlas.cached(Z, self.dir)
        self.assertSameAtlas(again, self.fresh)
        with mock.patch.object(atlas, "build_atlas", no_build):
            Atlas.cached(Z, self.dir)                          # и испорченный файл перезаписан

    def test_truncated_file_is_rebuilt(self):
        """обрезанный zip (питание пропало при записи) - не ошибка сборки, а повод нарисовать заново"""
        Atlas.cached(Z, self.dir)
        f = self.dir / self.files()[0]
        f.write_bytes(f.read_bytes()[: f.stat().st_size // 2])
        self.assertSameAtlas(Atlas.cached(Z, self.dir), self.fresh)
        data = bytearray(f.read_bytes())                      # испорченные сжатые данные внутри zip
        data[len(data) // 3: len(data) // 3 + 64] = bytes(64)
        f.write_bytes(bytes(data))
        self.assertSameAtlas(Atlas.cached(Z, self.dir), self.fresh)

    def test_new_version_rebuilds_and_removes_old_files(self):
        with mock.patch.object(atlas_cache, "version", return_value="old"):
            Atlas.cached(Z, self.dir)
        self.assertTrue(self.files()[0].startswith("atlas-old-"))
        Atlas.cached(Z, self.dir)
        self.assertEqual(len(self.files()), 1)
        self.assertFalse(self.files()[0].startswith("atlas-old-"))

    def test_old_version_tmp_leftovers_are_removed(self):
        """недописанный файл прошлой версии (программу закрыли посреди записи) не копится вечно"""
        (self.dir / "atlas-old-z0.7000.npz.123.tmp").write_bytes(b"half")
        Atlas.cached(Z, self.dir)
        self.assertEqual(len(self.files()), 1)
        self.assertFalse(self.files()[0].endswith(".tmp"))

    def test_prebuilt_is_read_when_user_cache_is_empty(self):
        """готовая схема из сборки: кэш пользователя пуст, а схема не рисуется и в кэш не копируется"""
        pre, user = self.dir / "pre", self.dir / "user"
        Atlas.cached(Z, pre)
        with mock.patch.object(atlas, "build_atlas", no_build):
            a = Atlas.cached(Z, user, prebuilt=pre)
            b = Atlas.preview(Z, user, prebuilt=pre)
        self.assertSameAtlas(a, self.fresh)
        self.assertEqual(b.Z, atlas_cache.zoom_key(Z))
        self.assertFalse(user.exists())

    def test_preview_falls_back_to_nearest_prebuilt(self):
        pre, user = self.dir / "pre", self.dir / "user"
        Atlas.cached(Z, pre)
        Atlas.cached(0.5, pre)
        with mock.patch.object(atlas, "build_atlas", no_build):
            self.assertEqual(Atlas.preview(0.75, user, prebuilt=pre).Z, Z)
            self.assertEqual(Atlas.preview(0.55, user, prebuilt=pre).Z, 0.5)
        self.assertIsNone(Atlas.preview(Z, user, prebuilt=self.dir / "none"))
        with mock.patch.object(atlas_cache, "version", return_value="other"):      # схемы другой версии не годятся
            self.assertIsNone(Atlas.preview(Z, user, prebuilt=pre))

    def test_version_depends_on_drawing_code(self):
        atlas_cache.version.cache_clear()
        self.addCleanup(atlas_cache.version.cache_clear)
        v = atlas_cache.version()
        self.assertEqual(v, atlas_cache.version())
        real = Path.read_bytes

        def edited(p):
            data = real(p)
            return data + b"\n# edit" if p.name == "heart.py" else data

        with mock.patch.object(Path, "read_bytes", edited):
            self.assertEqual(atlas_cache.version(), v)            # считается раз за запуск
            atlas_cache.version.cache_clear()
            self.assertNotEqual(atlas_cache.version(), v)

    def test_unwritable_cache_dir_still_works(self):
        blocker = self.dir / "file"
        blocker.write_text("x")
        a = Atlas.cached(Z, blocker / "sub")                   # каталог создать нельзя
        self.assertSameAtlas(a, self.fresh)
        self.assertEqual(self.files(), ["file"])


if __name__ == "__main__":
    unittest.main()
