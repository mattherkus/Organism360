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
from organism_atlas.organs import ORGANS, other_sex

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
        for job in ("flash_job", "next_job", "timer_job", "resize_job"):      # отложенные вызовы окна
            if getattr(self.app, job, None):
                self.root.after_cancel(getattr(self.app, job))
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
        self.root.after_cancel(self.app.flash_job)          # вспышку гасим сами, не дожидаясь таймера
        self.app.unflash()
        self.root.update()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.app.atlas.hidden, self.other)

    @property
    def other(self):
        """органы другого пола: на схеме их нет никогда"""
        return other_sex(self.app.body)

    def test_hidden_organs_only_in_study(self):
        self.app.toggle_organ("heart")
        self.assertEqual(self.app.atlas.hidden, {"heart"} | self.other)
        self.app.set_mode("find")
        self.assertEqual(self.app.atlas.hidden, self.other)
        self.app.set_mode("study")
        self.assertEqual(self.app.atlas.hidden, {"heart"} | self.other)
        self.assertEqual(self.errors, [])

    def test_body_switch(self):
        """женская и мужская схема: органы другого пола скрыты и в панели, и в викторине"""
        self.assertEqual(self.app.body, "male")
        self.assertIn("prostate", self.app.toggles)
        self.assertNotIn("uterus", self.app.toggles)
        self.app.toggle_organ("prostate")
        self.app.set_body("female")
        self.assertEqual(self.app.atlas.hidden, {"prostate"})
        self.assertIn("uterus", self.app.toggles)
        self.assertNotIn("prostate", self.app.toggles)
        self.app.set_mode("mix")
        self.app.start_quiz()
        self.assertNotIn("prostate", self.app.session.q)
        self.app.set_body("male")
        self.assertIsNone(self.app.session)             # игра началась заново с карточки настройки
        self.assertEqual(self.errors, [])

    def play(self):
        """пройти начатую игру до конца, отвечая верно: кликом по схеме или кнопкой"""
        s = self.app.session
        while not s.finished:
            if s.kind == "find":
                self.app.answer(s.current)
            else:
                self.assertEqual(set(self.app.choices), set(s.options()))
                self.app.pick(s.correct())
                self.root.after_cancel(self.app.next_job)
                self.app.next_question()
            self.root.update()
        if self.app.flash_job:
            self.root.after_cancel(self.app.flash_job)
        return s

    def test_quiz_length_and_topic(self):
        """длина игры и тема из карточки настройки; каждая игра проходится до конца"""
        for mode in ("find", "name", "facts", "mix"):
            self.app.set_mode(mode)
            for length in (5, 10, 0):
                self.app.set_cfg("length", length)
                self.app.start_quiz()
                s = self.play()
                self.assertEqual(s.total, length or len(self.app.organs()), (mode, length))
                self.assertEqual(s.first_try, s.total)
                self.app.set_mode(mode)
        self.app.set_cfg("topic", "digestive")
        self.app.set_cfg("length", 20)
        self.app.start_quiz()
        self.assertTrue(all("digestive" in ORGANS[k]["systems"] for k in self.app.session.q))
        self.assertEqual(self.app.session.total, 8)       # органов в теме меньше 20 - спрашиваем про все
        self.play()
        self.assertEqual(self.errors, [])

    def test_hide_all_organs(self):
        """кнопка в заголовке органов скрывает все органы, повторно - возвращает"""
        from organism_atlas.ui.widgets import ORGANS_ALL
        button = self.app.toggles[ORGANS_ALL]
        self.app.toggle_organ("heart")
        button.invoke()
        self.assertEqual(self.app.atlas.hidden, set(ORGANS))
        self.assertIsNone(self.app.atlas.organ_at(int(210 * Z), int(230 * Z)))
        self.assertEqual(button.cget("text"), i18n.t("layers_show_organs"))
        self.assertFalse(any(self.app.toggles[k].on for k in self.app.organs()))
        button.invoke()
        self.assertEqual(self.app.atlas.hidden, self.other)
        self.assertEqual(button.cget("text"), i18n.t("layers_hide_organs"))
        self.assertEqual(self.errors, [])

    def test_panel_only_in_study(self):
        """в викторине панели слоёв нет, а схема стоит на месте и не перерисовывается"""
        self.root.update()
        x = self.app.c.winfo_rootx()
        for mode in ("find", "name", "facts", "mix"):
            self.app.set_mode(mode)
            self.root.update()
            self.assertFalse(self.app.panel_box.winfo_ismapped(), mode)
            self.assertEqual(self.app.c.winfo_rootx(), x, mode)
            self.assertTrue(self.app.ready(), mode)
        self.app.set_mode("study")
        self.root.update()
        self.assertTrue(self.app.panel_box.winfo_ismapped())
        self.assertEqual(self.app.c.winfo_rootx(), x)
        self.assertEqual(self.errors, [])

    def test_setup_buttons(self):
        """каждая кнопка карточки настройки меняет свою настройку, а не настройку последней строки"""
        from organism_atlas.ui.widgets import RoundButton

        def press(text):
            todo = [self.app.card]
            while todo:
                w = todo.pop()
                if isinstance(w, RoundButton) and w.cget("text") == text:
                    return w.invoke()
                todo += w.winfo_children()
            self.fail(text)
        self.app.set_mode("name")
        self.root.update()
        before = self.app.card.winfo_children()
        press(i18n.t("level_hard"))
        press(i18n.t("timer_sec", sec=10))
        press("5")
        self.assertEqual((self.app.cfg["level"], self.app.cfg["timer"], self.app.cfg["length"]), ("hard", 10, 5))
        self.assertEqual(self.app.cfg["set"], "all")
        self.assertEqual(self.app.card.winfo_children(), before)          # обновлена на месте: не мигает
        self.app.set_mode("facts")                                         # другой режим - та же раскладка
        self.assertEqual(self.app.card.winfo_children(), before)
        self.assertEqual(self.errors, [])

    def test_panels_inside_window(self):
        """настройки, итоги и 3D - панели внутри главного окна, а не отдельные окна; Esc закрывает верхнюю"""
        from organism_atlas.ui import overlay, settings_window, viewer3d
        from organism_atlas.ui.results import show_results_dialog
        settings_window.show_settings(self.app)
        viewer3d.show_3d(self.root, "heart")
        s = SimpleNamespace(total=10, percent=80, first_try=8, verdict="", errors=2, elapsed=95, level="medium",
                            timeouts=0, missed=["heart"])
        results = show_results_dialog(self.root, s, on_again=lambda: None, on_retry=lambda: None)
        self.root.update()
        self.assertFalse([w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)])
        for panel in (settings_window._window.win, viewer3d._viewer.win, results):
            self.assertIsInstance(panel, overlay.Panel)
            self.assertIs(panel.master, self.root)
            self.assertTrue(panel.winfo_ismapped())
        self.app.on_key(SimpleNamespace(keysym="1", char="1"))           # цифры не уходят викторине за панелью
        self.root.focus_force()                                            # клавиши идут окну с фокусом
        self.root.update()
        for left in (2, 1, 0):
            self.root.event_generate("<Escape>")
            self.root.update()
            self.assertEqual(len(overlay.stack(self.root)), left)
        self.assertIsNone(settings_window._window)
        self.assertIsNone(viewer3d._viewer)
        self.assertEqual(self.errors, [])

    def test_button_fade(self):
        """наведение меняет цвет кнопки плавно и доходит до цвета состояния"""
        b = self.app.mode_buttons["find"]
        self.root.update()
        start = b.shown
        b.set_mouse(hover=True)
        self.assertIsNotNone(b.anim)
        t = time.time()
        while b.anim and time.time() - t < 2:
            self.root.update()
            time.sleep(0.005)
        self.assertEqual(b.shown, b.colors())
        self.assertNotEqual(b.shown, start)
        b.set_mouse(hover=False)
        b.config(text="x")                                                 # смена настройки - сразу, без перехода
        self.assertIsNone(b.anim)
        self.assertEqual(b.shown, b.colors())
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


