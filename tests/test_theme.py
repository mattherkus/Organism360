import unittest

from organism_atlas import i18n, settings, theme


class PaletteTests(unittest.TestCase):
    def test_same_roles_everywhere(self):
        roles = set(theme.THEMES["dark"])
        for name, pal in theme.THEMES.items():
            self.assertEqual(set(pal), roles, name)
        self.assertEqual(tuple(theme.THEMES), settings.CHOICES["theme"])

    def test_high_contrast_is_aaa(self):
        pal = theme.THEMES["contrast"]
        for fg, bg in theme.TEXT_PAIRS:
            self.assertGreaterEqual(theme.contrast(pal[fg], pal[bg]), 7.0, (fg, bg))

    def test_light_is_readable(self):
        pal = theme.THEMES["light"]
        for fg, bg in theme.TEXT_PAIRS:
            self.assertGreaterEqual(theme.contrast(pal[fg], pal[bg]), 4.5, (fg, bg))

    def test_contrast_formula(self):
        self.assertAlmostEqual(theme.contrast("#000000", "#ffffff"), 21.0)
        self.assertAlmostEqual(theme.contrast("#777777", "#777777"), 1.0)

    def test_unknown_theme_falls_back(self):
        theme.set_theme("contrast")
        theme.set_theme("purple")
        self.assertEqual(theme.current(), theme.DEFAULT)
        self.assertEqual(theme.C, theme.THEMES[theme.DEFAULT])

    def test_new_ui_strings_in_ru_and_en(self):
        keys = (["theme_" + n for n in settings.CHOICES["theme"]]
                + ["quality_" + q for q in settings.CHOICES["quality"]])
        for code in ("ru", "en"):
            ui = i18n._load(code)["ui"]
            for k in keys:
                self.assertTrue(ui.get(k), (code, k))


class TitleBarTests(unittest.TestCase):
    """заголовок окна и иконка в цветах темы"""

    def test_colors(self):
        from organism_atlas.ui import titlebar
        self.assertEqual(titlebar._colorref("#102030"), 0x302010)          # COLORREF: 0x00BBGGRR
        self.assertTrue(titlebar.is_dark(theme.THEMES["dark"]["bg"]))
        self.assertFalse(titlebar.is_dark(theme.THEMES["light"]["bg"]))
        self.assertTrue(titlebar.is_dark(theme.THEMES["contrast"]["bg"]))

    def test_icon(self):
        from organism_atlas.ui import titlebar
        im = titlebar.icon_image(32)
        self.assertEqual(im.size, (32, 32))
        self.assertEqual(im.getpixel((0, 0))[3], 0)                        # скруглённый угол прозрачный
        self.assertEqual(im.getpixel((16, 16))[:3], tuple(int(theme.C["on_accent"][i:i + 2], 16) for i in (1, 3, 5)))

    def test_paint_window(self):
        """покрасить заголовок можно только в Windows; в других системах paint ничего не делает"""
        import sys

        from tests.qt import app

        from organism_atlas.ui import titlebar
        from organism_atlas.ui.widgets import RoundCard
        app()
        w = RoundCard()
        self.assertEqual(titlebar.paint(w), sys.platform == "win32")
        titlebar.set_icon(app())
        self.assertFalse(app().windowIcon().isNull())


class Render3DBackgroundTests(unittest.TestCase):
    def test_frame_background_follows_colors(self):
        from organism_atlas.organs import ORGANS
        from organism_atlas.render3d.scene import Scene3D
        scene = Scene3D(ORGANS["heart"]["parts"]())
        dark = scene.render(80, 60, -62, 18, step=2)
        light = scene.render(80, 60, -62, 18, step=2, bg=("#ffffff", "#ffffff"))
        self.assertEqual(dark.getpixel((0, 0)), (14, 26, 34))          # как раньше: #0e1a22
        self.assertEqual(light.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(dark.getpixel((40, 30)), light.getpixel((40, 30)))    # сам орган не меняется


class PrefsTests(unittest.TestCase):
    def test_get_validates(self):
        self.assertEqual(settings.get({}, "theme"), "dark")
        self.assertEqual(settings.get({"theme": "light"}, "theme"), "light")
        self.assertEqual(settings.get({"theme": "neon"}, "theme"), "dark")
        self.assertEqual(settings.get({"quality": ["high"]}, "quality"), "medium")
        self.assertEqual(settings.get({"ui_scale": 1.25}, "ui_scale"), 1.25)
        self.assertEqual(settings.get({"ui_scale": True}, "ui_scale"), 1.0)
        self.assertEqual(settings.get({"ui_scale": "big"}, "ui_scale"), 1.0)


class RepaintTests(unittest.TestCase):
    """смена темы на лету: надписи и самодельные виджеты берут цвета новой темы"""

    def tearDown(self):
        theme.set_theme(theme.DEFAULT)

    def test_retheme(self):
        from tests.qt import app

        from organism_atlas.ui.widgets import RoundCard, fill_card, flat_button, label, retheme
        app()
        card = RoundCard()
        fill_card(card, "heart")
        muted = label("x", "muted")
        b = flat_button("x", None, bg="accent")
        theme.set_theme("contrast")
        retheme()
        self.assertEqual(muted.palette().windowText().color().name(), "#e6e6e6")
        self.assertEqual(b.colors()[:1] + b.colors()[2:], ("#ffd400", "#000000"))
        self.assertEqual(b.shown, b.colors())
        from PySide6.QtWidgets import QLabel
        labels = card.findChildren(QLabel)
        self.assertTrue(labels)
        self.assertTrue(all(w.palette().windowText().color().name() in ("#ffffff", "#e6e6e6", "#ffd400")
                            for w in labels))


if __name__ == "__main__":
    unittest.main()
