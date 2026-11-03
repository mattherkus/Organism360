import unittest

from organism_atlas import i18n, settings, theme


class PaletteTests(unittest.TestCase):
    def test_same_roles_everywhere(self):
        roles = set(theme.THEMES["paper"])
        for name, pal in theme.THEMES.items():
            self.assertEqual(set(pal), roles, name)
        self.assertEqual(tuple(theme.THEMES) + (theme.SYSTEM,), settings.CHOICES["theme"])

    def test_themes_are_readable(self):
        for name in ("paper", "black"):
            pal = theme.THEMES[name]
            for fg, bg in theme.TEXT_PAIRS:
                self.assertGreaterEqual(theme.contrast(pal[fg], pal[bg]), 4.5, (name, fg, bg))

    def test_atlas_themes(self):
        """светлая (по умолчанию) и тёмная: схема прямо на странице - её фон как у окна;
        окно тёмной темы тёмное, светлой - светлое"""
        from organism_atlas.ui import titlebar
        self.assertEqual(theme.DEFAULT, "paper")
        for name in ("paper", "black"):
            self.assertEqual(theme.THEMES[name]["scene_bg"], theme.THEMES[name]["bg"], name)
        self.assertTrue(titlebar.is_dark(theme.THEMES["black"]["bg"]))
        self.assertFalse(titlebar.is_dark(theme.THEMES["paper"]["bg"]))

    def test_contrast_formula(self):
        self.assertAlmostEqual(theme.contrast("#000000", "#ffffff"), 21.0)
        self.assertAlmostEqual(theme.contrast("#777777", "#777777"), 1.0)

    def test_system_theme(self):
        """«как в системе»: запоминается сам выбор, а цвета - светлой или тёмной палитры по системе"""
        from unittest import mock
        try:
            for sys_name in ("paper", "black"):
                with mock.patch.object(theme, "system_theme", return_value=sys_name):
                    theme.set_theme(theme.SYSTEM)
                self.assertEqual(theme.current(), theme.SYSTEM)
                self.assertEqual(theme.C, theme.THEMES[sys_name])
            self.assertIn(theme.system_theme(), theme.THEMES)
            self.assertEqual(settings.get({"theme": "system"}, "theme"), "system")
        finally:
            theme.set_theme(theme.DEFAULT)

    def test_unknown_theme_falls_back(self):
        theme.set_theme("black")
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
        self.assertTrue(titlebar.is_dark(theme.THEMES["black"]["bg"]))
        self.assertFalse(titlebar.is_dark(theme.THEMES["paper"]["bg"]))

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
        self.assertEqual(settings.get({}, "theme"), "paper")
        self.assertEqual(settings.get({"theme": "black"}, "theme"), "black")
        self.assertEqual(settings.get({"theme": "light"}, "theme"), "paper")      # убранные темы
        self.assertEqual(settings.get({"theme": "contrast"}, "theme"), "black")
        self.assertEqual(settings.get({"theme": "neon"}, "theme"), "paper")
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

        from organism_atlas.ui.cards import fill_card
        from organism_atlas.ui.widgets import RoundCard, flat_button, label, retheme
        app()
        card = RoundCard()
        fill_card(card, "heart")
        muted = label("x", "muted")
        b = flat_button("x", None, bg="accent")
        theme.set_theme("black")
        retheme()
        pal = theme.THEMES["black"]
        self.assertEqual(muted.palette().windowText().color().name(), pal["muted"])
        self.assertEqual(b.colors()[:1] + b.colors()[2:], (pal["accent"], pal["on_accent"]))
        self.assertEqual(b.shown, b.colors())
        from PySide6.QtWidgets import QLabel
        labels = card.findChildren(QLabel)
        self.assertTrue(labels)
        self.assertTrue(all(w.palette().windowText().color().name() in (pal["text"], pal["muted"], pal["accent_fg"], pal["day_title"])
                            for w in labels))


if __name__ == "__main__":
    unittest.main()
