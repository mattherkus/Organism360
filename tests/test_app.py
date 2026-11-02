"""Главное окно целиком: наведение, панель слоёв, викторины, панели, 3D. Окно на Qt без экрана (offscreen).
Схема рисуется в маленьком масштабе и в свою папку кэша, настройки и прогресс - во временные файлы."""

import os
import tempfile
import unittest
from unittest import mock

from PySide6.QtWidgets import QWidget

from tests.qt import app as qt_app, pump, wait

from organism_atlas import achievements, i18n, questions
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
        self.app.marks.flash("heart", "ok")
        self.app.toggle_organ("lungs")
        self.assertIsNone(self.app.view.layers["hover"])
        self.app.on_leave()
        self.hover_heart()
        self.app.show_all()
        self.app.marks.unflash()
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

    def test_diseases_disclaimer_sources_and_bone_links(self):
        """справочник: предупреждение на виду, у статьи - источники или «Где узнать больше» (внешние ссылки),
        ссылка на кость открывает её карточку в главном окне"""
        from unittest import mock
        from PySide6.QtWidgets import QLabel
        from organism_atlas.ui import diseases as panel_mod
        from organism_atlas.ui.overlay import top
        panel = panel_mod.show_diseases(self.app, "spinal_injury")
        self.assertIn(i18n.t("diseases_disclaimer"), panel.warn.text())
        texts = [w.text() for w in panel.card.findChildren(QLabel)]
        self.assertIn(i18n.t("disease_sources").upper(), texts)            # свои источники статьи
        self.assertIn(i18n.t("disease_more").upper(), texts)               # и общие сайты под ними
        self.assertIn(i18n.t("disease_unreviewed"), texts)
        urls = [w for w in panel.card.findChildren(QLabel) if 'href="https://' in w.text()]
        self.assertTrue(urls)
        with mock.patch.object(panel_mod, "QDesktopServices") as desk:
            urls[0].linkActivated.emit("https://www.who.int/ru")
            pump()
            self.assertEqual(desk.openUrl.call_args[0][0].toString(), "https://www.who.int/ru")
        self.assertIs(top(self.app), panel)                                  # внешняя ссылка справочник не закрывает
        spine = [w for w in panel.card.findChildren(QLabel) if 'href="spine"' in w.text()]
        self.assertEqual(len(spine), 1)
        spine[0].linkActivated.emit("spine")                                 # болезнь -> кость
        pump()
        self.assertIsNone(top(self.app))
        self.assertEqual((self.app.cards.current, self.app.spot), ("spine", "spine"))

    def test_latin_toggle(self):
        """кнопка «Латынь»: названия органов по-латыни, язык кнопок не меняется и запоминается"""
        from organism_atlas import settings
        self.app.set_lang("en")
        self.app.latin_action.trigger()
        self.assertTrue(i18n.latin())
        self.assertEqual(i18n.base(), "en")
        self.assertTrue(self.app.latin_action.isChecked())
        self.assertTrue(self.app.lang_actions["en"].isChecked())
        self.assertEqual(self.app.lang_button.text(), "English · Latina  ▾")    # язык полным названием и латынь
        self.assertEqual(self.app.toggles["heart"].text, "Cor")
        self.assertEqual(set(self.app.lang_actions), set(i18n.languages()))
        saved = settings.load()
        self.assertEqual((saved["lang"], saved["previous_lang"]), ("la", "en"))
        self.app.latin_action.trigger()
        self.assertFalse(i18n.latin())
        self.assertFalse(self.app.latin_action.isChecked())
        self.assertEqual(self.app.toggles["heart"].text, "Heart")
        self.assertEqual(self.app.lang_button.text(), "English  ▾")
        self.app.set_lang("ru")
        self.assertEqual(self.app.lang_button.text(), "Русский  ▾")

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
        self.app.marks.unflash()
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
        self.assertTrue(self.app.marks.reveal_timer.isActive())
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
        self.assertFalse(a.slide.hidden)
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
        self.assertTrue(a.slide.hidden)                        # сильно приближенная - интерфейс уехал
        self.assertTrue(wait(lambda: not a.slide.ghosts))
        self.assertFalse(a.header.isVisible() or a.panel.isVisible() or a.card_area.isVisible())
        a.on_key("", "0")
        v.finish()
        self.assertEqual(v.k, 1)
        self.assertEqual(v.pan, v.home())
        self.assertFalse(a.stage.zoom_buttons["zoom_reset"].isEnabled())
        self.assertTrue(wait(lambda: not a.slide.ghosts))
        self.assertTrue(a.header.isVisible() and a.panel.isVisible() and a.card_area.isVisible())

    def test_zoom_buttons_at_scheme_edge(self):
        """кнопки «+ − ⟲» - у правого края схемы уже при первом запуске (схема ещё без размера, когда окно
        впервые расставляет кнопки), а не посередине поверх неё"""
        from organism_atlas.ui.scaling import px
        a = self.app
        right = a.view.home().x() + min(a.view.scheme.width(), a.stage.width())      # шире места - у его края
        for i, b in enumerate(a.stage.zoom_buttons.values()):
            self.assertAlmostEqual(b.x(), right - px(38), delta=1)
            self.assertEqual(b.y() - a.stage.zoom_buttons["zoom_in"].y(), i * px(36))

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
        """справочник болезней, статистика и настройки - страницы-вкладки во всё окно под вкладками, 3D (как и
        достижения, горячие клавиши) - панель поверх; всё внутри главного окна, а не отдельными окнами.
        Открыта одна страница: новая заменяет прежнюю; панель поверх страницу не закрывает; Esc закрывает верхнее"""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from organism_atlas.ui import overlay, settings_window, stats, viewer3d
        from organism_atlas.ui.diseases import show_diseases
        from organism_atlas.ui.widgets import alive
        opened = []
        for show in (lambda: settings_window.show_settings(self.app) or settings_window._window.win,
                     lambda: show_diseases(self.app),
                     lambda: stats.show_stats(self.app),
                     lambda: show_diseases(self.app)):
            page = show()
            pump()
            self.assertEqual([w for w in self.qt.topLevelWidgets() if w.isVisible()], [self.app])
            self.assertIsInstance(page, overlay.Panel)
            self.assertTrue(page.page)
            self.assertIs(page.parent(), self.app)
            self.assertTrue(page.isVisible())
            self.assertEqual(page.geometry(), self.app.page_rect())           # во всё окно под вкладками
            self.assertEqual(overlay.stack(self.app), [page])                 # прежняя страница закрылась
            self.assertFalse(any(alive(p) and p.isVisible() for p in opened))
            opened.append(page)
        self.assertIsNone(settings_window._window)
        guide = opened[-1]
        view = viewer3d.show_3d(self.app, "heart").win                       # панель поверх страницы
        pump()
        self.assertFalse(view.page)
        self.assertTrue(self.app.rect().contains(view.geometry().center()))
        self.assertEqual(overlay.stack(self.app), [guide, view])
        QTest.keyClick(self.app, Qt.Key_Escape)                              # Esc - сначала панель поверх
        pump()
        self.assertEqual(overlay.stack(self.app), [guide])
        self.assertIsNone(viewer3d._viewer)
        self.app.set_mode("name")                                          # цифры не уходят викторине за страницей
        self.assertNotIn(guide, overlay.stack(self.app))                   # справочник в викторине закрывается
        settings_window.show_settings(self.app)
        self.app.quiz.start()
        self.app.on_key("", "1")
        self.assertEqual(self.app.quiz.session.errors + self.app.quiz.session.i, 0)
        self.assertFalse(self.app.quiz.next_timer.isActive())
        QTest.keyClick(self.app, Qt.Key_Escape)
        pump()
        self.assertEqual(overlay.stack(self.app), [])
        self.assertIsNone(settings_window._window)

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

    def test_bones_and_muscles_in_study(self):
        """где органа нет, а кость видна - наведение и клик ловят кость; её карточка - в истории карточек"""
        from organism_atlas.geometry import CX
        a = self.app
        x, y = int((CX + 82) * Z), int(245 * Z)                       # плечевая кость: органов и нервов там нет
        a.on_move(x, y)
        self.assertEqual(a.cur, "humerus")
        a.on_click(x, y)
        self.assertEqual(a.cards.current, "humerus")
        self.assertIn(i18n.name("humerus"), self.label_texts())
        a.toggle_layer("skeleton")                                     # кости скрыты, мышцы - тоже
        a.on_move(x, y)
        self.assertIsNone(a.cur)
        a.toggle_layer("muscles")
        a.on_click(x, y)
        self.assertEqual(a.cards.current, "biceps")
        a.open_link("spine")                                          # ссылка из текста на кость
        self.assertEqual((a.cards.current, a.spot), ("spine", "spine"))

    def test_body_quiz(self):
        """«Кости и мышцы»: органы скрыты, видны слои темы; верный щелчок по кости засчитывается"""
        import numpy as np
        from organism_atlas import structures
        a = self.app
        a.set_mode("body")
        self.assertEqual(a.hidden_now(), set(ORGANS))
        self.assertEqual(a.layers_now(), {"skin", "skeleton", "muscles"})
        a.quiz.set_cfg("topic", "bone")
        self.assertEqual(a.layers_now(), {"skin", "skeleton"})
        self.assertEqual(set(a.atlas.visible), {"skin", "skeleton"})
        a.quiz.start()
        s = a.quiz.session
        self.assertEqual(set(s.q) - set(structures.BONES), set())
        key = s.current
        d = a.atlas.structures()[key]
        ys, xs = np.nonzero(d["hit"] > 0.9)
        i = len(xs) // 2
        a.on_click(d["origin"][0] + xs[i], d["origin"][1] + ys[i])
        self.assertEqual(s.first_try, 1)
        self.assertEqual(s.results, {key: True})
        a.set_mode("study")                                           # в «Изучать» - снова выбранные слои
        self.assertEqual(set(a.atlas.visible), set(a.layers))

    def test_order_quiz(self):
        """«Расставь по порядку»: органы маршрута - кнопками и щелчками по схеме, ошибка отмечается"""
        import numpy as np
        a = self.app
        a.set_mode("order")
        a.quiz.cfg["level"] = "medium"
        a.quiz.start()
        s = a.quiz.session
        self.assertEqual(s.mode, "order")
        self.assertIn(i18n.t("progress_route", n=1, total=s.total, errors=0), a.quiz.progress_text())
        wrong = next(k for k in s.options() if k not in s.route())     # лишний орган среди кнопок
        a.quiz.pick(wrong)
        self.assertEqual(s.errors, 1)
        first = s.correct()
        d = a.atlas.org[first]                                          # первый орган - щелчком по схеме
        ys, xs = np.nonzero(d["hit"] > 0.9)
        for j in range(0, len(xs), max(1, len(xs) // 50)):
            x, y = d["origin"][0] + xs[j], d["origin"][1] + ys[j]
            if a.atlas.organ_at(x, y) == first:
                a.on_click(x, y)
                break
        self.assertEqual(s.placed, [first])
        while s.placed:                                                 # остальные - кнопками
            a.quiz.pick(s.correct())
        self.assertEqual(s.i, 1)
        self.assertTrue(a.quiz.next_timer.isActive())                   # пройденная цепочка видна, потом дальше

    def test_exam_quiz(self):
        """«Экзамен»: верно или нет - не видно, одна попытка, «Завершить» - итоги с оценкой и разбором"""
        a = self.app
        a.set_mode("exam")
        a.quiz.cfg["length"] = 5
        a.quiz.start()
        s = a.quiz.session
        self.assertEqual((s.total, s.total_time, s.timer), (5, 150, 0))
        while s.kind == "find":                                          # кнопка-вариант
            a.quiz.answer(s.correct())
            a.quiz.next_question()
        wrong = next(k for k in a.quiz.choices if k != s.correct())
        a.quiz.pick(wrong)
        self.assertEqual(a.quiz.choices, {})                             # второй попытки нет
        self.assertNotIn(i18n.t("answer_wrong", name=""), " ".join(self.label_texts()))
        a.quiz.next_question()
        a.quiz.give_up()                                                 # «Завершить экзамен»
        self.assertTrue(s.finished)
        self.assertEqual(s.total, 5)
        grade = i18n.t("grade_%d" % s.grade)
        self.assertTrue(wait(lambda: any(grade in x for x in self.label_texts()), 5))   # итоги - следом
        self.assertIn(i18n.t("review_title").upper(), self.label_texts())

    def test_daily_and_model_quiz(self):
        from organism_atlas.ui.turntable import Turntable
        a = self.app
        a.set_mode("daily")
        self.assertIn(i18n.t("daily_today_none"), " ".join(self.label_texts()))
        a.quiz.start()
        self.assertEqual((a.quiz.session.mode, a.quiz.session.total), ("daily", 10))
        a.set_mode("model")
        a.quiz.start()
        self.assertEqual(a.quiz.session.kind, "model")
        self.assertEqual(len(a.card.findChildren(Turntable)), 1)
        frames = a.quiz.frames[1]
        self.assertTrue(wait(lambda: frames.images))                    # первый кадр модели готов
        a.set_mode("study")
        self.assertIsNone(a.quiz.frames)                                # поток кадров остановлен

    def test_stats_panel_and_knowledge_map(self):
        """статистика: пусто до первой игры; после игр - графики и слабые места; карта знаний на схеме и K"""
        import random
        from organism_atlas import progress
        from organism_atlas.quiz import QuizSession
        from organism_atlas.ui import stats as panel_mod
        from organism_atlas.ui.overlay import top
        a = self.app
        p = panel_mod.show_stats(a)
        self.assertIn(i18n.t("stats_empty"), self.panel_texts(p))
        p.close_panel()
        keys = a.organs()
        for seed in range(3):
            s = QuizSession(keys, rng=random.Random(seed), pool=keys, mode="find", count=8)
            while not s.finished:
                if s.current == "liver" and not s.slipped:
                    s.answer("heart")
                s.answer(s.correct())
            progress.record(s)
        p = panel_mod.show_stats(a)
        self.assertTrue(p.findChildren(panel_mod.BarList) and p.findChildren(panel_mod.TrendChart))
        a.on_key("", "k")                                               # поверх открыта панель - клавиша не работает
        self.assertFalse(a.knowledge)
        p.toggle_map()                                                  # «Показать карту знаний»
        self.assertIsNone(top(a))
        self.assertTrue(a.knowledge)
        self.assertIsNotNone(a.view.layers["knowledge"])
        self.assertTrue(a.levels)
        a.set_mode("find")                                              # в викторине карты нет
        self.assertIsNone(a.view.layers["knowledge"])
        a.set_mode("study")
        self.assertIsNotNone(a.view.layers["knowledge"])
        a.on_key("", "k")
        self.assertFalse(a.knowledge)
        self.assertIsNone(a.view.layers["knowledge"])

    def test_train_weak_spots(self):
        a = self.app
        a.quiz.train(["liver", "heart"])
        self.assertEqual(a.mode, "mix")
        self.assertEqual(set(a.quiz.session.q), {"liver", "heart"})
        self.assertEqual(a.quiz.qset, "weak")

    def panel_texts(self, panel):
        from PySide6.QtWidgets import QLabel
        return [w.text() for w in panel.findChildren(QLabel)]

    def test_keyboard_selection(self):
        """без мыши: ↑ ↓ выбирают орган (подсветка и название), Enter открывает карточку;
        в «Найди орган» Enter отвечает выбранным органом, а названия рядом нет"""
        a = self.app
        a.on_key("Down", "")
        first = a.kb.keys()[0]
        self.assertEqual((a.kb.key, a.cur), (first, first))
        self.assertIsNotNone(a.view.layers["hover"])
        self.assertEqual(a.view.tip[2], i18n.name(first))
        a.on_key("Up", "")
        self.assertEqual(a.kb.key, a.kb.keys()[-1])                    # по кругу
        a.on_key("Return", "")
        self.assertEqual(a.cards.current, a.kb.key)
        a.toggle_organ("heart")
        self.assertNotIn("heart", a.kb.keys())                          # скрытые органы не выбираются
        a.set_mode("find")
        a.quiz.start()
        s = a.quiz.session
        target = s.current
        while a.kb.key != target:
            a.on_key("Down", "")
        self.assertIsNone(a.view.tip)
        a.on_key("Return", "")
        self.assertEqual(s.results.get(target), True)

    def test_read_aloud(self):
        """«Прочитать вслух»: кнопка есть, если есть голос; R читает открытую карточку, повторно - останавливает"""
        from organism_atlas import speech
        from organism_atlas.ui.cards import card_text
        said = []
        state = {"on": False}
        with mock.patch.object(speech, "available", return_value=True), \
                mock.patch.object(speech, "speak", side_effect=lambda text, lang: said.append((text, lang)) or
                                  state.update(on=True) or True), \
                mock.patch.object(speech, "speaking", side_effect=lambda: state["on"]), \
                mock.patch.object(speech, "stop", side_effect=lambda: state.update(on=False)):
            a = self.app
            a.show_info("heart")
            self.assertEqual(a.card.read_button.text(), i18n.t("card_read"))
            a.on_key("", "r")
            self.assertEqual(said, [(card_text("heart"), "ru")])
            self.assertIn(i18n.name("heart"), said[0][0])
            self.assertEqual(a.card.read_button.text(), i18n.t("card_read_stop"))
            a.on_key("", "к")                                           # та же клавиша в русской раскладке
            self.assertFalse(state["on"])
            self.assertEqual(a.card.read_button.text(), i18n.t("card_read"))
        with mock.patch.object(speech, "available", return_value=False):
            self.app.show_info("liver")
            self.assertIsNone(self.app.card.read_button)

    def test_update_button(self):
        """есть выпуск новее - в верхней панели кнопка «Новая версия», щелчок открывает его страницу"""
        from organism_atlas import updates
        info = {"version": "9.9.9", "url": "https://github.com/%s/releases/tag/v9.9.9" % updates.REPO}
        a = self.app
        self.assertTrue(a.update_check.button.isHidden())
        with mock.patch.object(updates, "due", return_value=True), \
                mock.patch.object(updates, "check", return_value=info):
            a.update_check.check()
            self.assertTrue(wait(lambda: not a.update_check.button.isHidden(), 5))
        self.assertEqual(a.update_check.button.text(), i18n.t("update_button", version="9.9.9"))
        with mock.patch("PySide6.QtGui.QDesktopServices.openUrl") as open_url:
            a.update_check.button.invoke()
            pump(0.1)
            self.assertEqual(open_url.call_args[0][0].toString(), info["url"])

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
        self.assertEqual(self.visible_toggles(), set())      # без поиска системы снова свёрнуты

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

    def test_tour_with_bones_and_muscles(self):
        """в маршруте экскурсии бывают кость и мышца: они подсвечиваются, а кнопки 3D у них нет"""
        from organism_atlas import tours
        self.assertEqual(tours.steps("nerve", self.app.body), ["phalanges", "spinal_cord", "brain", "biceps"])
        self.app.tours.start("nerve")
        self.app.tours.go(1)
        self.assertEqual(self.app.spot, "phalanges")
        self.assertIsNotNone(self.app.view.layers["target"])
        self.assertNotIn(i18n.t("card_3d"), self.button_texts())
        self.app.tours.go(1)                                  # спинной мозг - орган: 3D есть
        self.assertIn(i18n.t("card_3d"), self.button_texts())

    def test_flashcards(self):
        """флеш-карточки: колоды на стартовой карточке, пробел открывает ответ, 2 - «помню»; карточка органа
        во время подхода - с кнопкой вернуться к нему; в конце - итог и снова колоды"""
        from organism_atlas import progress
        deck_button = "▤  " + i18n.t("flash_deck_latin")
        self.assertIn(deck_button, self.button_texts())
        self.app.flash.start("latin")
        s = self.app.flash.session
        key = s.current
        self.assertEqual(self.app.spot, key)                  # латинские названия: орган подсвечен сразу
        self.assertIn(i18n.t("flash_show"), self.button_texts())
        self.app.on_key("", " ")                              # пробел - ответ
        self.assertTrue(s.shown)
        self.assertIn(i18n.t("flash_knew"), self.button_texts())
        self.app.on_key("", "2")                              # 2 - «помню»
        self.assertEqual(s.i, 1)
        self.assertEqual(progress.load()["cards"]["flash_latin:" + key]["box"], 1)
        self.app.on_click(int(210 * Z), int(230 * Z))         # щелчок по сердцу - его карточка
        self.assertEqual(self.app.cards.current, "heart")
        self.assertIn(i18n.t("flash_resume"), self.button_texts())
        self.app.flash.resume()
        self.assertEqual(self.app.card_fn, self.app.flash.card)
        while not s.finished:
            self.app.flash.reveal()
            self.app.flash.answer(False)
        self.assertIn(i18n.t("flash_again"), self.button_texts())
        self.assertEqual(self.app.spot, None)
        self.app.flash.end()
        self.assertIsNone(self.app.flash.session)
        self.assertIn(deck_button + "  ·  " + i18n.t("flash_due", n=len(s.keys) - 1), self.button_texts())

    def test_notes_and_bookmarks(self):
        """заметка под карточкой сохраняется сама, буквы в ней не нажимают горячие клавиши; закладка - на стартовой
        карточке и в наборе вопросов викторины"""
        from organism_atlas import notes
        a = self.app
        a.show_info("heart")
        box = a.card.note_box
        self.assertIsNotNone(box)
        a.activateWindow()
        box.setFocus()
        pump()
        box.setPlainText("Четыре камеры")
        a.on_key("", "k")                                    # набирают в заметке - карта знаний не включается
        self.assertFalse(a.knowledge)
        self.assertTrue(a.notes.timer.isActive())
        a.notes.flush()
        self.assertEqual(notes.note("heart"), "Четыре камеры")
        a.show_info("liver")
        a.show_info("heart")                                 # заметка снова на месте
        self.assertEqual(a.card.note_box.toPlainText(), "Четыре камеры")
        a.card.star_button.invoke()
        pump(0.1)
        self.assertEqual(a.card.star_button.text(), i18n.t("card_star_on"))
        self.assertEqual(notes.starred(), ["heart"])
        a.set_card(a.empty_card)                             # на стартовой карточке - закладки и викторина по ним
        self.assertIn(i18n.t("home_starred_quiz"), self.button_texts())
        a.notes.quiz()
        self.assertEqual((a.mode, a.quiz.qset), ("mix", "starred"))
        self.assertEqual(a.quiz.session.q, ["heart"])
        a.set_mode("find")
        a.quiz.set_cfg("set", "starred")
        self.assertIn(i18n.t("set_starred", n=1), self.button_texts())

    def test_onboarding(self):
        """подсказки первого запуска: пять шагов в рамках вокруг частей окна, клавиши листают, в конце -
        больше сами не показываются; из настроек - снова"""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from organism_atlas import settings
        from organism_atlas.ui import onboarding
        onboarding.maybe_start(self.app)
        coach = self.app.coach
        self.assertIsNotNone(coach)
        self.assertEqual(coach.geometry(), self.app.rect())
        self.assertIsNotNone(coach.hole())                    # схема - в рамке
        self.assertFalse(coach.bubble.geometry().intersects(coach.hole()))
        QTest.keyClick(coach, Qt.Key_Right)
        QTest.keyClick(coach, Qt.Key_Left)
        self.assertEqual(coach.i, 0)
        for _ in onboarding.STEPS[:-1]:
            QTest.keyClick(coach, Qt.Key_Return)
        self.assertIsNone(coach.hole())                       # последний шаг - по центру окна
        QTest.keyClick(coach, Qt.Key_Return)
        pump()
        self.assertIsNone(self.app.coach)
        self.assertEqual(settings.get(settings.load(), "onboarding"), "done")
        onboarding.maybe_start(self.app)                      # уже видели - сами не показываются
        self.assertIsNone(getattr(self.app, "coach", None))
        self.app.show_tips()                                  # кнопка в настройках
        self.assertIsNotNone(self.app.coach)
        QTest.keyClick(self.app.coach, Qt.Key_Escape)
        pump()
        self.assertIsNone(self.app.coach)

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
        self.assertEqual(self.app.ach_button.text(), i18n.t("ach_button", got=2, total=len(achievements.KEYS)))
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
            self.assertEqual(a.settings_button.colors()[0], theme.THEMES["light"]["accent"])   # вкладка панели
            self.assertFalse(a.mode_buttons["study"].selected())
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

    def test_fold_systems(self):
        """системы в списке органов сначала свёрнуты; стрелка разворачивает систему, у подзаголовка -
        сколько её органов видно; развёрнутое переживает пересборку панели"""
        from organism_atlas.ui.layers_panel import GROUPS
        a = self.app
        self.assertEqual(self.visible_toggles(), set())
        a.fold_system("circulatory")
        self.assertEqual(self.visible_toggles(), {"heart", "aorta", "vena_cava"})
        head = next(h for h in a.toggles[GROUPS] if h.system == "circulatory")
        self.assertEqual(head.count.text(), "3/3")
        a.toggle_organ("heart")
        self.assertEqual(head.count.text(), "2/3")
        a.set_lang("en")
        self.assertEqual(self.visible_toggles(), {"heart", "aorta", "vena_cava"})
        a.set_lang("ru")
        a.fold_system("circulatory")
        self.assertEqual(self.visible_toggles(), set())

    def test_results_on_scheme_and_toast(self):
        """итоги: кольцо доли верных с первой попытки, ошибки - красным на схеме с подписями (до следующей
        игры); новое достижение - плашкой внизу окна, щелчок по ней открывает достижения"""
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from organism_atlas.ui import overlay, toast
        from organism_atlas.ui.achievements import AchievementsPanel
        from organism_atlas.ui.widgets import Ring
        a = self.app
        a.set_mode("find")
        a.quiz.set_cfg("length", 5)
        a.quiz.start()
        s = a.quiz.session
        missed = s.current
        a.quiz.answer(next(k for k in a.organs() if k != missed))      # одна ошибка
        self.play()
        self.assertEqual(s.missed, [missed])
        shown = toast.toasts(a)
        self.assertEqual(len(shown), len(a.quiz.new_achievements))
        a.quiz.show_results()
        rings = a.card.findChildren(Ring)
        self.assertEqual(len(rings), 1)
        self.assertAlmostEqual(rings[0].value, s.percent / 100)
        self.assertIsNotNone(a.view.layers["missed"])
        self.assertEqual([text for *_xy, text in a.view.labels], [i18n.name(missed)])
        QTest.mouseClick(shown[0], Qt.LeftButton)
        self.assertTrue(wait(lambda: isinstance(overlay.top(a), AchievementsPanel), 2))
        overlay.close_top(a)
        a.quiz.start()                                          # новая игра - отметок прошлой нет
        self.assertIsNone(a.view.layers["missed"])
        self.assertEqual(a.view.labels, [])

    def test_header_tabs(self):
        """болезни, статистика и настройки - вкладки рядом с режимами: страница во всё окно вместо схемы, выбрана
        её вкладка; повторный щелчок её не закрывает; вкладка режима возвращает к схеме как было (карточка органа
        остаётся); в викторине вкладка «Болезни» недоступна"""
        from organism_atlas.ui import overlay
        a = self.app
        tabs = a.panel_tabs
        zoom = a.stage.zoom_buttons.values()
        a.show_info("heart")
        self.assertEqual(tabs["diseases"].text(), i18n.t("tab_diseases"))
        self.assertTrue(a.mode_buttons["study"].selected())
        for name, b in tabs.items():
            b.invoke()
            pump()
            self.assertEqual(a.open_tab(), name)
            self.assertEqual([n for n, x in tabs.items() if x.selected()], [name])
            self.assertFalse(a.mode_buttons["study"].selected())
            self.assertFalse(any(z.isVisible() for z in zoom))             # схема с её кнопками - под страницей
        tabs["settings"].invoke()                                         # та же вкладка - страница остаётся
        pump()
        self.assertEqual(a.open_tab(), "settings")
        a.mode_buttons["study"].invoke()                                  # назад к схеме - как было
        pump()
        self.assertIsNone(overlay.top(a))
        self.assertTrue(a.mode_buttons["study"].selected())
        self.assertFalse(any(b.selected() for b in tabs.values()))
        self.assertEqual(a.cards.current, "heart")
        self.assertTrue(all(z.isVisible() for z in zoom))
        a.set_mode("find")
        self.assertFalse(tabs["diseases"].isEnabled())
        self.assertTrue(a.mode_buttons["quiz"].selected())

    def test_card_fades_in(self):
        """новая карточка органа проявляется плавно, а после - без эффекта прозрачности"""
        a = self.app
        a.show_info("heart")
        self.assertIsNotNone(a.card.graphicsEffect())
        self.assertTrue(wait(lambda: a.card.graphicsEffect() is None, 2))


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
