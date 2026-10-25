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


if __name__ == "__main__":
    unittest.main()