class ColorGroupTests(unittest.TestCase):
    """органы в панели слоёв идут группами по цвету"""

    def test_families(self):
        from organism_atlas.ui.widgets import color_family
        self.assertEqual(color_family("#ea9fb6")[0], 0)          # розовый
        self.assertEqual(color_family("#c8323a")[0], 1)          # красный
        self.assertEqual(color_family("#7b2f55")[0], 2)          # тёмно-красный
        self.assertEqual(color_family("#e8a77f")[0], 3)          # персиковый
        self.assertEqual(color_family("#5fa13f")[0], 4)          # зелёный
        self.assertEqual(color_family("#3060c0")[0], 5)          # синий - прочие

    def test_order_keeps_families_together(self):
        from organism_atlas.ui.widgets import by_color, color_family
        order = by_color(ORGANS)
        self.assertEqual(sorted(order), sorted(ORGANS))
        fams = [color_family(ORGANS[k]["color"])[0] for k in order]
        self.assertEqual(fams, sorted(fams))
        self.assertEqual(order[-2:], ["gallbladder", "trachea"])      # зелёный, затем серо-голубая трахея
        self.assertLess(abs(order.index("lungs") - order.index("brain")), 2)



class SystemGroupTests(unittest.TestCase):
    """органы в панели слоёв разбиты на группы по главной системе"""

    def test_groups(self):
        from organism_atlas.organs import PANEL_SYSTEMS, by_system
        groups = dict(by_system(list(ORGANS)))
        self.assertEqual(sorted(k for ks in groups.values() for k in ks), sorted(ORGANS))
        self.assertEqual(list(groups), [s for s in PANEL_SYSTEMS if s in groups])
        self.assertEqual(groups["respiratory"], ["lungs", "trachea"])
        self.assertIn("pancreas", groups["digestive"])                   # главная система - первая
        self.assertEqual(groups["immune"], ["spleen"])
        self.assertEqual(groups["urinary"], ["kidneys", "bladder"])


if __name__ == "__main__":
    unittest.main()
