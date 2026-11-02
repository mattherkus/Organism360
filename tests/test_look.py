import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from organism_atlas.models import read_model
from organism_atlas.organs import ORGANS
from organism_atlas.render3d import look, shading
from organism_atlas.render3d.scene import Scene3D

MAT_KEYS = {"roughness", "wetness", "sss", "mottle", "veins"}


def pixels(im):
    return np.asarray(im).reshape(-1, 3)


class LookFileTests(unittest.TestCase):
    def test_materials_cover_all_textures_in_models(self):
        lk = look.get()
        self.assertEqual(lk["style"], "realistic")
        used = {p["texture"] for k in ORGANS for p in read_model(k)["parts"]}
        mats = {k: v for k, v in lk["materials"].items() if not k.startswith("_")}
        self.assertLessEqual(used, set(mats))
        for name, m in mats.items():
            self.assertEqual(set(m), MAT_KEYS, name)
            dry, wet = m["roughness"]
            self.assertTrue(0 < wet <= dry < 1, name)
            for k in ("wetness", "sss", "mottle", "veins"):
                self.assertTrue(0 <= m[k] <= 1, (name, k))

    def test_broken_file_falls_back_to_classic(self):
        sc = Scene3D(ORGANS["heart"]["parts"]())   # до подмены: resources.files общий для всего пакета
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "look.json").write_text('{"style": "realistic",', encoding="utf-8")
            with mock.patch.object(look.resources, "files", return_value=Path(tmp)), \
                    mock.patch.dict(look._cache, clear=True), mock.patch("sys.stderr"):
                self.assertEqual(look.get()["style"], "classic")
                a = sc.render(80, 60, -62, 18)                       # без настроек света не падает
                b = sc.render(80, 60, -62, 18, style="classic")
                self.assertEqual(a.tobytes(), b.tobytes())


class RealisticRenderTests(unittest.TestCase):
    def test_every_organ_differs_from_classic(self):
        for key, o in ORGANS.items():
            sc = Scene3D(o["parts"]())
            a = sc.render(120, 90, -62, 18, style="realistic")
            b = sc.render(120, 90, -62, 18, style="classic")
            self.assertNotEqual(a.tobytes(), b.tobytes(), key)
            self.assertGreater(len(np.unique(pixels(a), axis=0)), 200, key)

    def test_highlights_do_not_blow_out(self):
        """классический блик выжигал пузырь и печень в белое; теперь чистого белого почти нет"""
        for key in ("bladder", "liver", "heart"):
            sc = Scene3D(ORGANS[key]["parts"]())
            white = lambda st, sc=sc: int((pixels(sc.render(200, 150, -62, 18, ss=2, style=st)).min(1) >= 250).sum())
            self.assertLess(white("realistic"), max(5, white("classic") // 4), key)

    def test_shadows_full_frame_only(self):
        sc = Scene3D(ORGANS["kidneys"]["parts"]())
        with mock.patch.object(Scene3D, "_shadow", wraps=sc._shadow) as sh:
            sc.render(100, 75, -62, 18, step=2)                  # черновик при вращении
            self.assertEqual(sh.call_count, 0)
            sc.render(100, 75, -62, 18)
            self.assertEqual(sh.call_count, 1)
            sc.render(100, 75, -62, 18, shadows=False)
            self.assertEqual(sh.call_count, 1)

    def test_shadow_falls_on_kidney(self):
        """мочеточник и сосуды затеняют почку: с тенями кадр темнее"""
        sc = Scene3D(ORGANS["kidneys"]["parts"]())
        on = pixels(sc.render(200, 150, -62, 18, shadows=True)).astype(int).sum()
        off = pixels(sc.render(200, 150, -62, 18, shadows=False)).astype(int).sum()
        self.assertLess(on, off)

    def test_tonemap_keeps_hue(self):
        lin = np.array([[0.20, 0.03, 0.02], [0.05, 0.10, 0.30], [0.6, 0.4, 0.2]], np.float32)
        out = shading.tonemap(lin)
        for a, b in zip(lin, out):
            self.assertTrue(np.allclose(a / a.max(), b / b.max(), atol=1e-4))
        self.assertTrue(((out >= 0) & (out <= 1)).all())


if __name__ == "__main__":
    unittest.main()
