"""Главное окно (Qt): схема тела, наведение, карточка органа, панель слоёв с поиском органа, режим «Изучать»
и викторина. Игру ведёт QuizController (quiz_controller.py), экскурсии - TourController (tour_controller.py),
флеш-карточки - FlashController (flash_controller.py), историю карточек - CardHistory (history.py), подсветку
на схеме - Marks (marks.py), выбор органа стрелками - KeyboardChoice (keyboard.py), чтение вслух - CardReader
(reader.py), кнопку новой версии - UpdateCheck (update_check.py), выезд интерфейса при приближении - UiSlide
(sliding.py); окно даёт им карточку справа и схему.
Схема подстраивается под размер окна: пока рисуется чёткая версия, показывается растянутая прежняя.
Схема рисуется в пикселях экрана: на экране с масштабом 150 % она в полтора раза подробнее, а не растянута.
Новая карточка справа проявляется плавно, а в итогах викторины органы-ошибки отмечены на схеме."""

import math
import queue
import threading
import time
import traceback
from datetime import date

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QLineEdit, QMenu, QPlainTextEdit,
                               QScrollArea, QWidget)

from .. import achievements, i18n, progress, settings, speech, stats, theme, tours
from ..colors import hex2rgb
from ..config import STATUS
from ..atlas import Atlas
from ..body.base import BODY_LAYERS, DEFAULT_LAYERS
from ..geometry import H, W
from ..i18n import t
from ..organs import ORGANS, PANEL_SYSTEMS, by_system, fact_of_day, for_body, other_sex, search
from ..quiz import MODES, NOT_ORGANS
from ..structures import KINDS, LAYER_OF, STRUCTURES
from . import overlay, titlebar, toast
from .achievements import button_text as achievements_text, show_achievements
from .diseases import close_diseases, refresh_diseases, show_diseases
from .scaling import fit_zoom, pick_zoom, px, set_scale
from .scheme_view import HIDE_FROM, ZOOM_STEPS, SchemeView, Stage
from . import settings_window
from .settings_window import refresh_settings, show_settings
from .viewer3d import rerender_all, retranslate_all, set_quality, show_3d
from .help import show_help as open_help
from .cards import fill_card, fill_start
from .flash_controller import FlashController
from .history import CardHistory
from .keyboard import KeyboardChoice
from .layers_panel import (ORGANS_ALL, SEARCH, SKIN, by_color, count_organs, fill_layers, filter_organs,
                           show_all_button)
from .marks import Marks
from .notes_ui import CardNotes
from .quiz_controller import QuizController, timer
from .reader import CardReader
from .sliding import UiSlide
from .stats import show_stats
from .tour_controller import TourController
from .update_check import UpdateCheck
from .widgets import (TabButton, alive, color, flat_button, font, hbox, label, qimage, retheme, rounded_card,
                      set_button_bg, vbox)

ANIM_MS = 60                    # кадр анимации сердца и лёгких (около 16 в секунду)
ANIM_IDLE_MS = 300              # проверка, не пора ли снова анимировать, пока анимация не видна
REBUILD_WAIT = 5                # сколько секунд ждать, пока пересобранное окно нарисует схему (смена масштаба)
CRUMBS = 2                      # сколько прежних карточек показывать «крошками» над карточкой органа
CARD_FADE_MS = 180              # новая карточка справа проявляется за столько миллисекунд
LATIN_TITLE = "Corpus humanum"  # подзаголовок окна - по-латыни на любом языке, как на титуле атласа


