"""Главное окно целиком: наведение, панель слоёв, викторины, панели, 3D. Окно на Qt без экрана (offscreen).
Схема рисуется в маленьком масштабе и в свою папку кэша, настройки и прогресс - во временные файлы."""

import os
import tempfile
import unittest
from unittest import mock

from PySide6.QtWidgets import QWidget

from tests.qt import app as qt_app, pump, wait

from organism_atlas import i18n, questions
from organism_atlas.atlas import Atlas
from organism_atlas.organs import ORGANS, other_sex

Z = 0.7


class AppTests(unittest.TestCase):
    def setUp(self):
        self.qt = qt_app()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"ORGANISM_ATLAS_SETTINGS": os.path.join(self.tmp.name, "s.json"),
                                           "ORGANISM_ATLAS_PROGRESS": os.path.join(self.tmp.name, "p.json")})
        env.start()
        self.addCleanup(env.stop)
        from organism_atlas.ui import app
        self.zoom = Z                                       # масштаб, который «выбирает» окно
        cached, preview = Atlas.cached.__func__, Atlas.preview.__func__
        self.pre = os.path.join(self.tmp.name, "prebuilt")     # готовые схемы «из сборки»
        for p in (mock.patch.object(app, "pick_zoom", lambda w, h, dpr=1.0: Z),
                  mock.patch.object(app, "fit_zoom", lambda w, h: self.zoom),
                  mock.patch.object(app.Atlas, "cached", classmethod(lambda cls, z: cached(cls, z, self.tmp.name,
                                                                                          self.pre))),
                  mock.patch.object(app.Atlas, "preview", classmethod(lambda cls, z: preview(cls, z, self.tmp.name,
                                                                                            self.pre)))):
            p.start()
            self.addCleanup(p.stop)
        i18n.load_all()
        questions.load_all(known=list(ORGANS))
        self.app = app.App()
        self.app.show()
        self.wait()

    def tearDown(self):
        from organism_atlas.ui import overlay
        while overlay.close_top(self.app):
            pass
        self.app.close()
        self.app.deleteLater()
        pump()
        i18n._current = i18n._previous = i18n.BASE

    def wait(self):
        self.assertTrue(wait(self.app.ready))

    def hover_heart(self):
        z = self.app.want_Z
        self.app.on_move(int(210 * z), int(230 * z))
        self.assertEqual(self.app.cur, "heart")

    def test_hide_organ_after_hover(self):
        """подсветка показывалась, потом орган скрыли: подсветка убирается, наведение работает дальше"""
        self.hover_heart()
        self.app.flash("heart", "ok")
        self.app.toggle_organ("lungs")
        self.assertIsNone(self.app.view.layers["hover"])
        self.app.on_leave()
        self.hover_heart()
        self.app.show_all()
        self.app.unflash()
        pump()
        self.assertEqual(self.app.atlas.hidden, self.other)

    def test_card_links_open_other_organ(self):
        """в карточке сердца «лёгкие» - ссылка: щелчок открывает карточку лёгких и подсвечивает их"""
        from PySide6.QtWidgets import QLabel
        self.app.show_info("heart")
        links = [w for w in self.app.card.findChildren(QLabel) if 'href="lungs"' in w.text()]
        self.assertEqual(len(links), 1)                     # ссылка на орган одна, при первом упоминании
        self.assertFalse([w for w in self.app.card.findChildren(QLabel) if 'href="heart"' in w.text()])
        links[0].linkActivated.emit("lungs")
        pump()
        self.assertEqual(self.app.spot, "lungs")
        self.assertTrue([w for w in self.app.card.findChildren(QLabel) if w.text() == i18n.name("lungs")])

    def test_diseases_guide_links(self):
        """заболевание в карточке органа ведёт в справочник, орган в статье - обратно в карточку"""
        from PySide6.QtWidgets import QLabel
        from organism_atlas.ui.diseases import DiseasesPanel
        from organism_atlas.ui.overlay import top
        self.app.show_info("liver")
        link = [w for w in self.app.card.findChildren(QLabel) if 'href="cirrhosis"' in w.text()]
        self.assertEqual(len(link), 1)
        link[0].linkActivated.emit("cirrhosis")
        pump()
        panel = top(self.app)
        self.assertIsInstance(panel, DiseasesPanel)
        self.assertEqual(panel.key, "cirrhosis")
        texts = [w.text() for w in panel.card.findChildren(QLabel)]
        self.assertTrue(any('href="hepatitis"' in s for s in texts))        # болезнь -> болезнь
        panel.select("hepatitis")
        self.assertEqual(panel.key, "hepatitis")
        panel.on_search("почк")
        self.assertIn("ckd", panel.items)
        self.assertNotIn("stroke", panel.items)
        panel.select("stroke")                                               # ссылка вне поиска сбрасывает его
        self.assertEqual(panel.search.text(), "")
        self.assertIn("ckd", panel.items)
        organ = [w for w in panel.card.findChildren(QLabel) if 'href="brain"' in w.text()]
        organ[0].linkActivated.emit("brain")                                 # болезнь -> орган
        pump()
        self.assertIsNone(top(self.app))
        self.assertEqual(self.app.spot, "brain")

    def test_latin_toggle(self):
        """кнопка «Латынь»: названия органов по-латыни, язык кнопок не меняется и запоминается"""
        from organism_atlas import settings
        self.app.set_lang("en")
        self.app.latin_action.trigger()
        self.assertTrue(i18n.latin())
        self.assertEqual(i18n.base(), "en")
        self.assertTrue(self.app.latin_action.isChecked())
        self.assertTrue(self.app.lang_actions["en"].isChecked())
        self.assertIn("LA", self.app.lang_button.text())                  # кнопка меню показывает и латынь
        self.assertEqual(self.app.toggles["heart"].text, "Cor")
        self.assertEqual(set(self.app.lang_actions), set(i18n.languages()))
        saved = settings.load()
        self.assertEqual((saved["lang"], saved["previous_lang"]), ("la", "en"))
        self.app.latin_action.trigger()
        self.assertFalse(i18n.latin())
        self.assertFalse(self.app.latin_action.isChecked())
        self.assertEqual(self.app.toggles["heart"].text, "Heart")

    def test_diseases_only_in_study(self):
        from organism_atlas.ui.overlay import top
        self.app.diseases_button.invoke()
        self.assertIsNotNone(top(self.app))
        self.app.set_mode("find")
        self.assertIsNone(top(self.app))
        self.assertFalse(self.app.diseases_button.isEnabled())

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
        self.app.quiz.start()
        self.assertNotIn("prostate", self.app.quiz.session.q)
        self.app.set_body("male")
        self.assertIsNone(self.app.quiz.session)             # игра началась заново с карточки настройки

    def play(self):
        """пройти начатую игру до конца, отвечая верно: кликом по схеме или кнопкой"""
        s = self.app.quiz.session
        while not s.finished:
            if s.kind == "find":
                self.app.quiz.answer(s.current)
            else:
                self.assertEqual(set(self.app.quiz.choices), set(s.options()))
                self.app.quiz.choices[s.correct()].click()               # как щелчок по кнопке
                self.assertTrue(self.app.quiz.next_timer.isActive())
                self.app.quiz.next_question()
        self.app.unflash()
        self.app.quiz.results_timer.stop()
        return s

    def test_quiz_length_and_topic(self):
        """длина игры и тема из карточки настройки; каждая игра проходится до конца"""
        for mode in ("find", "name", "facts", "mix"):
            self.app.set_mode(mode)
            for length in (5, 10, 0):
                self.app.quiz.set_cfg("length", length)
                self.app.quiz.start()
                s = self.play()
                self.assertEqual(s.total, length or len(self.app.organs()), (mode, length))
                self.assertEqual(s.first_try, s.total)
                self.app.set_mode(mode)
        self.app.quiz.set_cfg("topic", "digestive")
        self.app.quiz.set_cfg("length", 15)
        self.app.quiz.start()
        self.assertTrue(all("digestive" in ORGANS[k]["systems"] for k in self.app.quiz.session.q))
        self.assertEqual(self.app.quiz.session.total, 8)       # органов в теме меньше 15 - спрашиваем про все
        self.play()

    def test_wrong_answer_and_digits(self):
        """неверный вариант краснеет и больше не нажимается; цифра на клавиатуре выбирает вариант"""
        self.app.set_mode("name")
        self.app.on_key("Return", "")                       # Enter на карточке настройки - начать игру
        s = self.app.quiz.session
        self.assertIsNotNone(s)
        wrong = next(k for k in s.options() if k != s.correct())
        b = self.app.quiz.choices[wrong]
        self.app.quiz.pick(wrong)
        self.assertFalse(b.isEnabled())
        self.assertEqual(b.role, "wrong_bg")
        self.assertEqual(s.errors, 1)
        right = s.correct()
        self.app.on_key("", str(list(self.app.quiz.choices).index(right) + 1))
        self.assertTrue(self.app.quiz.next_timer.isActive())
        self.assertEqual(self.app.quiz.choices[right].role, "right_bg")

    def test_easy_reveal(self):
        """лёгкий уровень: после ошибки верный орган подсвечен и подписан, верный ответ подсказку убирает;
        на среднем уровне подсказки нет"""
        self.app.set_mode("find")
        self.app.quiz.set_cfg("level", "easy")
        self.app.quiz.start()
        s = self.app.quiz.session
        asked = s.current
        self.app.quiz.answer(next(k for k in self.app.organs() if k != asked))
        self.assertIsNotNone(self.app.view.layers["reveal"])
        self.assertEqual(self.app.view.pin[2], i18n.name(asked))
        self.assertTrue(self.app.reveal_timer.isActive())
        self.app.quiz.answer(asked)
        self.assertIsNone(self.app.view.pin)
        self.app.set_mode("find")
        self.app.quiz.set_cfg("level", "medium")
        self.app.quiz.start()
        s = self.app.quiz.session
        self.app.quiz.answer(next(k for k in self.app.organs() if k != s.current))
        self.assertIsNone(self.app.view.pin)

    def test_give_up(self):
        """«Сдаться»: ошибка засчитана, верный орган подписан на схеме, игра сразу заканчивается - итоги"""
        self.app.set_mode("find")
        self.app.quiz.set_cfg("length", 5)
        self.app.quiz.start()
        s = self.app.quiz.session
        self.app.quiz.answer(s.current)                          # первый вопрос - верно
        asked = s.current
        next(b for b in self.buttons(self.app.card) if b.text() == i18n.t("give_up")).invoke()
        self.assertTrue(s.finished)
        self.assertEqual((s.total, s.planned, s.errors, s.first_try, s.missed), (2, 5, 1, 1, [asked]))
        self.assertEqual(self.app.view.pin[2], i18n.name(asked))
        self.app.quiz.show_results()
        self.assertIn(i18n.t("results_gave_up", n=2, total=5), self.label_texts())

    def label_texts(self):
        from PySide6.QtWidgets import QLabel
        return [w.text() for w in self.app.card.findChildren(QLabel)]

    def test_quiz_progress_bars(self):
        """шапка вопроса: шкала пройденных вопросов и шкала таймера; цифра - значок на кнопке варианта"""
        self.app.set_mode("name")
        self.app.quiz.set_cfg("timer", 10)
        self.app.quiz.start()
        p = self.app.quiz.progress
        self.assertEqual(p.done.value, 0)
        self.assertFalse(p.time.isHidden())
        self.assertGreater(p.time.value, 0.5)
        self.assertEqual([b.key_hint for b in self.app.quiz.choices.values()],
                         [str(i + 1) for i in range(len(self.app.quiz.choices))])
        s = self.app.quiz.session
        self.app.quiz.pick(s.correct())
        self.app.quiz.next_question()
        self.assertAlmostEqual(self.app.quiz.progress.done.value, 1 / s.total)

    def test_quiz_mode_on_setup_card(self):
        """вид викторины выбирается на карточке настройки и запоминается для кнопки «Викторина»"""
        from organism_atlas import settings
        self.app.mode_buttons["quiz"].invoke()
        self.assertEqual(self.app.mode, "find")
        next(b for b in self.buttons(self.app.card) if b.text() == i18n.t("mode_facts")).invoke()
        self.assertEqual(self.app.mode, "facts")
        self.assertEqual(settings.load()["quiz_mode"], "facts")
        self.app.set_mode("study")
        self.app.mode_buttons["quiz"].invoke()
        self.assertEqual(self.app.mode, "facts")

    def test_card_history(self):
        """назад и вперёд по просмотренным карточкам; переход в сторону обрезает «вперёд»"""
        a = self.app
        for key in ("heart", "lungs", "liver"):
            a.open_link(key)
        self.assertEqual((a.cards.items, a.cards.pos), (["heart", "lungs", "liver"], 2))
        a.go_history(-1)
        self.assertEqual((a.cards.pos, a.spot), (1, "lungs"))
        a.go_history(-1)
        a.go_history(-1)                                    # дальше назад некуда
        self.assertEqual(a.cards.pos, 0)
        a.go_history(1)
        self.assertEqual(a.cards.items[a.cards.pos], "lungs")
        a.open_link("brain")
        self.assertEqual(a.cards.items, ["heart", "lungs", "brain"])
        self.assertIn("←", self.button_texts())
        a.set_mode("find")
        self.assertEqual(a.cards.items, [])

    def test_system_toggle_and_layers_fold(self):
        """щелчок по системе скрывает и показывает её органы; раздел «Слои» сворачивается и это запоминается"""
        from organism_atlas import settings
        a = self.app
        keys = set(dict(a.groups())["digestive"])
        a.toggle_system("digestive")
        self.assertEqual(a.hidden, keys)
        a.toggle_organ("liver")
        a.toggle_system("digestive")                        # часть скрыта - показать все
        self.assertEqual(a.hidden, set())
        a.fold_layers()
        self.assertTrue(a.toggles["skin"].isHidden())
        self.assertEqual(settings.load()["layers_panel"], "closed")
        a.fold_layers()
        pump()                                              # новые виджеты панели показываются в цикле событий
        self.assertFalse(a.toggles["skin"].isHidden())

    def test_skin_opacity(self):
        from organism_atlas.ui.layers_panel import SKIN
        a = self.app
        a.toggles[SKIN].setValue(100)
        a.apply_skin()
        self.assertEqual(a.atlas.skin_opacity, 0.0)
        a.toggle_layer("skin")                              # кожа выключена - ползунок прячется
        self.assertTrue(a.toggles[SKIN].isHidden())

    def test_zoom(self):
        """приближение: точка под курсором остаётся на месте, наведение попадает в тот же орган;
        схема всегда под всем окном, а при сильном приближении интерфейс уезжает и возвращается"""
        from PySide6.QtCore import QPointF
        from organism_atlas.ui.scheme_view import HIDE_FROM, ZOOM_STEPS
        a, v = self.app, self.app.view
        self.assertEqual(v.geometry(), a.rect())
        x, y = int(210 * Z), int(230 * Z)                   # сердце в пикселях схемы
        v.zoom_step(1)                                      # чуть приближенная - интерфейс на месте
        v.finish()
        self.assertLess(v.k, HIDE_FROM)
        self.assertFalse(a.ui_hidden)
        self.assertTrue(a.header.isVisible() and a.card_area.isVisible())
        v.zoom_to(ZOOM_STEPS[-2])                           # схема выше окна: по высоте у краёв не упирается
        v.finish()
        at = QPointF(*v.to_screen(x, y))
        v.zoom_step(1, at)
        v.finish()
        self.assertGreater(v.k, 1)
        sx, sy = v.to_screen(x, y)
        self.assertAlmostEqual(sy, at.y(), delta=1)
        # по ширине схема уже окна: не сдвигается за край, пока помещается целиком
        self.assertTrue(0 <= v.pan.x() <= v.width() - v.scheme.width() * v.k)
        self.assertEqual(a.atlas.organ_at(*v.to_scheme(QPointF(sx, sy))), "heart")
        self.assertTrue(a.stage.zoom_buttons["zoom_reset"].isEnabled())
        self.assertTrue(a.ui_hidden)                        # сильно приближенная - интерфейс уехал
        self.assertTrue(wait(lambda: not a.ghosts))
        self.assertFalse(a.header.isVisible() or a.panel.isVisible() or a.card_area.isVisible())
        a.on_key("", "0")
        v.finish()
        self.assertEqual(v.k, 1)
        self.assertEqual(v.pan, v.home())
        self.assertFalse(a.stage.zoom_buttons["zoom_reset"].isEnabled())
        self.assertTrue(wait(lambda: not a.ghosts))
        self.assertTrue(a.header.isVisible() and a.panel.isVisible() and a.card_area.isVisible())

    def test_help_and_search_keys(self):
        from organism_atlas.ui import help, overlay
        from organism_atlas.ui.layers_panel import SEARCH
        self.app.focus_search()
        self.assertTrue(self.app.toggles[SEARCH].hasFocus() or not self.app.isActiveWindow())
        self.app.show_help()
        self.assertIsInstance(overlay.top(self.app), help.HelpPanel)
        self.assertIs(help.show_help(self.app), overlay.top(self.app))

    def test_home_card(self):
        """стартовая карточка: орган дня открывает свою карточку"""
        texts = self.button_texts()
        opener = next(t for t in texts if t.startswith(i18n.t("home_organ_open", name="")))
        next(b for b in self.buttons(self.app.card) if b.text() == opener).invoke()
        self.assertEqual(len(self.app.cards.items), 1)

    def test_hide_all_organs(self):
        """кнопка в заголовке органов скрывает все органы, повторно - возвращает"""
        from organism_atlas.ui.layers_panel import ORGANS_ALL
        button = self.app.toggles[ORGANS_ALL]
        self.app.toggle_organ("heart")
        button.click()
        self.assertEqual(self.app.atlas.hidden, set(ORGANS))
        self.assertIsNone(self.app.atlas.organ_at(int(210 * Z), int(230 * Z)))
        self.assertEqual(button.text(), i18n.t("layers_show_organs"))
        self.assertFalse(any(self.app.toggles[k].on for k in self.app.organs()))
        button.click()
        self.assertEqual(self.app.atlas.hidden, self.other)
        self.assertEqual(button.text(), i18n.t("layers_hide_organs"))

    def test_panel_only_in_study(self):
        """в викторине панели слоёв нет, а схема стоит на месте и не перерисовывается"""
        pump()
        x = self.app.view.mapTo(self.app, self.app.view.rect().topLeft()).x()
        for mode in ("find", "name", "facts", "mix"):
            self.app.set_mode(mode)
            pump()
            self.assertFalse(self.app.panel.isVisible(), mode)
            self.assertEqual(self.app.view.mapTo(self.app, self.app.view.rect().topLeft()).x(), x, mode)
            self.assertTrue(self.app.ready(), mode)
        self.app.set_mode("study")
        pump()
        self.assertTrue(self.app.panel.isVisible())
        self.assertEqual(self.app.view.mapTo(self.app, self.app.view.rect().topLeft()).x(), x)

    def buttons(self, widget):
        from organism_atlas.ui.widgets import RoundButton
        pump()                                              # новые виджеты показываются в цикле событий
        return [b for b in widget.findChildren(RoundButton) if not b.isHidden()]

    def test_setup_buttons(self):
        """каждая кнопка карточки настройки меняет свою настройку, а не настройку последней строки"""
        def press(text):
            for b in self.buttons(self.app.card):
                if b.text() == text:
                    return b.click()
            self.fail(text)
        self.app.set_mode("name")
        pump()
        before = self.app.card.findChildren(QWidget)
        press(i18n.t("level_hard"))
        press(i18n.t("timer_sec", sec=10))
        press("5")
        self.assertEqual((self.app.quiz.cfg["level"], self.app.quiz.cfg["timer"], self.app.quiz.cfg["length"]), ("hard", 10, 5))
        self.assertEqual(self.app.quiz.cfg["set"], "all")
        self.assertEqual(self.app.card.findChildren(QWidget), before)       # обновлена на месте: не мигает
        self.app.set_mode("facts")                                          # другой режим - та же раскладка
        self.assertEqual(self.app.card.findChildren(QWidget), before)

    def test_panels_inside_window(self):
        """настройки, 3D и справочник болезней - панели внутри главного окна, а не отдельные окна;
        Esc закрывает верхнюю"""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from organism_atlas.ui import overlay, settings_window, viewer3d
        from organism_atlas.ui.diseases import show_diseases
        settings_window.show_settings(self.app)
        viewer3d.show_3d(self.app, "heart")
        guide = show_diseases(self.app)
        pump()
        self.assertEqual([w for w in self.qt.topLevelWidgets() if w.isVisible()], [self.app])
        for panel in (settings_window._window.win, viewer3d._viewer.win, guide):
            self.assertIsInstance(panel, overlay.Panel)
            self.assertIs(panel.parent(), self.app)
            self.assertTrue(panel.isVisible())
            self.assertTrue(self.app.rect().contains(panel.geometry().center()))
        self.app.set_mode("name")                                          # цифры не уходят викторине за панелью
        self.assertNotIn(guide, overlay.stack(self.app))                   # справочник в викторине закрывается
        self.app.quiz.start()
        self.app.on_key("", "1")
        self.assertEqual(self.app.quiz.session.errors + self.app.quiz.session.i, 0)
        self.assertFalse(self.app.quiz.next_timer.isActive())
        for left in (1, 0):
            QTest.keyClick(self.app, Qt.Key_Escape)
            pump()
            self.assertEqual(len(overlay.stack(self.app)), left)
        self.assertIsNone(settings_window._window)
        self.assertIsNone(viewer3d._viewer)

    def test_button_fade(self):
        """наведение меняет цвет кнопки плавно и доходит до цвета состояния"""
        b = self.app.mode_buttons["quiz"]
        pump()
        start = b.shown
        b.hover = True
        b.fade()
        self.assertIsNotNone(b.anim)
        self.assertTrue(wait(lambda: b.anim is None, 2))
        self.assertEqual(b.shown, b.colors())
        self.assertNotEqual(b.shown, start)
        b.hover = False
        b.retheme()                                        # смена темы - сразу, без перехода
        self.assertIsNone(b.anim)
        self.assertEqual(b.shown, b.colors())

    def visible_toggles(self):
        """органы, строки которых сейчас в списке панели слоёв"""
        pump()
        return {k for k in self.app.organs() if not self.app.toggles[k].isHidden()}

    def test_search(self):
        """поиск оставляет в панели подходящие органы, единственный найденный подсвечен, Enter открывает карточку"""
        from organism_atlas.ui.layers_panel import NOTHING, SEARCH
        box = self.app.toggles[SEARCH]
        self.app.toggle_organ("heart")
        box.setText("сердц")                                # «серд» - ещё и сердечно-сосудистая система
        self.assertEqual(self.visible_toggles(), {"heart"})
        self.assertEqual(self.app.spot, "heart")
        self.assertNotIn("heart", self.app.hidden)          # найденный скрытый орган снова виден
        self.assertIsNotNone(self.app.view.layers["target"])
        box.setText("почеч")                                # системы «мочевыделительная» нет - ничего
        box.setText("ж")
        self.assertGreater(len(self.visible_toggles()), 1)
        self.assertIsNone(self.app.spot)
        box.setText("zzz")
        self.assertEqual(self.visible_toggles(), set())
        self.assertFalse(self.app.toggles[NOTHING].isHidden())
        box.setText("Hepar")
        box.returnPressed.emit()
        self.assertEqual(self.app.spot, "liver")
        self.app.set_lang("en")                             # панель пересобрана, поиск остался
        self.assertEqual(self.app.toggles[SEARCH].text(), "Hepar")
        self.assertEqual(self.visible_toggles(), {"liver"})
        self.app.set_lang("ru")
        self.app.set_mode("find")                            # в викторине подсветки поиска нет
        self.assertIsNone(self.app.view.layers["target"])
        self.app.set_mode("study")
        self.assertEqual(self.app.query, "")
        self.assertEqual(self.visible_toggles(), set(self.app.organs()))

    def test_search_keeps_keys(self):
        """пока набирают в поиске, цифры и стрелки не уходят викторине и экскурсии; Esc очищает поле"""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from organism_atlas.ui.layers_panel import SEARCH
        self.app.tours.start("food")
        box = self.app.toggles[SEARCH]
        self.app.activateWindow()
        box.setFocus()
        pump()
        QTest.keyClicks(box, "hear")
        QTest.keyClick(box, Qt.Key_Right)                   # курсор в строке, а не шаг экскурсии
        self.assertEqual(self.app.tours.tour, ("food", 0))
        QTest.keyClick(box, Qt.Key_Return)                  # Enter - карточка найденного органа, экскурсия на паузе
        self.assertEqual(self.app.tours.paused, ("food", 0))
        self.assertEqual(self.app.spot, "heart")
        QTest.keyClick(box, Qt.Key_Escape)
        self.assertEqual(box.text(), "")

    def test_tour(self):
        """экскурсия: вступление, шаги с подсветкой органа, стрелки, конец и викторина по теме"""
        from organism_atlas import tours
        keys = tours.steps("food", self.app.body)
        self.app.tours.start("food")
        self.assertIsNone(self.app.spot)
        self.app.on_key("Right", "")
        self.assertEqual(self.app.spot, keys[0])
        self.assertIsNotNone(self.app.view.layers["target"])
        self.app.on_key("Left", "")
        self.assertEqual(self.app.tours.tour, ("food", 0))
        for _ in range(len(keys) + 3):                      # дальше конца не уходит
            self.app.tours.go(1)
        self.assertEqual(self.app.tours.tour, ("food", len(keys) + 1))
        self.assertIsNone(self.app.spot)
        self.app.set_lang("en")                              # карточка шага перерисовалась на другом языке
        self.app.set_lang("ru")
        self.app.tours.quiz("digestive")
        self.assertEqual((self.app.mode, self.app.quiz.cfg["topic"]), ("mix", "digestive"))
        self.assertIsNone(self.app.tours.tour)
        self.app.set_mode("study")
        self.app.tours.start("air")
        self.app.tours.go(2)
        self.app.on_click(int(210 * Z), int(230 * Z))       # щелчок по органу - пауза
        self.assertIsNone(self.app.tours.tour)
        self.assertEqual(self.app.tours.paused, ("air", 2))
        self.assertIn(i18n.t("tour_resume", title=tours.title("air")), self.button_texts())
        self.app.tours.resume()                               # вернулись на тот же шаг
        self.assertEqual(self.app.tours.tour, ("air", 2))
        self.assertEqual(self.app.spot, tours.steps("air", self.app.body)[1])
        self.app.tours.end()
        self.app.on_click(int(210 * Z), int(230 * Z))       # без экскурсии - к списку
        self.assertIn(i18n.t("tours_back"), self.button_texts())

    def button_texts(self):
        """надписи кнопок в карточке справа"""
        return [b.text() for b in self.buttons(self.app.card)]

    def test_achievements_after_game(self):
        from PySide6.QtWidgets import QLabel

        from organism_atlas.ui import achievements as panel, overlay
        self.app.set_mode("find")
        self.app.quiz.set_cfg("length", 5)
        self.app.quiz.start()
        self.play()
        self.assertEqual(self.app.quiz.new_achievements, ["first", "perfect"])
        self.assertEqual(self.app.quiz.streak, 1)
        self.assertEqual(self.app.ach_button.text(), i18n.t("ach_button", got=2, total=12))
        self.app.quiz.show_results()                             # итоги - в карточке справа, а не панелью поверх
        self.assertIsNone(overlay.top(self.app))
        texts = self.button_texts()
        self.assertEqual(texts[0], i18n.t("results_again"))
        self.assertIn(i18n.t("results_achievements"), texts)
        self.assertTrue(any(w.text() == i18n.t("results_score", right=5, total=5)
                            for w in self.app.card.findChildren(QLabel)))
        self.app.set_lang("en")                                 # итоги перерисовались на другом языке
        self.assertEqual(self.button_texts()[0], "Play again")
        self.app.set_lang("ru")
        self.buttons(self.app.card)[-1].invoke()                # «Изменить настройки игры»
        self.assertIn(i18n.t("setup_start"), self.button_texts())
        p = panel.show_achievements(self.app)
        self.assertIs(panel.show_achievements(self.app), p)            # вторая не открывается
        pump()
        self.assertTrue(p.isVisible())
        p.close_panel()

    def test_3d_parts(self):
        """у мозга три части: список под кадром, подпись под курсором, скрытие и «Найди часть»"""
        from PySide6.QtCore import QPointF

        from organism_atlas.ui import viewer3d
        viewer3d.show_3d(self.app, "brain")
        v = viewer3d._viewer
        self.assertTrue(wait(lambda: v.ids is not None, 60))
        self.assertEqual([n for _, n, _ in v.names], ["Ствол мозга", "Мозжечок", "Большие полушария"])
        self.assertFalse(v.parts_card.isHidden())
        cortex = 2
        ys, xs = (v.ids == cortex).nonzero()
        ih, iw = v.ids.shape
        x, y = (xs[len(xs) // 2] + 0.5) * v.w / iw, (ys[len(ys) // 2] + 0.5) * v.h / ih
        self.assertEqual(v.part_at(x, y), cortex)
        v.hover(QPointF(x, y))
        self.assertEqual(v.view.tip[2], "Большие полушария")
        widgets = v.parts_card.findChildren(QWidget)
        v.toggle_part(cortex)
        self.assertEqual(v.hidden, {cortex})
        self.assertFalse(v.part_toggles[cortex].on)
        self.assertEqual(v.parts_card.findChildren(QWidget), widgets)       # обновлено на месте, не мигает
        v.toggle_quiz()                                      # викторина: все части снова видны
        self.assertEqual(v.hidden, frozenset())
        target = v.quiz["order"][0]
        v.ids = v.ids.copy()
        v.ids[:] = target                                     # щелчок куда угодно попадает в нужную часть
        v.quiz_click(1, 1)
        self.assertEqual((v.quiz["i"], v.quiz["right"]), (1, 1))
        v.ids[:] = v.quiz["order"][2]                         # не та часть - ошибка
        v.quiz_click(1, 1)
        self.assertTrue(v.quiz["slipped"])
        self.assertIn("Попробуй ещё", v.note.text())
        self.assertEqual(v.parts_card.findChildren(QWidget), widgets)
        viewer3d.show_3d(self.app, "bladder")                 # одна часть - списка нет
        self.assertTrue(v.parts_card.isHidden())
        self.assertIsNone(v.quiz)
        v.win.close_panel()
        self.assertIsNone(viewer3d._viewer)

    def test_3d_rotation(self):
        """вращение мышью: кадр меняется, после отпускания - чистый кадр текущего вида"""
        from PySide6.QtCore import QPointF

        from organism_atlas.ui import viewer3d
        v = viewer3d.show_3d(self.app, "heart")
        self.assertTrue(wait(lambda: v.ids is not None and not v.gpu_timer.isActive(), 60))
        first = v.view.image
        v.press(QPointF(100, 100))
        v.drag(QPointF(160, 110))
        self.assertTrue(v.moved)
        self.assertNotEqual(v.az, -62.0)
        v.release(QPointF(160, 110))
        self.assertTrue(wait(lambda: v.view.image is not first and not v.gpu_timer.isActive()
                             and (v.gpu or v.q.empty()), 60))
        self.assertEqual(v.view.image.width(), round(v.w * v.dpr))
        v.win.close_panel()

    def test_muscles_layer(self):
        """мышцы по умолчанию скрыты, флажок их показывает; «Показать всё» мышцы не трогает"""
        self.assertNotIn("muscles", self.app.atlas.visible)
        self.assertFalse(self.app.toggles["muscles"].on)
        self.app.toggle_layer("muscles")
        self.assertIn("muscles", self.app.atlas.visible)
        self.assertFalse(self.app.something_hidden())        # мышцы - добавка, а не «что-то скрыто»
        self.app.toggle_layer("skeleton")
        self.assertTrue(self.app.something_hidden())
        self.app.show_all()
        self.assertIn("muscles", self.app.atlas.visible)
        self.assertIn("skeleton", self.app.atlas.visible)

    def test_first_scheme_from_prebuilt(self):
        """первая схема - готовая из сборки другого масштаба (растянутая), следом рисуется точная"""
        from organism_atlas import atlas_cache
        from organism_atlas.ui import app
        atlas_cache.save(0.65, self.app.atlas.body, self.app.atlas.org, self.pre)
        for f in os.listdir(self.tmp.name):                 # точной схемы в кэше пользователя ещё нет
            if f.startswith("atlas-"):
                os.remove(os.path.join(self.tmp.name, f))
        win = app.App()
        self.addCleanup(win.deleteLater)
        self.addCleanup(win.close)
        win.show()
        self.assertTrue(wait(lambda: win.atlas is not None))
        self.assertEqual(win.atlas.Z, 0.65)
        self.assertFalse(win.ready())                       # растянутая: наведение и клики ждут точную
        self.assertTrue(wait(win.ready))
        self.assertEqual(win.atlas.Z, Z)
        self.assertIsNone(win.view.message)

    def test_animation(self):
        """кусок с сердцем и лёгкими поверх схемы; не рисуется, когда выключен, открыта панель или окно неактивно"""
        from organism_atlas.ui import settings_window
        with mock.patch.object(self.app, "isActiveWindow", return_value=False):
            self.app.animate()
        self.assertIsNone(self.app.view.layers["anim"])
        self.app.activateWindow()
        pump()
        self.app.animate()
        layer = self.app.view.layers["anim"]
        self.assertIsNotNone(layer)
        self.assertEqual(layer[1:], self.app.atlas.anim_box()[:2])
        settings_window.show_settings(self.app)              # поверх панель - не рисуем
        self.app.animate()
        self.assertIsNone(self.app.view.layers["anim"])
        settings_window._window.win.close_panel()
        self.app.set_animation("off")
        self.app.animate()
        self.assertIsNone(self.app.view.layers["anim"])
        self.app.set_animation("on")
        self.app.toggle_organ("heart")
        self.app.toggle_organ("lungs")                       # оба скрыты - анимировать нечего
        self.app.animate()
        self.assertIsNone(self.app.view.layers["anim"])

    def test_repaints_only_changed_part(self):
        """кадр анимации и наведение перерисовывают только свой кусок схемы: панель слоёв и карточка поверх схемы
        не перерисовываются (раньше каждый кадр перерисовывал всё окно)"""
        from PySide6.QtCore import QEvent, QObject

        class Paints(QObject):
            def __init__(self):
                super().__init__()
                self.seen = []

            def eventFilter(self, obj, e):
                if e.type() == QEvent.Paint:
                    self.seen.append(obj)
                return False

        pump(0.2)
        a = self.app
        anim, hover = Paints(), Paints()
        self.qt.installEventFilter(anim)
        try:
            with mock.patch.object(a, "isActiveWindow", return_value=True):
                for _ in range(3):
                    a.animate()
                    pump()
        finally:
            self.qt.removeEventFilter(anim)
        self.qt.installEventFilter(hover)
        try:
            self.hover_heart()
            pump()
            a.on_leave()
            pump()
        finally:
            self.qt.removeEventFilter(hover)
        self.assertIn(a.view, anim.seen)
        for w in (a.panel, a.card, a.header):
            self.assertNotIn(w, anim.seen)
        self.assertIn(a.view, hover.seen)
        for w in (a.panel, a.header):                       # подсказка у курсора в узком окне может задеть карточку
            self.assertNotIn(w, hover.seen)

    def test_resize_after_hover(self):
        """после наведения окно поменяло размер: схема перерисовалась, подсветка работает"""
        self.hover_heart()
        self.zoom = 0.6
        self.app.on_resize()
        self.assertFalse(self.app.ready())
        self.assertEqual(self.app.view.message[1], True)    # «перерисовывается» внизу схемы
        self.app.start_build()                              # не ждём паузу после растягивания
        self.wait()
        self.assertEqual(self.app.atlas.Z, 0.6)
        self.assertIsNone(self.app.view.message)
        self.hover_heart()

    def test_theme_and_settings_apply_and_persist(self):
        """настройки: тема перекрашивает окно на лету, язык меняет тексты, выбор сохраняется"""
        from organism_atlas import settings, theme
        from organism_atlas.ui import settings_window, viewer3d
        a = self.app
        settings_window.show_settings(a)
        win = settings_window._window
        try:
            a.set_theme("light")
            self.assertEqual(theme.C["bg"], theme.THEMES["light"]["bg"])
            self.assertEqual(a.title.palette().windowText().color().name(), theme.THEMES["light"]["text"])
            self.assertEqual(a.mode_buttons["study"].colors()[0], theme.THEMES["light"]["accent"])
            a.set_lang("en")
            self.assertEqual(win.win.title(), "Settings")
            self.assertEqual(a.settings_button.toolTip(), "Settings")
            a.set_quality("high")
            self.assertEqual(viewer3d._quality, "high")
            before = win.card.findChildren(QWidget)
            a.open_link("heart")
            next(b for b in self.buttons(win.card) if b.text() == "Medium").click()    # как щелчок в панели
            self.assertEqual(win.card.findChildren(QWidget), before)           # обновлено на месте: не мигает
            next(b for b in self.buttons(win.card) if b.text() == "125%").click()
            pump()                                            # окно пересобирается в новом масштабе сразу
            from organism_atlas.ui.app import App
            from organism_atlas.ui.scaling import get_scale
            new = App.main
            self.assertIsNot(new, a)
            self.app = new                                    # закроет tearDown
            self.assertEqual(new.windowOpacity(), 0.0)        # пока схема рисуется, видно прежнее окно
            self.assertTrue(wait(lambda: new.windowOpacity() == 1.0))
            self.assertFalse(a.isVisible())
            self.assertEqual((new.ui_scale, get_scale()), (1.25, 1.25))
            self.assertEqual(new.cards.items, ["heart"])          # открытая карточка осталась
            win = settings_window._window                     # настройки снова открыты - уже в новом окне
            self.assertIsNotNone(win)
            self.assertIs(win.app, new)
            saved = settings.load()
            self.assertEqual({k: settings.get(saved, k) for k in settings.DEFAULTS},
                             {**settings.DEFAULTS, "theme": "light", "quality": "medium", "ui_scale": 1.25})
            self.assertEqual(saved["lang"], "en")
            win.win.close_panel()
            self.assertIsNone(settings_window._window)
        finally:
            theme.set_theme(theme.DEFAULT)
            viewer3d.set_quality("medium")


class ColorGroupTests(unittest.TestCase):
    """органы в панели слоёв идут группами по цвету"""

    def test_families(self):
        from organism_atlas.ui.layers_panel import color_family
        self.assertEqual(color_family("#ea9fb6")[0], 0)          # розовый
        self.assertEqual(color_family("#c8323a")[0], 1)          # красный
        self.assertEqual(color_family("#7b2f55")[0], 2)          # тёмно-красный
        self.assertEqual(color_family("#e8a77f")[0], 3)          # персиковый
        self.assertEqual(color_family("#5fa13f")[0], 4)          # зелёный
        self.assertEqual(color_family("#3060c0")[0], 5)          # синий - прочие

    def test_order_keeps_families_together(self):
        from organism_atlas.ui.layers_panel import by_color, color_family
        order = by_color(ORGANS)
        self.assertEqual(sorted(order), sorted(ORGANS))
        fams = [color_family(ORGANS[k]["color"])[0] for k in order]
        self.assertEqual(fams, sorted(fams))
        self.assertEqual(order[-3:], ["gallbladder", "trachea", "vena_cava"])   # зелёный, серо-голубая, синяя
        self.assertLessEqual(abs(order.index("lungs") - order.index("brain")), 2)    # оба розовые: рядом


class SystemGroupTests(unittest.TestCase):
    """органы в панели слоёв разбиты на группы по главной системе"""

    def test_groups(self):
        from organism_atlas.organs import PANEL_SYSTEMS, by_system
        groups = dict(by_system(list(ORGANS)))
        self.assertEqual(sorted(k for ks in groups.values() for k in ks), sorted(ORGANS))
        self.assertEqual(list(groups), [s for s in PANEL_SYSTEMS if s in groups])
        self.assertEqual(groups["respiratory"], ["lungs", "diaphragm", "trachea"])
        self.assertIn("pancreas", groups["digestive"])                   # главная система - первая
        self.assertEqual(groups["immune"], ["spleen", "thymus", "lymph_nodes"])
        self.assertEqual(groups["circulatory"], ["heart", "aorta", "vena_cava"])
        self.assertEqual(groups["nervous"], ["brain", "spinal_cord"])
        self.assertEqual(groups["urinary"], ["kidneys", "bladder"])


if __name__ == "__main__":
    unittest.main()


class QImageTests(unittest.TestCase):
    def test_native_formats(self):
        """картинки для экрана - в родных форматах Qt (их не надо перекодировать при каждой перерисовке),
        цвета и прозрачность те же"""
        from PIL import Image
        from PySide6.QtGui import QColor, QImage
        from organism_atlas.ui.widgets import qimage
        q = qimage(Image.new("RGB", (3, 2), (10, 200, 30)))
        self.assertEqual(q.format(), QImage.Format_RGB32)
        self.assertEqual(q.pixelColor(2, 1), QColor(10, 200, 30))
        q = qimage(Image.new("RGBA", (3, 2), (255, 0, 0, 255)))
        self.assertEqual(q.format(), QImage.Format_ARGB32_Premultiplied)
        self.assertEqual(q.pixelColor(0, 0), QColor(255, 0, 0, 255))
