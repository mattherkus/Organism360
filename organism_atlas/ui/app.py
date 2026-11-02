"""Главное окно (Qt): схема тела, наведение, карточка органа, панель слоёв с поиском органа, режим «Изучать»
и викторина. Игру ведёт QuizController (quiz_controller.py), экскурсии - TourController (tour_controller.py),
историю карточек - CardHistory (history.py); окно даёт им карточку справа и подсветку органов на схеме.
Схема подстраивается под размер окна: пока рисуется чёткая версия, показывается растянутая прежняя.
Схема рисуется в пикселях экрана: на экране с масштабом 150 % она в полтора раза подробнее, а не растянута."""

import math
import queue
import threading
import time
import traceback
from datetime import date

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup, QKeySequence, QPainter, QPixmap, QRegion, QShortcut
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QMenu, QScrollArea, QWidget

from .. import achievements, i18n, progress, settings, stats, theme, tours
from ..colors import hex2rgb
from ..config import STATUS
from ..atlas import Atlas
from ..body.base import BODY_LAYERS, DEFAULT_LAYERS
from ..geometry import H, W
from ..i18n import t
from ..organs import ORGANS, by_system, fact_of_day, for_body, other_sex, search
from ..quiz import MODES, NOT_ORGANS
from ..structures import KINDS, LAYER_OF, STRUCTURES
from . import overlay, titlebar
from .achievements import button_text as achievements_text, show_achievements
from .diseases import close_diseases, refresh_diseases, show_diseases
from .scaling import fit_zoom, pick_zoom, px, set_scale
from .scheme_view import HIDE_FROM, ZOOM_STEPS, SchemeView, Stage, slide
from . import settings_window
from .settings_window import refresh_settings, show_settings
from .viewer3d import rerender_all, retranslate_all, set_quality, show_3d
from .help import show_help as open_help
from .cards import fill_card, fill_start
from .history import CardHistory
from .layers_panel import ORGANS_ALL, SEARCH, SKIN, by_color, fill_layers, filter_organs, show_all_button
from .quiz_controller import QuizController, timer
from .stats import show_stats
from .tour_controller import TourController
from .widgets import alive, color, flat_button, font, hbox, label, qimage, retheme, rounded_card, set_button_bg, vbox