class App(QWidget):
    main = None                                 # окно на экране (после смены масштаба - пересобранное)

    def __init__(self, ui_scale=1.0, quality="medium"):
        """ui_scale - множитель масштаба из настроек (действует с запуска), quality - качество 3D"""
        super().__init__()
        self.host = self                       # панели (настройки, болезни, 3D) открываются поверх этого окна
        self.ui_scale = ui_scale
        App.main = self
        set_scale(ui_scale)
        self.quality = quality
        set_quality(quality)
        titlebar.set_icon(QApplication.instance())
        self.mode = "study"                    # study или режим викторины из quiz.MODES
        saved = settings.load()
        self.quiz = QuizController(self)       # игра: настройки, вопросы, таймер, итоги
        self.tours = TourController(self)      # экскурсии в режиме «Изучать»
        self.flash = FlashController(self)     # флеш-карточки в режиме «Изучать»
        self.notes = CardNotes(self)           # заметки и закладки на карточках
        self.cards = CardHistory()             # просмотренные карточки органов: «назад», «вперёд»
        self.marks = Marks(self)               # подсветка на схеме: под курсором, вопрос, верно/ошибка, итоги
        self.kb = KeyboardChoice(self)         # орган (кость, мышца), выбранный стрелками ↑ ↓ - без мыши
        self.reader = CardReader(self)         # чтение карточки вслух
        self.update_check = UpdateCheck(self)  # кнопка «Новая версия», если на GitHub есть выпуск новее
        self.slide = UiSlide(self)             # интерфейс уезжает к краям при сильном приближении схемы
        self.quiz_mode = settings.get(saved, "quiz_mode")     # вид викторины, который открывает кнопка «Викторина»
        self.layers_open = settings.get(saved, "layers_panel") == "open"   # раздел «Слои» развёрнут
        self.folded = set(PANEL_SYSTEMS)       # свёрнутые системы в списке органов (сначала - все)
        self.skin_clear = 0                    # прозрачность кожи, % (ползунок под строкой «Кожа»)
        self.body = settings.get(saved, "body")   # схема тела: female или male (органы малого таза)
        self.animation = settings.get(saved, "animation")      # on - сердце бьётся, лёгкие дышат
        self.atlas, self.cur = None, None
        # что сейчас в карточке и в строке статуса: функции, чтобы перерисовать их на другом языке
        self.card_fn = self.status_fn = None
        self.built = queue.Queue()
        self.building = False                  # в фоне рисуется схема (при запуске или под новый размер окна)
        self.layers = set(DEFAULT_LAYERS)      # видимые слои тела (мышцы включают в панели)
        self.hidden = set()                    # органы, скрытые в режиме «Изучать» (в викторине видны все)
        self.query = ""                        # строка поиска органа в панели слоёв
        self.spot = None                       # орган, подсвеченный в «Изучать»: найденный поиском или шаг экскурсии
        self.knowledge = False                 # карта знаний на схеме (органы в цвете уровня знания)
        self.levels = {}                       # {орган: уровень знания} для карты знаний и подсказки у курсора
        self.toggles = {}
        # отложенные действия
        self.skin_timer = timer(self, self.apply_skin, 40)
        self.resize_timer = timer(self, self.start_build, 400)
        self.anim_timer = timer(self, self.animate)
        self.build_timer = QTimer(self)
        self.build_timer.timeout.connect(self.poll_build)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(False)

        root = vbox(self, margins=(24, 18, 24, 0))
        top = hbox()
        # заголовок, как на титуле атласа: название шрифтом с засечками и латинский подзаголовок курсивом
        self.title = label("", size=20, bold=True, wrap=False, serif=True)
        top.addWidget(self.title, 0, Qt.AlignBottom)
        top.addSpacing(px(10))
        self.subtitle = label(LATIN_TITLE, "muted", 13, italic=True, wrap=False, serif=True)
        self.subtitle.setContentsMargins(0, 0, 0, px(3))                 # на одной линии с заголовком
        top.addWidget(self.subtitle, 0, Qt.AlignBottom)
        top.addSpacing(px(32))                           # заголовок не прилипает к кнопкам при узком окне
        top.addStretch(1)
        # вкладки: два режима - «Изучать» и «Викторина» (вид викторины выбирается на её карточке настройки),
        # а следом страницы - справочник болезней, статистика и настройки (во всё окно под вкладками, вместо
        # схемы). Выбрана вкладка открытой страницы, а без неё - режима
        self.mode_buttons = {"study": TabButton("", lambda: self.mode_tab("study")),
                             "quiz": TabButton("", lambda: self.mode_tab("quiz"))}
        self.panel_tabs = {name: TabButton("", lambda n=name, f=show: self.page_tab(n, f))
                           for name, show in (("diseases", lambda: show_diseases(self)),
                                              ("stats", lambda: show_stats(self)),
                                              ("settings", lambda: show_settings(self)))}
        self.diseases_button, self.stats_button, self.settings_button = self.panel_tabs.values()
        for i, b in enumerate([*self.mode_buttons.values(), *self.panel_tabs.values()]):
            top.addSpacing(px(10) if i else 0)
            top.addWidget(b, 0, Qt.AlignTop)
        top.addSpacing(px(24))
        # язык и латинские названия - одной кнопкой с меню
        self.lang_button = flat_button("", self.show_lang_menu, padx=10)
        self.lang_menu = QMenu(self)
        group = QActionGroup(self)
        self.lang_actions = {}
        for code in i18n.languages():
            a = self.lang_menu.addAction(i18n.language_name(code), lambda c=code: self.set_lang(c))
            a.setCheckable(True)
            group.addAction(a)
            self.lang_actions[code] = a
        self.lang_menu.addSeparator()
        self.latin_action = self.lang_menu.addAction("", lambda: self.set_latin(not i18n.latin()))
        self.latin_action.setCheckable(True)
        top.addWidget(self.lang_button, 0, Qt.AlignTop)
        self.ach_button = flat_button("", lambda: show_achievements(self), padx=10)
        for b in (self.update_check.button, self.ach_button):
            top.addSpacing(px(6))
            top.addWidget(b, 0, Qt.AlignTop)
        self.top_bar = top
        self.header = QWidget()                            # заголовок с кнопками и статус - уезжают вместе
        head = vbox(self.header)
        head.addLayout(top)
        # статус - отдельной строкой: длинный текст не должен теснить кнопки режимов
        self.status = label("", size=11, bold=True)
        self.status.setMinimumHeight(self.status.fontMetrics().lineSpacing())   # пустая не сдвигает схему
        head.addSpacing(px(8))
        head.addWidget(self.status)
        root.addWidget(self.header)

        body = hbox()
        root.addSpacing(px(10))
        root.addLayout(body, 1)
        root.addSpacing(px(10))
        left = vbox()
        self.panel = rounded_card()                        # панель слоёв; в викторине место за ней остаётся
        sp = self.panel.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.panel.setSizePolicy(sp)
        self.panel.setFixedWidth(px(214))
        left.addSpacing(px(10))
        left.addWidget(self.panel)
        left.addStretch(1)
        body.addLayout(left)
        body.addSpacing(px(20))
        self.view = SchemeView(self)
        self.view.setParent(self)                          # схема - под всем окном, раскладка - поверх неё
        self.view.lower()
        self.stage = Stage(self, self.view)
        body.addWidget(self.stage, 1)
        body.addSpacing(px(20))
        # карточка справа листается, если она выше окна
        self.card = rounded_card()
        self.card_area = QScrollArea()
        self.card_area.setFrameShape(QFrame.NoFrame)
        self.card_area.setWidgetResizable(True)
        self.card_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("scrollInner")
        self.card_area.setStyleSheet("QScrollArea, QWidget#scrollInner {background: transparent}")
        hl = vbox(holder)
        hl.addSpacing(px(10))
        hl.addWidget(self.card)
        hl.addStretch(1)
        self.card_area.setWidget(holder)
        body.addWidget(self.card_area)
        for w in (self.header, self.card_area):            # уехавшие при приближении держат место в раскладке
            sp = w.sizePolicy()
            sp.setRetainSizeWhenHidden(True)
            w.setSizePolicy(sp)

        # горячие клавиши, которые работают и при наборе в поиске
        for keys, command in ((QKeySequence.Find, self.focus_search), ("F1", self.show_help),
                              ("Alt+Left", lambda: self.go_history(-1)), ("Alt+Right", lambda: self.go_history(1))):
            QShortcut(QKeySequence(keys), self, command)

        self.want_Z = None                                 # масштаб схемы под текущий размер окна
        self.set_status(lambda: t("hint"))
        self.set_card(self.empty_card)
        self.retranslate()
        self.fix_card_width()
        self.fit_window()
        self.view.message = (t("loading"), False)
        self.anim_timer.start(ANIM_MS)

    def fix_card_width(self):
        """ширина карточки справа - один раз, по самой широкой (настройка викторины): иначе при смене режима
        колонка раздвигалась бы, а схема сдвигалась и меняла масштаб"""
        mode, wide = self.mode, px(340)
        for self.mode in MODES:
            self.quiz.render_setup()
            self.card.layout().activate()
            wide = max(wide, self.card.minimumSizeHint().width())
        self.mode = mode
        self.card_fn()
        self.card.setFixedWidth(wide)
        self.card_area.setFixedWidth(wide + px(12))

    def fit_window(self):
        """размер окна при запуске: схема как можно крупнее, но окно целиком на экране"""
        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        dpr = self.devicePixelRatioF()
        Z = pick_zoom(screen.width(), screen.height(), dpr)
        cw, ch = math.ceil(W * Z / dpr), math.ceil(H * Z / dpr)
        self.stage.hint = QSize(cw, ch)
        self.stage.updateGeometry()
        self.layout().activate()
        hint = self.sizeHint()
        w = min(hint.width(), int(0.96 * screen.width()))
        h = min(max(hint.height(), ch + px(150)), int(0.92 * screen.height()))
        self.resize(w, h)
        self.setMinimumSize(min(self.top_bar.minimumSize().width() + px(48), screen.width()), px(520))

    def showEvent(self, e):
        super().showEvent(e)
        if App.main is self and self.update_check.queue is None:   # проверка обновлений - один раз за запуск окна
            QTimer.singleShot(3000, self.update_check.check)
        titlebar.paint(self)
        self.setFocus()
        self.on_resize()                                 # схема начинает рисоваться, когда окно на экране

    # --- язык и настройки
    def set_lang(self, code):
        """язык текста (кнопки RU, EN); латинские названия остаются включёнными или выключенными"""
        i18n.set_base(code)
        settings.save(lang=i18n.current(), previous_lang=i18n.previous())
        self.retranslate()

    def set_latin(self, on):
        """кнопка «Латынь»: названия органов по-латыни, остальной текст - на выбранном языке"""
        i18n.set_latin(on)
        settings.save(lang=i18n.current(), previous_lang=i18n.previous())
        self.retranslate()

    def set_theme(self, name):
        """сменить тему на лету: перекрасить все окна, а карточки и тексты перерисовать"""
        theme.set_theme(name)
        settings.save(theme=theme.current())
        retheme()
        titlebar.set_icon(QApplication.instance())
        titlebar.paint(self)
        if self.atlas:
            self.paint_base()
        rerender_all()
        self.retranslate()

    def set_quality(self, name):
        self.quality = name
        set_quality(name)
        settings.save(quality=name)

    def set_updates(self, value):
        """проверять ли обновления (раз в день, в фоне)"""
        settings.save(updates=value)
        if value == "on":
            self.update_check.check()

    def set_animation(self, value):
        self.animation = value
        settings.save(animation=value)
        if value != "on":
            self.view.show_layer("anim", None)

    def show_tips(self):
        """кнопка в настройках: подсказки по интерфейсу ещё раз - поверх схемы, а не страницы настроек"""
        from . import onboarding
        while overlay.close_top(self):
            pass
        onboarding.start(self)

    def organs(self):
        """органы на схеме: без органов другого пола"""
        return for_body(self.body)

    def set_body(self, value):
        """женская или мужская схема тела; викторина начинается заново - вопросы могли быть о скрытых органах"""
        if value == self.body:
            return
        self.body = value
        settings.save(body=value)
        self.hidden -= other_sex(value)
        self.tours.reset()                              # маршрут экскурсии зависит от схемы тела
        self.flash.reset()                              # и колоды флеш-карточек - тоже
        self.set_spot(None)
        self.render_layers()
        self.apply_view()
        if self.mode != "study":
            self.set_mode(self.mode)
        elif self.card_fn != self.empty_card:
            self.set_card(self.empty_card, fade=True)

    def set_ui_scale(self, value):
        """масштаб меняет размеры всего окна и схемы: окно пересобирается в новом масштабе сразу
        (после щелчка - кнопка настроек ещё обрабатывает мышь)"""
        settings.save(ui_scale=value)
        if value != self.ui_scale:
            QTimer.singleShot(0, lambda: self.rebuild(value))

    def rebuild(self, scale):
        """новое окно в масштабе scale на месте этого: слои, скрытые органы, режим и открытая карточка органа
        переносятся (начатая игра - нет: она начинается заново с карточки настройки), настройки снова открыты.
        Новое окно сначала невидимо (прозрачность 0) и показывается, только когда схема нарисована, -
        до тех пор на экране прежнее: без белой вспышки пустого окна"""
        if App.main is not self and App.main is not None:
            return                                      # окно уже пересобрали
        set_scale(scale)
        QApplication.instance().setFont(font(10))
        new = App(ui_scale=scale, quality=self.quality)
        new.layers, new.hidden, new.skin_clear = set(self.layers), set(self.hidden), self.skin_clear
        new.quiz.cfg = dict(self.quiz.cfg)
        new.render_layers()
        if self.mode != "study":
            new.set_mode(self.mode)
        elif self.cards.current is not None and self.card_fn not in (self.empty_card, self.tours.card, self.flash.card):
            new.cards = self.cards.upto_current()
            new.show_info(self.cards.current, record=False)
        new.setWindowOpacity(0.0)                       # заголовок красится в showEvent, пока окно невидимо
        new.move(self.frameGeometry().topLeft())
        if self.isMaximized():
            new.showMaximized()
        else:
            new.show()
        start = time.monotonic()

        def swap():
            if not new.ready() and time.monotonic() - start < REBUILD_WAIT:
                QTimer.singleShot(30, swap)             # схема ещё рисуется - прежнее окно пока на экране
                return
            settings_open = settings_window._window is not None
            while overlay.close_top(self):
                pass
            if settings_open:
                show_settings(new)
            new.repaint()                               # нарисовать всё, пока окно невидимо
            new.setWindowOpacity(1.0)
            self.close()
            self.deleteLater()

        QTimer.singleShot(0, swap)

    def retranslate(self):
        """переписать все тексты на текущем языке, не сбрасывая режим и вопрос викторины"""
        self.setWindowTitle(t("app_title"))
        self.title.setText(t("app_title"))
        for name, b in self.panel_tabs.items():
            b.setText(t("tab_" + name))
            b.setToolTip(t(name + "_hint"))
        self.update_check.retranslate()
        self.ach_button.setText(achievements_text())
        self.ach_button.setToolTip(t("ach_hint"))
        self.lang_button.setToolTip(t("lang_hint"))
        self.latin_action.setText(t("lang_latin_item"))
        for mode, b in self.mode_buttons.items():
            b.setText(t("mode_" + mode))
        for name, b in self.stage.zoom_buttons.items():
            b.setToolTip(t(name))
        self.update_buttons()
        if self.view.message:
            self.view.message = (t("rescaling") if self.view.message[1] else t("loading"), self.view.message[1])
        self.view.set_tip(None)
        self.render_layers()
        self.status.setText(self.status_fn())
        self.card_fn()
        retranslate_all()
        refresh_settings()
        refresh_diseases(self)

    def set_status(self, fn):
        self.status_fn = fn
        self.status.setText(fn())

    def set_card(self, fn, fade=False):
        """показать в карточке справа то, что рисует fn; fade - новая карточка проявляется плавно
        (а не обновление той же карточки: ответ на вопрос, щелчок в настройке)"""
        self.card_fn = fn
        fn()
        self.card_area.verticalScrollBar().setValue(0)
        if fade:
            self.fade_card()

    def fade_card(self):
        """карточка проявляется за CARD_FADE_MS; после - без эффекта (он замедлял бы перерисовку)"""
        if not self.isVisible():
            return
        old = getattr(self, "card_fade", None)
        if old is not None:
            old.stop()
        effect = QGraphicsOpacityEffect(self.card)
        effect.setOpacity(0.0)
        self.card.setGraphicsEffect(effect)
        a = QPropertyAnimation(effect, b"opacity", self.card)
        a.setDuration(CARD_FADE_MS)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)

        def done():
            if self.card_fade is a:
                self.card_fade = None
                self.card.setGraphicsEffect(None)

        a.finished.connect(done)
        self.card_fade = a
        a.start()

    def empty_card(self):
        fill_start(self.card, t("pick_title"), t("pick_hint"), t("tours_title"),
                   [("➜  " + tours.title(name), lambda n=name: self.start_tour(n)) for name in tours.available(self.body)],
                   review=self.review_block(), organ=self.organ_block(), knowledge=self.knowledge_block(),
                   flash=self.flash.block(), starred=self.notes.home_block())

    def start_tour(self, name):
        """экскурсия со стартовой карточки: начатый подход флеш-карточек заканчивается"""
        self.flash.reset()
        self.tours.start(name)

    def review_block(self):
        """раздел «Повторение» на стартовой карточке: сколько органов пора повторить (в том виде викторины,
        где их больше всего) и серия дней подряд"""
        try:
            data = progress.load()
            due = {mode: len(progress.due(mode, self.quiz.mode_keys(mode), data)) for mode in MODES}
            streak = achievements.streak(data)
        except Exception:                               # прогресс - не повод не показать карточку
            traceback.print_exc()
            return None
        mode = max(MODES, key=lambda m: (due[m], m == self.quiz_mode))
        lines = [(t("home_due", n=due[mode]), "text") if due[mode] else (t("home_due_none"), "muted")]
        if streak:
            lines.append((t("home_streak", n=streak), "day_title"))
        button = (t("home_due_button") + "  ·  " + t("mode_" + mode), lambda: self.quiz.review(mode)) if due[mode] else None
        return t("home_review"), lines, button

    def knowledge_block(self):
        """кнопка карты знаний на стартовой карточке и легенда, пока карта видна"""
        button = (t("knowledge_hide") if self.knowledge else t("knowledge_show"),
                  lambda: self.set_knowledge(not self.knowledge))
        return button, (stats.LEVELS[::-1] if self.knowledge else None)

    def set_knowledge(self, on):
        """показать или спрятать карту знаний: органы в цвете уровня знания (выучено, учу, слабо)"""
        self.knowledge = on
        self.refresh_knowledge()
        if self.card_fn == self.empty_card:
            self.card_fn()

    def refresh_knowledge(self):
        """слой карты знаний заново (новые результаты, скрытые органы, другой масштаб); в викторине его нет"""
        if not (self.knowledge and self.mode == "study" and self.ready()):
            self.view.show_layer("knowledge", None)
            return
        try:
            self.levels = stats.mastery(progress.load())
        except Exception:
            traceback.print_exc()
            self.levels = {}
        colors = {k: hex2rgb(STATUS[v]) for k, v in self.levels.items()}
        self.view.show_layer("knowledge", (qimage(self.atlas.tint(colors)), (0, 0)))

    def organ_block(self):
        """«Орган дня» на стартовой карточке: каждый день другой, с фактом дня и кнопкой его карточки"""
        keys = self.organs()
        key = keys[date.today().toordinal() % len(keys)]
        return t("home_organ"), key, fact_of_day(key), (t("home_organ_open", name=i18n.name(key)),
                                                       lambda: self.open_link(key))

    # --- построение схемы (в отдельном потоке: окно не замирает)
    def ready(self):
        """схема нарисована в масштабе окна: можно наводить, кликать и подсвечивать"""
        return self.atlas is not None and self.atlas.Z == self.want_Z

    def start_build(self):
        """нарисовать схему в масштабе want_Z (из кэша, если есть); одновременно строится одна"""
        self.resize_timer.stop()
        if self.building or self.ready() or self.want_Z is None:
            return
        self.building = True
        Z = self.want_Z
        first = self.atlas is None
        look = self.look()

        def work():
            try:
                # первая схема: готовая из сборки, пусть другого масштаба, - сразу, а точная следом
                atlas = (first and Atlas.preview(Z)) or Atlas.cached(Z)
                # картинку для показа (фон темы, кожа, видимые слои и органы) собираем тоже здесь, а не в окне:
                # окно её только покажет и не замрёт. Если вид за это время сменился, окно пересоберёт её само
                self.apply_look(atlas, look)
                atlas.anim_frame(time.monotonic())      # и заготовки анимации сердца и лёгких
                atlas.structures()                      # маски костей и мышц для клика
                self.built.put((Z, atlas))
            except Exception as ex:                     # покажем ошибку в основном потоке
                self.built.put((Z, ex))

        threading.Thread(target=work, daemon=True).start()
        self.build_timer.start(50)

    def poll_build(self):
        try:
            _Z, res = self.built.get_nowait()
        except queue.Empty:
            return
        self.build_timer.stop()
        self.building = False
        if isinstance(res, Exception):
            traceback.print_exception(type(res), res, res.__traceback__)
            if self.atlas is None:
                self.view.message = (t("build_error", error=res), False)
                self.view.update()
            return                                      # под новый размер не вышло: остаётся растянутая
        if self.atlas is not None:
            self.atlas.stop_warm()
            self.marks.drop()                           # подсветка прежнего масштаба больше не подходит
        self.atlas = res
        self.apply_look(self.atlas, self.look())        # обычно картинка уже собрана потоком с тем же видом
        self.show_base()
        if not self.ready():                            # пока рисовали, окно снова поменяло размер
            self.view.message = (t("rescaling"), True)  # (или это готовая схема из сборки другого масштаба)
            self.start_build()
            return
        self.view.message = None
        self.view.update()
        self.marks.show_target()                        # если режим включили, пока схема строилась
        self.refresh_knowledge()
        self.marks.show_missed(self.marks.missed)
        self.atlas.warm()                               # подсветка под курсором - заранее, в фоне

    def look(self):
        """вид схемы сейчас: видимые слои тела, скрытые органы, непрозрачность кожи, цвета фона темы.
        Снимок (неизменяемые значения): его можно отдать потоку, который строит схему"""
        return (tuple(self.layers_now()), frozenset(self.hidden_now()), 1 - self.skin_clear / 100,
                theme.C["scene_bg"], theme.C["scene_hi"])

    @staticmethod
    def apply_look(atlas, look):
        """применить вид look() к схеме; что не поменялось, не пересобирается"""
        layers, hidden, skin, bg, hi = look
        atlas.set_layers(layers)
        atlas.set_hidden(hidden)
        atlas.set_skin_opacity(skin)
        atlas.set_background(bg, hi)

    def paint_base(self):
        """схема тела на фоне текущей темы"""
        self.atlas.set_background(theme.C["scene_bg"], theme.C["scene_hi"])
        self.show_base()

    def show_base(self):
        """показать готовую схему (если масштаб уже другой - растянутой, пока не нарисуется чёткая)"""
        self.view.base = qimage(self.atlas.base)
        self.view.update()

    # --- анимация: сердце бьётся, лёгкие дышат
    def animate(self):
        """раз в ANIM_MS: кусок схемы с сердцем и лёгкими в текущий момент поверх неподвижной схемы.
        Не рисуем, пока анимация выключена, схема перерисовывается под новый размер, поверх открыта
        панель (настройки, болезни, 3D), окно свёрнуто или неактивно (работают в другой программе, окно может
        быть закрыто ею целиком) - тогда проверяем реже и процессор не тратим"""
        live = (self.animation == "on" and self.ready() and overlay.top(self) is None and not self.isMinimized()
                and self.isActiveWindow())
        frame = self.atlas.anim_frame(time.monotonic()) if live else None
        if frame is None:
            self.view.show_layer("anim", None)
            self.anim_timer.start(ANIM_IDLE_MS)
            return
        im, pos = frame
        self.view.show_layer("anim", (qimage(im), pos))
        self.anim_timer.start(ANIM_MS)

    # --- размер окна
    def set_zoom(self, Z):
        """новый масштаб схемы: место под неё сразу, сама схема - когда дорисуется"""
        self.want_Z = Z
        d = self.view.dpr()
        self.view.set_size(math.ceil(W * Z / d), math.ceil(H * Z / d))

    def on_resize(self):
        """окно поменяло размер: схема сразу растягивается, а чёткая рисуется, когда размер устоится"""
        if not self.isVisible():                         # раскладка до показа окна - размер ещё не настоящий
            return
        d = self.stage.devicePixelRatioF()
        Z = fit_zoom(self.stage.width() * d, self.stage.height() * d)
        if self.atlas is None and not self.building:    # окно показалось: рисуем первую схему сразу
            self.set_zoom(Z)
            self.start_build()
            return
        if Z == self.want_Z:
            return
        self.set_zoom(Z)
        self.resize_timer.start()
        if self.atlas is None:                          # первая схема ещё рисуется
            return
        self.on_leave()
        for name in ("target", "flash", "anim", "knowledge", "missed"):        # в прежнем масштабе
            self.view.show_layer(name, None)
        self.view.set_labels([])
        if self.ready():                                # вернули прежний размер, пока рисовалась другая
            self.view.message = None
            self.marks.show_target()
        else:
            self.view.message = (t("rescaling"), True)
        self.view.update()

    # --- слои
    def hidden_now(self):
        """какие органы скрыты сейчас: в викторине видны все, иначе вопрос мог бы оказаться невидимым
        (а в викторине по костям и мышцам не видно ни одного); органов другого пола нет на схеме всегда"""
        if self.mode in NOT_ORGANS:
            return set(ORGANS)
        return (self.hidden if self.mode == "study" else set()) | other_sex(self.body)

    def layers_now(self):
        """какие слои тела видны сейчас: выбранные в панели «Слои», а в викторине по костям и мышцам - кожа
        и скелет и (или) мышцы по теме игры"""
        if self.mode not in NOT_ORGANS:
            return self.layers
        topic = self.quiz.body_topic()
        return {"skin"} | {LAYER_OF[k] for k in (KINDS if topic is None else (topic,))}

    def something_hidden(self):
        return bool(self.hidden or not set(DEFAULT_LAYERS) <= self.layers)

    def organs_all_text(self):
        """подпись кнопки в заголовке органов: всё скрыто - вернуть, иначе - скрыть все"""
        return t("layers_show_organs") if self.hidden == set(self.organs()) else t("layers_hide_organs")

    def render_layers(self):
        """построить панель слоёв заново (смена языка, схемы тела)"""
        self.toggles = fill_layers(
            self.panel, t("layers_title"),
            [(name, t("layer_" + name), name in self.layers) for name in BODY_LAYERS],
            t("layers_organs"),
            [(system, t("system_" + system),
              [(k, i18n.name(k), ORGANS[k]["color"], k not in self.hidden) for k in keys])
             for system, keys in self.groups()],
            self.toggle_layer, self.toggle_organ,
            show_all=(t("layers_show_all"), self.show_all, self.something_hidden()),
            organs_all=(self.organs_all_text(), self.toggle_all_organs),
            search=(t("search_hint"), self.query, self.on_search, self.on_search_enter, t("search_nothing")),
            fold=(self.layers_open, self.fold_layers),
            skin=(self.skin_clear, self.set_skin_clear, t("skin_opacity")),
            on_system=self.toggle_system, system_tip=t("layers_system_hint"),
            folded=self.folded, on_fold=self.fold_system, fold_tip=t("layers_fold_hint"))
        self.apply_filter()

    def apply_filter(self, to_top=True):
        """какие органы видны в списке панели: при поиске - найденные (свёрнутые системы не в счёт),
        без поиска - все, кроме органов свёрнутых систем"""
        if self.query.strip():
            filter_organs(self.toggles, set(search(self.organs(), self.query)), to_top=to_top)
        else:
            filter_organs(self.toggles, set(self.organs()), self.folded, to_top)

    def fold_system(self, system):
        """стрелка у системы в списке органов: свернуть или развернуть её органы (список не прыгает к началу)"""
        self.folded ^= {system}
        self.apply_filter(to_top=False)

    def groups(self):
        """органы панели по системам: [(система, [органы])]"""
        return by_system(by_color(self.organs()))

    def fold_layers(self):
        """свернуть или развернуть раздел «Слои» (запоминается)"""
        self.layers_open = not self.layers_open
        settings.save(layers_panel="open" if self.layers_open else "closed")
        self.render_layers()

    def toggle_system(self, system):
        """щелчок по названию системы: все её органы видны - скрыть их, иначе - показать все"""
        keys = set(dict(self.groups())[system])
        self.hidden = self.hidden - keys if keys & self.hidden else self.hidden | keys
        self.apply_view()

    def set_skin_clear(self, value):
        """ползунок прозрачности кожи (0 - кожа как нарисована, 100 - её не видно); схема - чуть позже,
        чтобы при перетаскивании не пересобирать её на каждый шаг"""
        self.skin_clear = value
        self.skin_timer.start()

    def apply_skin(self):
        if self.atlas is not None:
            self.atlas.set_skin_opacity(1 - self.skin_clear / 100)
            self.show_base()

    # --- поиск органа
    def on_search(self, text):
        """строка поиска изменилась: в панели остаются подходящие органы; если подходит ровно один,
        он подсвечивается на схеме"""
        self.query = text
        found = search(self.organs(), text)
        self.apply_filter()
        if self.tours.tour is None:
            self.set_spot(found[0] if text.strip() and len(found) == 1 else None, look=False)

    def on_search_enter(self, text):
        """Enter в поиске: открыть карточку первого найденного органа и подсветить его (скрытый - показать)"""
        found = search(self.organs(), text)
        if not text.strip() or not found:
            return
        self.tours.pause()
        self.show_info(found[0])
        self.set_spot(found[0])

    def set_spot(self, key, look=True):
        """подсветить орган в режиме «Изучать» (None - снять подсветку); скрытый орган сначала показать.
        look - приближенная схема плавно подводит орган к середине окна (переход по ссылке, шаг экскурсии)"""
        self.spot = key
        if key is not None and key in self.hidden:
            self.hidden.discard(key)
            self.apply_view()
        self.marks.show_target()
        if look and key is not None and self.ready():
            self.view.look_at(*self.atlas.center(key))

    def update_layers(self):
        """после щелчка: обновить флажки и кнопки на месте (пересоздавать панель долго)"""
        show_all_button(self.toggles, self.something_hidden())
        self.toggles[ORGANS_ALL].setText(self.organs_all_text())
        for name in BODY_LAYERS:
            self.toggles[name].set(t("layer_" + name), name in self.layers)
        if SKIN in self.toggles:
            self.toggles[SKIN].setVisible(self.layers_open and "skin" in self.layers)
        for k in self.organs():
            self.toggles[k].set(i18n.name(k), k not in self.hidden)
        count_organs(self.toggles)

    def show_panel(self):
        """панель слоёв - только в режиме «Изучать». В викторине её место остаётся пустым,
        чтобы схема не меняла масштаб (и не перерисовывалась) при каждой смене режима"""
        self.panel.setVisible(self.mode == "study" and not self.slide.hidden)

    def toggle_all_organs(self):
        self.hidden = set() if self.hidden == set(self.organs()) else set(self.organs())
        self.apply_view()

    def toggle_layer(self, name):
        self.layers ^= {name}
        self.apply_view()

    def toggle_organ(self, key):
        self.hidden ^= {key}
        self.apply_view()

    def show_all(self):
        self.layers, self.hidden = self.layers | set(DEFAULT_LAYERS), set()    # мышцы - как выбрано
        self.apply_view()

    def apply_view(self):
        """применить слои и скрытые органы к схеме и обновить панель"""
        self.update_layers()
        if self.atlas is not None:
            self.atlas.set_layers(self.layers_now())
            hidden = frozenset(self.hidden_now())
            if hidden != self.atlas.hidden:
                self.atlas.set_hidden(hidden)
                self.marks.drop()                       # подсветка зависит от того, кто кого закрывает
                self.on_leave()
                self.atlas.warm()
            self.show_base()
            self.marks.show_target()                    # подсветка органа поиска или экскурсии - заново
            self.refresh_knowledge()

    # --- наведение и клики
    def kind(self):
        """тип текущего вопроса (quiz.KINDS); без игры - режим: study или режим викторины"""
        return self.quiz.kind() or self.mode

    def on_move(self, x, y):
        """мышь над схемой; x, y - в пикселях схемы"""
        if not self.ready() or self.kind() not in ("study", "find", "body", "order"):   # остальные - кнопками
            return
        s = self.quiz.session
        if self.kind() != "study" and s and (s.level == "hard" or self.quiz.exam()):
            return                                      # на сложном уровне и в экзамене подсветки под курсором нет
        key = self.thing_at(x, y)
        self.kb.key = None                              # мышь снова главная: выбор стрелками сброшен
        if key != self.cur:
            self.cur = key
            self.marks.hover(key)
        # в викторине - без названия; при карте знаний - и уровень знания
        name = i18n.name(key) if key else ""
        if key and self.knowledge and key in self.levels:
            name += "  ·  " + t("level_name_" + self.levels[key])
        tip = (*self.view.to_screen(x, y), name) if key and self.mode == "study" else None
        self.view.set_tip(tip)

    def thing_at(self, x, y):
        """что под точкой схемы: орган, а в «Изучать» и викторине по костям и мышцам - и кость или мышца
        (если её слой тела виден и органа над ней нет)"""
        key = self.atlas.organ_at(x, y)
        if key is None and self.kind() in ("study", "body"):
            key = self.atlas.structure_at(x, y)
        return key

    def on_leave(self):
        if self.atlas is None:
            return
        self.cur = None
        self.marks.hover(None)
        self.view.set_tip(None)

    # --- приближение схемы
    def zoom_changed(self, animate=False):
        """схему приблизили или вернули: кнопки приближения доступны, когда есть куда;
        с HIDE_FROM интерфейс уезжает к краям окна"""
        stage = getattr(self, "stage", None)
        if stage is None:
            return
        k = self.view.aim()
        stage.zoom_buttons["zoom_in"].setEnabled(k < ZOOM_STEPS[-1])
        stage.zoom_buttons["zoom_out"].setEnabled(k > 1)
        stage.zoom_buttons["zoom_reset"].setEnabled(k > 1)
        self.slide.set_hidden(k >= HIDE_FROM, animate)

    def mousePressEvent(self, e):
        """боковые кнопки мыши листают историю карточек"""
        if e.button() in (Qt.BackButton, Qt.ForwardButton):
            self.go_history(-1 if e.button() == Qt.BackButton else 1)
            return
        super().mousePressEvent(e)

    # --- горячие клавиши
    def focus_search(self):
        """Ctrl+F: в режиме «Изучать» - в строку поиска органа"""
        box = self.toggles.get(SEARCH)
        if self.mode != "study" or overlay.top(self) is not None or not alive(box):
            return
        box.setFocus()
        box.selectAll()

    def show_help(self):
        open_help(self)

    def on_click(self, x, y):
        if not self.ready():
            return
        key = self.thing_at(x, y)
        if key is None or self.kind() not in ("study", "find", "body", "order"):
            return
        if self.mode != "study":
            self.quiz.answer(key)
            return
        self.tours.pause()                              # щелчок по органу прерывает экскурсию (к ней можно вернуться)
        self.set_spot(None)
        self.show_info(key)

    def show_info(self, key, record=True):
        """карточка органа; под ней - возврат к прерванной экскурсии или к списку экскурсий, над ней -
        «назад» и «вперёд» по просмотренным карточкам. record - добавить карточку в историю просмотра"""
        if record:
            self.cards.record(key)

        def nav():
            h = self.cards
            crumbs = [(i18n.name(k), "#%d" % j) for j, k in h.crumbs(CRUMBS)]
            return ((t("nav_back"), (lambda: self.go_history(-1)) if h.can_go(-1) else None),
                    (t("nav_forward"), (lambda: self.go_history(1)) if h.can_go(1) else None),
                    crumbs, lambda ref: self.go_history(int(ref[1:]) - h.pos))

        on_3d = (lambda: show_3d(self, key)) if key in ORGANS else None          # у костей и мышц 3D нет
        back = self.flash.back_button() or self.tours.back_button()     # вернуться к флеш-карточкам или экскурсии
        self.set_card(lambda: fill_card(self.card, key, on_3d=on_3d, back=back,
                                        on_link=self.open_link, nav=nav(), on_read=self.reader.action(key),
                                        note=self.notes.block(key)), fade=True)

    def go_history(self, step):
        """на step карточек назад (step < 0) или вперёд по истории просмотра (Alt+стрелки, кнопки над карточкой)"""
        if self.mode != "study" or overlay.top(self) is not None or not self.cards.can_go(step):
            return
        key = self.cards.go(step)
        self.tours.pause()
        self.show_info(key, record=False)
        self.set_spot(key if key in self.organs() or key in STRUCTURES else None)

    def open_link(self, key):
        """щелчок по ссылке в карточке: орган - открыть его карточку и подсветить на схеме,
        болезнь - статью справочника болезней"""
        if key not in ORGANS and key not in STRUCTURES:
            show_diseases(self, key)
            return
        self.show_info(key)
        self.set_spot(key if key in self.organs() or key in STRUCTURES else None)

    def update_buttons(self):
        self.update_tabs()
        for code, a in self.lang_actions.items():
            a.setChecked(code == i18n.base())
        self.latin_action.setChecked(i18n.latin())
        name = i18n.language_name(i18n.base())          # полным названием: «Русский», «English»
        if i18n.latin():
            name += " · " + i18n.language_name(i18n.LATIN)
        self.lang_button.setText(name + "  ▾")
        self.diseases_button.setEnabled(self.mode == "study")     # в викторине справочник подсказал бы ответ

    def page_rect(self):
        """место страницы-вкладки: во всю ширину окна от строки статуса (под вкладками) до низа"""
        top = self.status.mapTo(self, QPoint(0, 0)).y()
        return QRect(0, top, self.width(), self.height() - top)

    def open_tab(self):
        """открытая страница: diseases, stats, settings или None (видна схема). Панель поверх страницы
        (достижения, горячие клавиши) её не закрывает"""
        pages = [p for p in overlay.stack(self) if p.page]
        return pages[-1].kind if pages else None

    def update_tabs(self):
        """выбрана вкладка открытой страницы, а без неё - вкладка режима"""
        opened = self.open_tab()
        for mode, b in self.mode_buttons.items():
            set_button_bg(b, "accent" if opened is None and (mode == "study") == (self.mode == "study") else "card")
        for name, b in self.panel_tabs.items():
            set_button_bg(b, "accent" if name == opened else "card")

    def panels_changed(self):
        """страница или панель открылась или закрылась (overlay.Panel): вкладки - по ней. Пока открыта страница,
        схема под ней не видна: кнопки приближения спрятаны, а приближенная схема - снова целиком (иначе
        заголовок с вкладками уехал бы за край окна)"""
        if not alive(self.diseases_button):
            return
        page = self.open_tab() is not None
        for b in self.stage.zoom_buttons.values():
            b.setVisible(not page)
        if page:
            self.on_leave()
            if self.view.aim() > 1:
                self.view.reset_zoom(animate=False)
        self.update_tabs()

    def page_tab(self, name, show):
        """вкладка страницы: открыть страницу; если она уже открыта - закрыть панели поверх неё"""
        if self.open_tab() != name:
            show()
            return
        while overlay.top(self) is not None and not overlay.top(self).page:
            overlay.close_top(self)

    def mode_tab(self, name):
        """вкладка режима (study или quiz). Со страницы - назад к схеме: в тот же режим - как было (начатая игра
        и карточка остаются), в другой - режим меняется. Без страницы - как раньше: режим начинается заново
        (в «Изучать» - стартовая карточка, в «Викторине» - её настройка)"""
        if self.open_tab() is not None:
            while overlay.close_top(self):
                pass
            if (name == "study") == (self.mode == "study"):
                return
        self.set_mode("study" if name == "study" else self.quiz_mode)

    def show_lang_menu(self):
        """меню под кнопкой языка: языки и латинские названия органов"""
        self.lang_menu.setStyleSheet(
            "QMenu {background: %s; color: %s; border: 1px solid %s; padding: %dpx}"
            " QMenu::item {padding: %dpx %dpx; border-radius: %dpx}"
            " QMenu::item:selected {background: %s; color: %s}"
            " QMenu::separator {height: 1px; background: %s; margin: %dpx %dpx}"
            % (theme.C["card"], theme.C["text"], theme.C["border"], px(4), px(5), px(14), px(4),
               theme.C["accent"], theme.C["on_accent"], theme.C["border"], px(4), px(6)))
        self.lang_menu.setFont(font(10))
        b = self.lang_button
        self.lang_menu.popup(b.mapToGlobal(b.rect().bottomLeft()))

    def set_mode(self, mode):
        """study - изучение; режим викторины сначала показывает карточку настройки"""
        self.mode = mode
        if mode != "study" and mode != self.quiz_mode:
            self.quiz_mode = mode
            settings.save(quiz_mode=mode)
        self.tours.reset()
        self.flash.reset()
        self.cards.clear()
        self.kb.key = None
        self.reader.stop()                              # чтение карточки - только в «Изучать»
        self.marks.unreveal()
        if SEARCH in self.toggles:
            self.toggles[SEARCH].clear()                # поиск сбрасывается вместе с подсветкой
        self.spot = None
        self.update_buttons()
        if mode != "study":
            close_diseases(self)
        self.quiz.stop()
        self.show_panel()
        self.apply_view()                               # в викторине скрытые органы снова видны
        if mode == "study":
            self.set_status(lambda: t("hint"))
            self.set_card(self.empty_card, fade=True)
            return
        self.set_status(lambda: t("setup_status"))
        self.set_card(self.quiz.render_setup, fade=True)

    def keyPressEvent(self, e):
        """Esc закрывает верхнюю панель; остальное - on_key"""
        if e.key() == Qt.Key_Escape:
            if overlay.top(self) is None and self.view.aim() > 1:
                self.view.reset_zoom()                   # приближенная схема - снова целиком, интерфейс виден
            else:
                overlay.close_top(self)
            return
        names = {Qt.Key_Right: "Right", Qt.Key_Left: "Left", Qt.Key_Return: "Return", Qt.Key_Enter: "KP_Enter",
                 Qt.Key_Up: "Up", Qt.Key_Down: "Down"}
        self.on_key(names.get(e.key(), ""), e.text())

    def on_key(self, keysym, char):
        """цифры выбирают вариант ответа, Enter на карточке настройки начинает игру, стрелки листают экскурсию,
        + и − приближают схему, 0 возвращает её целиком, ? - справка о клавишах
        (но не тогда, когда поверх открыта панель: настройки, болезни или 3D, и не при наборе в поиске)"""
        if overlay.top(self) is not None or isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)):
            return                                      # набирают в поиске или в заметке
        if char in ("+", "=", "-", "−", "0"):
            if char == "0":
                self.view.reset_zoom()
            else:
                self.view.zoom_step(1 if char in ("+", "=") else -1)
            return
        if char == "?":
            self.show_help()
            return
        if keysym in ("Up", "Down") and self.kb.keys():
            self.kb.move(-1 if keysym == "Up" else 1)
            return
        if keysym in ("Return", "KP_Enter") and self.kb.choose():
            return
        if self.mode == "study":
            if char in ("k", "K", "л", "Л"):             # K (и та же клавиша в русской раскладке)
                self.set_knowledge(not self.knowledge)
                return
            if char in ("r", "R", "к", "К") and self.cards.current is not None:   # R - прочитать карточку вслух
                self.reader.toggle(self.cards.current)
                return
            if self.flash.on_key(keysym, char):        # флеш-карточка: пробел - ответ, 1 / 2 - не знал / знал
                return
            self.tours.on_key(keysym)
            return
        self.quiz.on_key(keysym, char)

    def closeEvent(self, e):
        self.notes.flush()                              # недописанная заметка - в файл
        if App.main is self:                            # программу закрывают (а не пересобирают окно):
            speech.stop()                               # голос системы - отдельный процесс, сам он не замолчит
        super().closeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.view.setGeometry(self.rect())
        self.view.reset_zoom(animate=False)              # новый размер окна - схема снова целиком
        self.stage.place()
        toast.place(self)

    def paintEvent(self, _e):
        QPainter(self).fillRect(self.rect(), color("bg"))
