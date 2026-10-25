"""Главное окно целиком: наведение, панель слоёв, смена размера. Нужен экран; без него тесты пропускаются.
Схема рисуется в маленьком масштабе и в свою папку кэша, настройки и прогресс - во временные файлы."""

import os
import tempfile
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

from organism_atlas import i18n, questions
from organism_atlas.atlas import Atlas
from organism_atlas.organs import ORGANS

Z = 0.7


class AppTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("нет экрана")
        self.root.attributes("-alpha", 0.0)            # окно показано (схема рисуется по <Configure>), но невидимо
        self.errors = []
        self.root.report_callback_exception = lambda *a: self.errors.append(a[1])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"ORGANISM_ATLAS_SETTINGS": os.path.join(self.tmp.name, "s.json"),
                                           "ORGANISM_ATLAS_PROGRESS": os.path.join(self.tmp.name, "p.json")})
        env.start()
        self.addCleanup(env.stop)
        from organism_atlas.ui import app
        self.zoom = Z                                       # масштаб, который «выбирает» окно
        cached = Atlas.cached.__func__
        for p in (mock.patch.object(app, "pick_zoom", lambda root: Z),
                  mock.patch.object(app, "fit_zoom", lambda w, h: self.zoom),
                  mock.patch.object(app.Atlas, "cached", classmethod(lambda cls, z: cached(cls, z, self.tmp.name)))):
            p.start()
            self.addCleanup(p.stop)
        i18n.load_all()
        questions.load_all(known=list(ORGANS))
        self.app = app.App(self.root)
        self.wait()

    def tearDown(self):
        self.root.destroy()

    def wait(self):
        t = time.time()
        while not self.app.ready() and time.time() - t < 60:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(self.app.ready())

    def hover_heart(self):
        z = self.app.want_Z
        self.app.on_move(SimpleNamespace(x=int(210 * z), y=int(230 * z)))
        self.root.update()
        self.assertEqual(self.app.cur, "heart")

    def test_hide_organ_after_hover(self):
        """подсветка показывалась, потом орган скрыли: картинки подсветки удаляются без ошибок Tk"""
        self.hover_heart()
        self.app.flash("heart", "ok")
        self.app.toggle_organ("lungs")
        self.app.on_leave(None)
        self.hover_heart()
        self.app.show_all()
        self.app.unflash()
        self.root.update()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.app.atlas.hidden, frozenset())

    def test_hidden_organs_only_in_study(self):
        self.app.toggle_organ("heart")
        self.assertEqual(self.app.atlas.hidden, {"heart"})
        self.app.set_mode("find")
        self.assertEqual(self.app.atlas.hidden, frozenset())
        self.app.set_mode("study")
        self.assertEqual(self.app.atlas.hidden, {"heart"})
        self.assertEqual(self.errors, [])

    def test_resize_after_hover(self):
        """после наведения окно поменяло размер: схема перерисовалась, подсветка работает"""
        self.hover_heart()
        self.zoom = 0.6
        self.app.on_resize(SimpleNamespace(width=0, height=0))
        self.assertFalse(self.app.ready())
        self.app.start_build()                              # не ждём паузу после растягивания
        self.wait()
        self.assertEqual(self.app.atlas.Z, 0.6)
        self.hover_heart()
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