ANIM_MS = 60                    # кадр анимации сердца и лёгких (около 16 в секунду)
ANIM_IDLE_MS = 300              # проверка, не пора ли снова анимировать, пока анимация не видна
REVEAL_MS = 500                # сколько на лёгком уровне видна подсказка «верный орган здесь» после ошибки
REBUILD_WAIT = 5                # сколько секунд ждать, пока пересобранное окно нарисует схему (смена масштаба)
CRUMBS = 2                      # сколько прежних карточек показывать «крошками» над карточкой органа


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
        self.cards = CardHistory()             # просмотренные карточки органов: «назад», «вперёд»
        self.quiz_mode = settings.get(saved, "quiz_mode")     # вид викторины, который открывает кнопка «Викторина»
        self.layers_open = settings.get(saved, "layers_panel") == "open"   # раздел «Слои» развёрнут
        self.skin_clear = 0                    # прозрачность кожи, % (ползунок под строкой «Кожа»)
        self.body = settings.get(saved, "body")   # схема тела: female или male (органы малого таза)
        self.animation = settings.get(saved, "animation")      # on - сердце бьётся, лёгкие дышат
        self.atlas, self.cur = None, None
        self.photos = {}                       # {(орган, вид подсветки): (QImage, (x, y))}
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
        self.flash_timer = timer(self, self.unflash, 500)
        self.reveal_timer = timer(self, self.unreveal, REVEAL_MS)
        self.skin_timer = timer(self, self.apply_skin, 40)
        self.resize_timer = timer(self, self.start_build, 400)
        self.anim_timer = timer(self, self.animate)
        self.build_timer = QTimer(self)
        self.build_timer.timeout.connect(self.poll_build)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(False)
        self.ui_hidden = False                 # схема приближена сильно: заголовок, слои и карточка уехали
        self.ghosts = {}                       # {виджет: его картинка, которая сейчас уезжает или возвращается}

        root = vbox(self, margins=(24, 18, 24, 0))
        top = hbox()
        self.title = label("", size=20, bold=True, wrap=False)
        top.addWidget(self.title)
        top.addSpacing(px(32))                           # заголовок не прилипает к кнопкам при узком окне
        top.addStretch(1)
        # два режима: «Изучать» и «Викторина»; вид викторины выбирается на её карточке настройки
        self.mode_buttons = {"study": flat_button("", lambda: self.set_mode("study")),
                             "quiz": flat_button("", lambda: self.set_mode(self.quiz_mode))}
        for i, b in enumerate(self.mode_buttons.values()):
            top.addSpacing(px(6) if i else 0)
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
        # справочник, достижения и настройки - значками с подсказками
        self.diseases_button = flat_button("⚕", lambda: show_diseases(self), size=12, padx=10, pady=4)
        self.ach_button = flat_button("", lambda: show_achievements(self), padx=10)
        self.settings_button = flat_button("⚙", lambda: show_settings(self), size=12, padx=10, pady=4)
        self.stats_button = flat_button("▤", lambda: show_stats(self), size=12, padx=10, pady=4)
        for b in (self.diseases_button, self.stats_button, self.ach_button, self.settings_button):
            top.addSpacing(px(6))
            top.addWidget(b, 0, Qt.AlignTop)
        for b in (self.diseases_button, self.stats_button, self.settings_button):   # значок крупнее - высота как у соседних
            b.setFixedHeight(self.ach_button.sizeHint().height())
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

    def set_animation(self, value):
        self.animation = value
        settings.save(animation=value)
        if value != "on":
            self.view.show_layer("anim", None)

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
        self.set_spot(None)
        self.render_layers()
        self.apply_view()
        if self.mode != "study":
            self.set_mode(self.mode)
        elif self.card_fn != self.empty_card:
            self.set_card(self.empty_card)

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
        elif self.cards.current is not None and self.card_fn not in (self.empty_card, self.tours.card):
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
        self.settings_button.setToolTip(t("settings_hint"))
        self.diseases_button.setToolTip(t("diseases_hint"))
        self.stats_button.setToolTip(t("stats_hint"))
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

    def set_card(self, fn):
        self.card_fn = fn
        fn()
        self.card_area.verticalScrollBar().setValue(0)

    def empty_card(self):
        fill_start(self.card, t("pick_title"), t("pick_hint"), t("tours_title"),
                   [("➜  " + tours.title(name), lambda n=name: self.tours.start(n)) for name in tours.available(self.body)],
                   review=self.review_block(), organ=self.organ_block(), knowledge=self.knowledge_block())

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
            self.drop_photos()                          # подсветка прежнего масштаба больше не подходит
        self.atlas = res
        self.apply_look(self.atlas, self.look())        # обычно картинка уже собрана потоком с тем же видом
        self.show_base()
        if not self.ready():                            # пока рисовали, окно снова поменяло размер
            self.view.message = (t("rescaling"), True)  # (или это готовая схема из сборки другого масштаба)
            self.start_build()
            return
        self.view.message = None
        self.view.update()
        self.show_target()                              # если режим включили, пока схема строилась
        self.refresh_knowledge()
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
        for name in ("target", "flash", "anim", "knowledge"):        # в прежнем масштабе
            self.view.show_layer(name, None)
        if self.ready():                                # вернули прежний размер, пока рисовалась другая
            self.view.message = None
            self.show_target()
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
            on_system=self.toggle_system, system_tip=t("layers_system_hint"))
        if self.query:
            filter_organs(self.toggles, set(search(self.organs(), self.query)))

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
        filter_organs(self.toggles, set(found))
        if self.tours.tour is None:
            self.set_spot(found[0] if text.strip() and len(found) == 1 else None)

    def on_search_enter(self, text):
        """Enter в поиске: открыть карточку первого найденного органа и подсветить его (скрытый - показать)"""
        found = search(self.organs(), text)
        if not text.strip() or not found:
            return
        self.tours.pause()
        self.show_info(found[0])
        self.set_spot(found[0])

    def set_spot(self, key):
        """подсветить орган в режиме «Изучать» (None - снять подсветку); скрытый орган сначала показать"""
        self.spot = key
        if key is not None and key in self.hidden:
            self.hidden.discard(key)
            self.apply_view()
        self.show_target()

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

    def show_panel(self):
        """панель слоёв - только в режиме «Изучать». В викторине её место остаётся пустым,
        чтобы схема не меняла масштаб (и не перерисовывалась) при каждой смене режима"""
        self.panel.setVisible(self.mode == "study" and not self.ui_hidden)

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
                self.drop_photos()                      # подсветка зависит от того, кто кого закрывает
                self.on_leave()
                self.atlas.warm()
            self.show_base()
            self.show_target()                          # подсветка органа поиска или экскурсии - заново
            self.refresh_knowledge()

    # --- наведение и клики
    def drop_photos(self):
        """забыть картинки подсветки"""
        for name in ("target", "hover", "flash", "reveal"):
            self.view.show_layer(name, None)
        self.view.set_pin(None)
        self.photos.clear()

    def photo(self, key, kind):
        if (key, kind) not in self.photos:
            im, pos = self.atlas.overlay(key, kind)
            self.photos[(key, kind)] = (qimage(im), pos)
        return self.photos[(key, kind)]

    def set_hover(self, key):
        self.view.show_layer("hover", None if key is None else self.photo(key, "hover"))
        self.view.setCursor(Qt.ArrowCursor if key is None else Qt.PointingHandCursor)

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
        if key != self.cur:
            self.cur = key
            self.set_hover(key)
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
        self.set_hover(None)
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
        self.set_ui_hidden(k >= HIDE_FROM, animate)

    def sliding(self):
        """что уезжает при сильном приближении: заголовок - вверх, слои - влево, карточка - вправо;
        (виджет, виден ли он, когда интерфейс на месте, куда уезжает)"""
        return ((self.header, True, QPoint(0, -1)), (self.panel, self.mode == "study", QPoint(-1, 0)),
                (self.card_area, True, QPoint(1, 0)))

    def set_ui_hidden(self, hide, animate=True):
        """увезти интерфейс за края окна (hide) или вернуть; без animate - сразу"""
        if hide == self.ui_hidden:
            return
        self.ui_hidden = hide
        animate = animate and self.isVisible()
        for w, shown, d in self.sliding():
            if not shown:
                continue
            if not animate:
                w.setVisible(not hide)
                continue
            at = w.mapTo(self, QPoint(0, 0))
            away = QPoint(-w.width() if d.x() < 0 else self.width() if d.x() > 0 else at.x(),
                          -w.height() if d.y() < 0 else at.y())
            g, pos = self.ghost(w)
            w.hide()                                     # пока едет - вместо виджета его картинка
            slide(g, pos or (at if hide else away), away if hide else at, lambda g=g, w=w: self.landed(g, w))
        self.stage.place(animate)

    def ghost(self, w):
        """картинка виджета для выезда; если прошлая ещё едет - новая начинает с её места"""
        old = self.ghosts.pop(w, None)
        pos = None
        if old is not None:
            pos = old.pos()
            old._slide.stop()
            old.deleteLater()
        g = QLabel(self)
        g.setAttribute(Qt.WA_TransparentForMouseEvents)
        d = w.devicePixelRatioF()
        pm = QPixmap(w.size() * d)                       # без фона: заголовок едет поверх схемы прозрачным
        pm.setDevicePixelRatio(d)
        pm.fill(Qt.transparent)
        w.render(pm, QPoint(), QRegion(), QWidget.DrawChildren)
        g.setPixmap(pm)
        g.resize(w.size())
        g.show()
        g.raise_()
        self.ghosts[w] = g
        return g, pos

    def landed(self, g, w):
        """картинка доехала: убрать её, а вернувшийся виджет показать"""
        if self.ghosts.get(w) is not g:
            return
        del self.ghosts[w]
        g.deleteLater()
        if not self.ui_hidden:
            self.show_panel() if w is self.panel else w.show()

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
        self.set_card(lambda: fill_card(self.card, key, on_3d=on_3d, back=self.tours.back_button(),
                                        on_link=self.open_link, nav=nav()))

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
        for mode, b in self.mode_buttons.items():
            set_button_bg(b, "accent" if (mode == "study") == (self.mode == "study") else "card")
        for code, a in self.lang_actions.items():
            a.setChecked(code == i18n.base())
        self.latin_action.setChecked(i18n.latin())
        text = i18n.short_name(i18n.base())
        self.lang_button.setText(text + (" · " + t("latin_toggle") if i18n.latin() else "") + "  ▾")
        self.diseases_button.setEnabled(self.mode == "study")     # в викторине справочник подсказал бы ответ

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
        self.cards.clear()
        self.unreveal()
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
            self.set_card(self.empty_card)
            return
        self.set_status(lambda: t("setup_status"))
        self.set_card(self.quiz.render_setup)

    # --- подсветка на схеме: вопрос, верно/ошибка, подсказка
    def show_target(self):
        """подсветить орган текущего вопроса «Угадай название», а в «Изучать» - орган поиска или экскурсии;
        у вопроса другого типа подсветки нет"""
        if not self.ready():
            return
        key = self.quiz.target() if self.mode != "study" else self.spot
        if key is None or key in self.hidden_now():
            self.view.show_layer("target", None)
            return
        self.view.show_layer("target", self.photo(key, "target"))

    def flash(self, key, kind):
        """на полсекунды закрасить орган зелёным (верно) или красным (ошибка)"""
        if not self.ready():
            return
        self.view.show_layer("flash", self.photo(key, kind))
        self.flash_timer.start()

    def unflash(self):
        self.flash_timer.stop()
        self.view.show_layer("flash", None)

    def reveal(self, key):
        """лёгкий уровень: после ошибки ненадолго показать на схеме, где верный орган, и подписать его"""
        if not self.ready() or (key not in ORGANS and key not in STRUCTURES) or key in self.hidden_now():
            return
        self.view.show_layer("reveal", self.photo(key, "ok"))
        self.view.set_pin((*self.atlas.anchor(key), i18n.name(key)))
        self.reveal_timer.start()

    def unreveal(self):
        self.reveal_timer.stop()
        self.view.show_layer("reveal", None)
        self.view.set_pin(None)

    def keyPressEvent(self, e):
        """Esc закрывает верхнюю панель; остальное - on_key"""
        if e.key() == Qt.Key_Escape:
            if overlay.top(self) is None and self.view.aim() > 1:
                self.view.reset_zoom()                   # приближенная схема - снова целиком, интерфейс виден
            else:
                overlay.close_top(self)
            return
        names = {Qt.Key_Right: "Right", Qt.Key_Left: "Left", Qt.Key_Return: "Return", Qt.Key_Enter: "KP_Enter"}
        self.on_key(names.get(e.key(), ""), e.text())

    def on_key(self, keysym, char):
        """цифры выбирают вариант ответа, Enter на карточке настройки начинает игру, стрелки листают экскурсию,
        + и − приближают схему, 0 возвращает её целиком, ? - справка о клавишах
        (но не тогда, когда поверх открыта панель: настройки, болезни или 3D, и не при наборе в поиске)"""
        if overlay.top(self) is not None or isinstance(QApplication.focusWidget(), QLineEdit):
            return
        if char in ("+", "=", "-", "−", "0"):
            if char == "0":
                self.view.reset_zoom()
            else:
                self.view.zoom_step(1 if char in ("+", "=") else -1)
            return
        if char == "?":
            self.show_help()
            return
        if self.mode == "study":
            if char in ("k", "K", "л", "Л"):             # K (и та же клавиша в русской раскладке)
                self.set_knowledge(not self.knowledge)
                return
            self.tours.on_key(keysym)
            return
        self.quiz.on_key(keysym, char)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.view.setGeometry(self.rect())
        self.view.reset_zoom(animate=False)              # новый размер окна - схема снова целиком
        self.stage.place()

    def paintEvent(self, _e):
        QPainter(self).fillRect(self.rect(), color("bg"))
