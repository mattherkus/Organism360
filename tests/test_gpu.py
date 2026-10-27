"""3D на видеокарте (render3d/gpu.py) против программного рендера: кадры должны совпадать.
Без OpenGL 3.3 (нет видеокарты, драйвера или moderngl) тесты пропускаются."""

import unittest

import numpy as np

from organism_atlas.models import load_procedural
from organism_atlas.organs import ORGANS
from organism_atlas.render3d import gpu
from organism_atlas.render3d.scene import Scene3D


def diff(a, b):
    return np.abs(np.asarray(a).astype(np.int16) - np.asarray(b).astype(np.int16))


class GpuRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not gpu.available():
            raise unittest.SkipTest("нет OpenGL 3.3: %s" % gpu._failed)

    def check(self, parts, **kw):
        """кадр и карта частей те же, что у Scene3D: отличаются лишь отдельные пиксели на рёбрах треугольников"""
        g, c = gpu.GpuScene(parts), Scene3D(parts)
        a, ia = c.render(160, 120, -62, 18, ids=True, **kw)
        b, ib = g.render(160, 120, -62, 18, ids=True, **kw)
        self.assertIsNone(g.gpu_error)
        d = diff(a, b)
        self.assertLess(d.mean(), 0.1)
        self.assertLessEqual(np.percentile(d, 99), 2)
        self.assertLess((ia != ib).mean(), 0.001)
        return g, b, ib

    def test_meshes(self):
        for key in ("heart", "brain", "lungs", "intestines", "thyroid"):
            with self.subTest(organ=key):
                self.check(ORGANS[key]["parts"]())
                self.check(ORGANS[key]["parts"](), ss=2)

    def test_draft(self):
        self.check(ORGANS["liver"]["parts"](), step=2)

    def test_procedural_ellipsoids_and_tubes(self):
        for key in ("heart", "kidneys", "lungs"):
            with self.subTest(organ=key):
                self.check(load_procedural(key))
                self.check(load_procedural(key), step=2)

    def test_hidden_parts_background_and_shadows(self):
        from organism_atlas.models import load_mesh
        parts = load_mesh("brain")
        cortex = [p["group"] for p in parts].index("cortex")
        _, _, ids = self.check(parts, hidden={cortex}, bg=("#ffffff", "#eef2f5"))
        self.assertNotIn(cortex, np.unique(ids))
        self.check(parts, shadows=False)

    def test_speed(self):
        """кадр 600 x 450 с суперсэмплингом x3: на видеокарте - миллисекунды, даже на программном OpenGL (llvmpipe) -
        меньше полутора секунд (программный рендер Scene3D - около трёх)"""
        import time
        g = gpu.GpuScene(ORGANS["heart"]["parts"]())
        g.render(600, 450, -62, 18, ss=3)
        t = time.perf_counter()
        g.render(600, 450, -40, 10, ss=3)
        self.assertLess(time.perf_counter() - t, 1.5)
        self.assertIsNone(g.gpu_error)

    def test_many_sizes_and_scenes(self):
        """кадры разных размеров (черновики при вращении) и смена органов: посредники и буферы ушедших
        сцен освобождаются, а кадр по-прежнему на видеокарте"""
        import gc
        for key in ("heart", "brain", "kidneys"):
            g = gpu.GpuScene(ORGANS[key]["parts"]())
            for i in range(2 * gpu.GL.KEEP):
                g.render(60 + 7 * i, 50 + 5 * i, -62 + 10 * i, 18, ss=1 + i % 2, step=1 + i % 2)
                self.assertIsNone(g.gpu_error)
            del g
            gc.collect()
        gl = gpu.context()
        self.assertFalse([k for k in gl.pool if k[0] == (60, 50)])     # первый черновик давно освобождён
        self.assertTrue(all(gl.frame - f <= gl.KEEP for f in gl.used.values()))
        self.check(ORGANS["liver"]["parts"]())

    def test_renderer_name_after_frame(self):
        """название видеокарты для настроек - и после кадра (контекст тогда уже не текущий)"""
        gpu.GpuScene(ORGANS["bladder"]["parts"]()).render(40, 30, -62, 18)
        self.assertTrue(gpu.info())

    def test_other_thread_falls_back(self):
        """контекст привязан к своему потоку: из другого кадр считает Scene3D"""
        import threading
        g = gpu.GpuScene(ORGANS["bladder"]["parts"]())
        out = []
        th = threading.Thread(target=lambda: out.append(g.render(80, 60, -62, 18, step=2)))
        th.start()
        th.join()
        self.assertEqual(out[0].size, (80, 60))
        self.assertEqual(g.gpu_error, "другой поток")


class FallbackTests(unittest.TestCase):
    def test_make_scene_without_gpu(self):
        """ORGANISM_ATLAS_GPU=0 или нет OpenGL - обычная Scene3D"""
        from unittest import mock
        with mock.patch.object(gpu, "available", lambda: False):
            self.assertIs(type(gpu.make_scene(ORGANS["bladder"]["parts"]())), Scene3D)

    def test_noise_tables_match_fbm3(self):
        """волны из fbm_waves дают тот же шум, что textures.fbm3"""
        from organism_atlas.render3d.textures import fbm3
        p = np.random.default_rng(1).normal(size=(50, 3)).astype(np.float32)
        for f, octs, seed in gpu.FIXED_NOISE + ((1.3, 3, 31),):
            s = sum(a * np.sin(p @ d + ph) for d, ph, a in gpu.fbm_waves(f, octs, seed))
            np.testing.assert_allclose(s, fbm3(p, f, octs, seed), atol=1e-4)


if __name__ == "__main__":
    unittest.main()
