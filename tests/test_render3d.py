import unittest

import numpy as np

from organism_atlas.organs import ORGANS
from organism_atlas.render3d.scene import Scene3D


class Render3DTests(unittest.TestCase):
    def test_every_organ_renders(self):
        for key, o in ORGANS.items():
            with self.subTest(organ=key):
                im = Scene3D(o["parts"]()).render(120, 90, -62, 18, zoom=1.0, ss=1, step=2)
                self.assertEqual(im.size, (120, 90))
                colors = np.unique(np.asarray(im).reshape(-1, 3), axis=0)
                self.assertGreater(len(colors), 50)               # не пустая картинка

    def test_rotation_changes_picture(self):
        scene = Scene3D(ORGANS["heart"]["parts"]())
        a = scene.render(100, 80, 0, 10)
        b = scene.render(100, 80, 90, 10)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_fast_raster_matches_exact(self):
        """быстрая растеризация черновика даёт почти ту же картинку, что и точная (разница - на рёбрах)"""
        import math
        from organism_atlas.render3d.meshraster import raster_mesh
        scene = Scene3D(ORGANS["heart"]["parts"]())
        a, e = math.radians(-62), math.radians(18)
        cam = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        right = np.array([-math.sin(a), math.cos(a), 0.0])
        up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
        W, H = 160, 120
        scale = 0.5 * min(W, H) / scene.radius
        out = []
        for exact in (True, False):
            bufs = (np.full((H, W), -1e9, np.float32), np.zeros((3, H, W), np.float32),
                    np.full((H, W), -1, np.int16), np.full((H, W), -1, np.int32))
            for V, F, VN, mid, cull, FN in scene.meshes:
                raster_mesh(V, F, VN, mid, bufs, cam, right, up, scale, W / 2, H / 2, scene.center, cull, FN, exact)
            out.append(bufs)
        (z1, n1, m1, _), (z2, n2, m2, _) = out
        self.assertGreater((m1 >= 0).sum(), 3000)
        self.assertLess((m1 != m2).mean(), 0.003)                       # части - те же почти везде
        same = (m1 == m2) & (m1 >= 0)
        self.assertLess(np.abs(z1 - z2)[same].max(), 0.05 * scene.radius)
        self.assertGreater((n1 * n2).sum(0)[same].mean(), 0.995)        # нормали почти совпадают


if __name__ == "__main__":
    unittest.main()
