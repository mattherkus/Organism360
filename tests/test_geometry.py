import unittest

from organism_atlas.geometry import CX, P, cr_spline, rrect, sym, tube_outline


class GeometryTests(unittest.TestCase):
    def test_p_flip_mirrors_around_axis(self):
        (x1, y1), = P([(10, 5)])
        (x2, y2), = P([(10, 5)], flip=True)
        self.assertEqual((x1, y1), (CX + 10, 5))
        self.assertEqual((x2, y2), (CX - 10, 5))

    def test_sym_is_closed_and_symmetric(self):
        half = [(0, 0), (10, 5), (0, 10)]
        pts = sym(half)
        self.assertEqual(len(pts), 6)
        self.assertEqual({(round(x - CX), y) for x, y in pts if x >= CX},
                         {(round(CX - x), y) for x, y in pts if x <= CX})

    def test_spline_passes_through_control_points(self):
        ctrl = [(0, 0), (10, 5), (20, 0), (30, 8)]
        out = cr_spline(ctrl, n=10)
        for p in ctrl:
            self.assertIn(tuple(map(float, p)), out)

    def test_tube_outline_has_two_sides(self):
        outline, centre, widths = tube_outline([(0, 0), (10, 0), (20, 5)], [4, 4, 4], n=6)
        self.assertEqual(len(outline), 2 * len(centre))
        self.assertEqual(len(widths), len(centre))

    def test_rrect_has_eight_points(self):
        self.assertEqual(len(rrect(0, 0, 10, 6)), 8)


if __name__ == "__main__":
    unittest.main()
