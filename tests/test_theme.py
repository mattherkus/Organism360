import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

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
        from organism_atlas.ui import titlebar
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("нет экрана")
        try:
            titlebar.set_icon(root)
            titlebar.paint(root)
            titlebar.paint_all(root)                                     # повторно: <Map> привязан один раз
            self.assertEqual(root.bind("<Map>").count("<lambda>"), 1)
        finally:
            root.destroy()


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
    """смена темы на лету в настоящих окнах Tk"""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:                       # нет экрана
            self.skipTest(str(e))
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.old_env = os.environ.get("ORGANISM_ATLAS_SETTINGS")
        os.environ["ORGANISM_ATLAS_SETTINGS"] = str(Path(self.tmp.name, "settings.json"))

    def tearDown(self):
        self.root.destroy()
        theme.set_theme(theme.DEFAULT)
        i18n._current = i18n._previous = i18n.BASE
        if self.old_env is None:
            os.environ.pop("ORGANISM_ATLAS_SETTINGS", None)
        else:
            os.environ["ORGANISM_ATLAS_SETTINGS"] = self.old_env
        self.tmp.cleanup()

    def test_repaint_reaches_child_windows(self):
        from organism_atlas.ui.widgets import fill_card, flat_button, frame
        top = theme.style(tk.Toplevel(self.root), bg="bg")
        card = frame(top)
        fill_card(card, "heart")
        b = flat_button(top, "x", None, bg="accent")
        theme.set_theme("contrast")
        theme.repaint(self.root)
        self.assertEqual(top.cget("bg"), "#000000")
        self.assertEqual(b.cget("bg"), "#ffd400")
        self.assertEqual(b.cget("fg"), "#000000")
        labels = [w for w in card.winfo_children() if isinstance(w, tk.Label)]
        self.assertTrue(labels)
        self.assertTrue(all(w.cget("bg") == "#000000" for w in labels))

    def test_app_settings_apply_and_persist(self):
        from organism_atlas.ui import app as app_mod, settings_window, viewer3d
        app_mod.App.start_build = lambda self: None          # схема тела для этой проверки не нужна
        try:
            a = app_mod.App(self.root)
            settings_window.show_settings(a)
            win = settings_window._window
            self.assertIsNotNone(win)
            a.set_theme("light")
            self.assertEqual(self.root.cget("bg"), theme.THEMES["light"]["bg"])
            self.assertEqual(a.card.cget("bg"), "#ffffff")
            self.assertEqual(win.win.cget("bg"), theme.THEMES["light"]["bg"])
            a.set_lang("en")
            self.assertEqual(win.win.title(), "Settings")
            self.assertIn("Settings", a.settings_button.cget("text"))
            a.set_quality("high")
            self.assertEqual(viewer3d._quality, "high")
            from organism_atlas.ui.widgets import RoundButton
            buttons = [b for row in win.body.winfo_children() for b in row.winfo_children()
                       if isinstance(b, RoundButton)]
            before = win.body.winfo_children()
            next(b for b in buttons if b.cget("text") == "125%").invoke()    # как щелчок в окне
            self.assertEqual(win.body.winfo_children(), before)            # обновлено на месте: не мигает
            self.assertEqual(a.ui_scale, 1.0)                 # сам масштаб - после перезапуска
            texts = [w.cget("text") for w in win.body.winfo_children() if isinstance(w, tk.Label)]
            self.assertIn("125% selected: restart the app to apply it.", texts)
            saved = settings.load()
            self.assertEqual({k: settings.get(saved, k) for k in settings.DEFAULTS},
                             {**settings.DEFAULTS, "theme": "light", "quality": "high", "ui_scale": 1.25})
            self.assertEqual(saved["lang"], "en")
            win.win.destroy()
            self.assertIsNone(settings_window._window)
        finally:
            del app_mod.App.start_build
            viewer3d.set_quality("medium")


if __name__ == "__main__":
    unittest.main()
