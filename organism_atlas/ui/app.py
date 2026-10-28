"""Главное окно (Qt): схема тела, наведение, карточка органа, панель слоёв с поиском органа, режим «Изучать»
с экскурсиями по системам органов и четыре викторины: «Найди орган», «Угадай название», «Угадай по факту»
и «Вперемешку» (со сложностью, таймером, длиной игры, темой и повторением ошибок).
Схема подстраивается под размер окна: пока рисуется чёткая версия, показывается растянутая прежняя.
Схема рисуется в пикселях экрана: на экране с масштабом 150 % она в полтора раза подробнее, а не растянута."""

import math
import queue
import threading
import time
import traceback

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QFrame, QLineEdit, QScrollArea, QSizePolicy, QWidget

from .. import achievements, i18n, progress, settings, theme, tours
from ..atlas import Atlas
from ..body.base import BODY_LAYERS, DEFAULT_LAYERS
from ..geometry import H, W
from ..i18n import t
from ..organs import ORGANS, SYSTEMS, by_system, for_body, in_system, other_sex, search
from ..quiz import LENGTHS, LEVELS, MODES, TIMERS, QuizSession, format_time, game_length
from . import overlay, titlebar
from .achievements import button_text as achievements_text, show_achievements
from .results import show_results_dialog
from .scaling import fit_zoom, pick_zoom, px, set_scale
from .settings_window import refresh_settings, show_settings
from .viewer3d import rerender_all, retranslate_all, set_quality, show_3d
from .widgets import (ORGANS_ALL, SEARCH, alive, by_color, color, fill_card, fill_layers, fill_question, fill_setup,
                      fill_start, fill_tour, filter_organs, flat_button, font, hbox, label, mark, qimage, retheme,
                      rounded_card, set_button_bg, show_all_button, vbox)


ANIM_MS = 60                    # кадр анимации сердца и лёгких (около 16 в секунду)
ANIM_IDLE_MS = 300              # проверка, не пора ли снова анимировать, пока анимация не видна


def timer(parent, fn, ms=None):
    """однократный таймер: start(мс) - вызвать fn через столько-то, stop() - отменить, isActive() - ждёт ли"""
    tm = QTimer(parent)
    tm.setSingleShot(True)
    tm.timeout.connect(fn)
    if ms is not None:
        tm.setInterval(ms)
    return tm


class SchemeView(QWidget):
    """схема тела: картинки в пикселях экрана (масштаб Z подобран под них) и поверх - кусок анимации,
    подсветка органа-вопроса, органа под курсором и вспышка ответа, подсказка с названием и надпись
    «рисуется»/«перерисовывается». Координаты мыши передаются окну в пикселях схемы"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.base = None                # QImage схемы (пока чёткая не готова - прежняя, растягивается)
        self.layers = {"anim": None, "target": None, "hover": None, "flash": None}   # (QImage, x, y) или None
        self.tip = None                 # (x, y, текст) в логических пикселях
        self.message = None             # (текст, внизу ли) - «Рисуется схема...» или «перерисовывается»
        self.setMouseTracking(True)

    def dpr(self):
        return self.devicePixelRatioF()

    def show_layer(self, name, item):
        """item - (QImage, (x, y)) в пикселях схемы или None - спрятать"""
        self.layers[name] = None if item is None else (item[0], item[1][0], item[1][1])
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), color("bg"))
        d = self.dpr()
        if self.base is not None:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRectF(self.rect()), self.base)
            if self.app.ready():
                for name in ("anim", "target", "hover", "flash"):
                    item = self.layers[name]
                    if item is not None:
                        im, x, y = item
                        p.drawImage(QRectF(x / d, y / d, im.width() / d, im.height() / d), im)
        if self.tip:
            x, y, text = self.tip
            p.setFont(font(10, bold=True))
            fm = p.fontMetrics()
            w, h = fm.horizontalAdvance(text) + 10, fm.height() + 4
            x, y = x + 14, y + 14
            x -= max(0, x + w + 6 - self.width())         # не даём подсказке вылезти за край схемы
            p.setPen(color("border"))
            p.setBrush(color("tip_bg"))
            p.drawRect(QRectF(x, y, w, h))
            p.setPen(color("tip_fg"))
            p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, text)
        if self.message:
            text, bottom = self.message
            p.setPen(color("muted"))
            p.setFont(font(9 if bottom else 12))
            r = self.rect().adjusted(0, 0, 0, -px(6)) if bottom else self.rect()
            p.drawText(r, (Qt.AlignBottom | Qt.AlignHCenter) if bottom else Qt.AlignCenter, text)

    def mouseMoveEvent(self, e):
        d = self.dpr()
        self.app.on_move(e.position().x() * d, e.position().y() * d)

    def leaveEvent(self, _e):
        self.app.on_leave()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.app.setFocus()                          # стрелки и цифры - снова окну, а не строке поиска
            d = self.dpr()
            self.app.on_click(e.position().x() * d, e.position().y() * d)


class Stage(QWidget):
    """место под схему, которое растягивается вместе с окном; схема - по центру сверху"""

    def __init__(self, app, view):
        super().__init__()
        self.app, self.view = app, view
        view.setParent(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def place(self):
        v = self.view
        v.move(max(0, (self.width() - v.width()) // 2), 0)

    def sizeHint(self):                                  # раскладка окна при запуске - под размер схемы
        return self.view.size()

    def minimumSizeHint(self):
        return QSize(px(200), px(200))

    def resizeEvent(self, e):
        self.place()
        self.app.on_resize()


class App(QWidget):
    def __init__(self, ui_scale=1.0, quality="medium"):
        """ui_scale - множитель масштаба из настроек (действует с запуска), quality - качество 3D"""
        super().__init__()
        self.host = self                       # панели (настройки, итоги, 3D) открываются поверх этого окна
        self.ui_scale = self.pending_scale = ui_scale     # pending - выбрано в настройках до перезапуска
        set_scale(ui_scale)
        self.quality = quality
        set_quality(quality)
        titlebar.set_icon(QApplication.instance())
        self.mode = "study"                    # study или режим викторины из quiz.MODES
        self.session = None                    # QuizSession во время игры (None - на карточке настройки)
        saved = settings.load()
        # настройки викторины: сложность, таймер и длина переживают перезапуск, тема и набор вопросов - нет
        self.cfg = {"level": settings.get(saved, "quiz_level"), "timer": settings.get(saved, "quiz_timer"),
                    "length": settings.get(saved, "quiz_length"), "topic": None, "set": "all"}
        self.body = settings.get(saved, "body")   # схема тела: female или male (органы малого таза)
        self.animation = settings.get(saved, "animation")      # on - сердце бьётся, лёгкие дышат
        self.qset = "all"                      # набор вопросов текущей игры (для истории)
        self.atlas, self.cur = None, None
        self.photos = {}                       # {(орган, вид подсветки): (QImage, (x, y))}
        self.choices = {}                      # {ключ органа: кнопка} в режиме «Угадай название»
        self.progress = None                   # метка «Вопрос N из M · Ошибок: K» в карточке
        self.feedback = None                   # (ключ текста, орган, цвет[, вопрос]) - отзыв о прошлом ответе
        self.wrong = set()                     # неверно выбранные варианты текущего вопроса
        # что сейчас в карточке и в строке статуса: функции, чтобы перерисовать их на другом языке
        self.card_fn = self.status_fn = None
        self.built = queue.Queue()
        self.building = False                  # в фоне рисуется схема (при запуске или под новый размер окна)
        self.layers = set(DEFAULT_LAYERS)      # видимые слои тела (мышцы включают в панели)
        self.hidden = set()                    # органы, скрытые в режиме «Изучать» (в викторине видны все)
        self.query = ""                        # строка поиска органа в панели слоёв
        self.spot = None                       # орган, подсвеченный в «Изучать»: найденный поиском или шаг экскурсии
        self.tour = None                       # (экскурсия, шаг): 0 - вступление, 1..n - органы, n + 1 - конец
        self.paused = None                     # экскурсия, прерванная щелчком по органу: к ней можно вернуться
        self.new_achievements, self.streak = [], 0        # для итогов игры: новые достижения и серия дней
        self.toggles = {}
        # отложенные действия
        self.flash_timer = timer(self, self.unflash, 500)
        self.next_timer = timer(self, self.next_question, 700)
        self.tick_timer = timer(self, self.tick, 250)
        self.resize_timer = timer(self, self.start_build, 400)
        self.results_timer = timer(self, self.show_results, 600)
        self.anim_timer = timer(self, self.animate)
        self.build_timer = QTimer(self)
        self.build_timer.timeout.connect(self.poll_build)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(False)

        root = vbox(self, margins=(24, 18, 24, 0))
        top = hbox()
        self.title = label("", size=20, bold=True, wrap=False)
        top.addWidget(self.title)
        top.addStretch(1)
        self.mode_buttons = {mode: flat_button("", lambda m=mode: self.set_mode(m)) for mode in ("study",) + MODES}
        for i, b in enumerate(self.mode_buttons.values()):
            top.addSpacing(px(8) if i else 0)
            top.addWidget(b, 0, Qt.AlignTop)
        top.addSpacing(px(20))
        self.lang_buttons = {}                             # переключатель языка, справа от режимов
        for i, code in enumerate(i18n.available()):
            b = flat_button(i18n.short_name(code), lambda c=code: self.set_lang(c), padx=8)
            top.addSpacing(px(4) if i else 0)
            top.addWidget(b, 0, Qt.AlignTop)
            self.lang_buttons[code] = b
        self.ach_button = flat_button("", lambda: show_achievements(self))
        top.addSpacing(px(12))
        top.addWidget(self.ach_button, 0, Qt.AlignTop)
        self.settings_button = flat_button("", lambda: show_settings(self))
        top.addSpacing(px(12))
        top.addWidget(self.settings_button, 0, Qt.AlignTop)
        self.top_bar = top
        root.addLayout(top)
        # статус - отдельной строкой: длинный текст не должен теснить кнопки режимов
        self.status = label("", size=11, bold=True)
        root.addSpacing(px(8))
        root.addWidget(self.status)

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
            self.render_setup()
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
        self.view.setFixedSize(cw, ch)
        self.layout().activate()
        hint = self.sizeHint()
        self.view.setMinimumSize(1, 1)
        self.view.setMaximumSize(16777215, 16777215)
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
        i18n.set_lang(code)
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
        self.tour = self.paused = None                  # маршрут экскурсии зависит от схемы тела
        self.set_spot(None)
        self.render_layers()
        self.apply_view()
        if self.mode != "study":
            self.set_mode(self.mode)
        elif self.card_fn != self.empty_card:
            self.set_card(self.empty_card)

    def set_ui_scale(self, value):
        """масштаб меняет размеры всего окна и схемы, поэтому применяется со следующего запуска"""
        self.pending_scale = value
        settings.save(ui_scale=value)

    def retranslate(self):
        """переписать все тексты на текущем языке, не сбрасывая режим и вопрос викторины"""
        self.setWindowTitle(t("app_title"))
        self.title.setText(t("app_title"))
        self.settings_button.setText("⚙  " + t("settings_button"))
        self.ach_button.setText(achievements_text())
        for mode, b in self.mode_buttons.items():
            b.setText(t("mode_" + mode))
        self.update_buttons()
        if self.view.message:
            self.view.message = (t("rescaling") if self.view.message[1] else t("loading"), self.view.message[1])
        self.view.tip = None
        self.render_layers()
        self.status.setText(self.status_fn())
        self.card_fn()
        retranslate_all()
        refresh_settings()

    def set_status(self, fn):
        self.status_fn = fn
        self.status.setText(fn())

    def set_card(self, fn):
        self.card_fn = fn
        fn()
        self.card_area.verticalScrollBar().setValue(0)

    def empty_card(self):
        fill_start(self.card, t("pick_title"), t("pick_hint"), t("tours_title"),
                   [("➜  " + tours.title(name), lambda n=name: self.start_tour(n)) for name in tours.available(self.body)])

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

        def work():
            try:
                self.built.put((Z, Atlas.cached(Z)))
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
            self.drop_photos()                          # подсветка прежнего масштаба больше не подходит
        self.atlas = res
        self.atlas.set_layers(self.layers)
        self.atlas.set_hidden(self.hidden_now())
        self.paint_base()
        if not self.ready():                            # пока рисовали, окно снова поменяло размер
            self.start_build()
            return
        self.view.message = None
        self.view.update()
        self.show_target()                              # если режим включили, пока схема строилась

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
        панель (настройки, итоги, 3D) или окно свёрнуто - тогда проверяем реже"""
        live = (self.animation == "on" and self.ready() and overlay.top(self) is None and not self.isMinimized())
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
        self.view.setFixedSize(math.ceil(W * Z / d), math.ceil(H * Z / d))
        self.stage.place()

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
        for name in ("target", "flash", "anim"):        # в прежнем масштабе
            self.view.show_layer(name, None)
        if self.ready():                                # вернули прежний размер, пока рисовалась другая
            self.view.message = None
            self.show_target()
        else:
            self.view.message = (t("rescaling"), True)
        self.view.update()

    # --- слои
    def hidden_now(self):
        """какие органы скрыты сейчас: в викторине видны все, иначе вопрос мог бы оказаться невидимым;
        органов другого пола нет на схеме всегда"""
        return (self.hidden if self.mode == "study" else set()) | other_sex(self.body)

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
            [(t("system_" + system), [(k, i18n.name(k), ORGANS[k]["color"], k not in self.hidden) for k in keys])
             for system, keys in by_system(by_color(self.organs()))],
            self.toggle_layer, self.toggle_organ,
            show_all=(t("layers_show_all"), self.show_all, self.something_hidden()),
            organs_all=(self.organs_all_text(), self.toggle_all_organs),
            search=(t("search_hint"), self.query, self.on_search, self.on_search_enter, t("search_nothing")))
        if self.query:
            filter_organs(self.toggles, set(search(self.organs(), self.query)))

    # --- поиск органа
    def on_search(self, text):
        """строка поиска изменилась: в панели остаются подходящие органы; если подходит ровно один,
        он подсвечивается на схеме"""
        self.query = text
        found = search(self.organs(), text)
        filter_organs(self.toggles, set(found))
        if self.tour is None:
            self.set_spot(found[0] if text.strip() and len(found) == 1 else None)

    def on_search_enter(self, text):
        """Enter в поиске: открыть карточку первого найденного органа и подсветить его (скрытый - показать)"""
        found = search(self.organs(), text)
        if not text.strip() or not found:
            return
        self.pause_tour()
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
        for k in self.organs():
            self.toggles[k].set(i18n.name(k), k not in self.hidden)

    def show_panel(self):
        """панель слоёв - только в режиме «Изучать». В викторине её место остаётся пустым,
        чтобы схема не меняла масштаб (и не перерисовывалась) при каждой смене режима"""
        self.panel.setVisible(self.mode == "study")

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
            self.atlas.set_layers(self.layers)
            hidden = frozenset(self.hidden_now())
            if hidden != self.atlas.hidden:
                self.atlas.set_hidden(hidden)
                self.drop_photos()                      # подсветка зависит от того, кто кого закрывает
                self.on_leave()
            self.show_base()
            self.show_target()                          # подсветка органа поиска или экскурсии - заново

    # --- наведение и клики
    def drop_photos(self):
        """забыть картинки подсветки"""
        for name in ("target", "hover", "flash"):
            self.view.show_layer(name, None)
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
        """тип текущего вопроса (quiz.KINDS); без игры - режим: study, find, name, facts или mix"""
        s = self.session
        return s.kind if s is not None and not s.finished else self.mode

    def on_move(self, x, y):
        """мышь над схемой; x, y - в пикселях схемы"""
        if not self.ready() or self.kind() not in ("study", "find"):   # отвечают кнопками; в «Угадай название» подсвечен вопрос
            return
        if self.kind() == "find" and self.session and self.session.level == "hard":
            return                                      # на сложном уровне орган под курсором не подсвечивается
        key = self.atlas.organ_at(x, y)
        if key != self.cur:
            self.cur = key
            self.set_hover(key)
        d = self.view.dpr()
        tip = (x / d, y / d, i18n.name(key)) if key and self.mode == "study" else None     # в викторине - без названия
        if tip != self.view.tip:
            self.view.tip = tip
            self.view.update()

    def on_leave(self):
        if self.atlas is None:
            return
        self.cur = None
        self.set_hover(None)
        self.view.tip = None
        self.view.update()

    def on_click(self, x, y):
        if not self.ready():
            return
        key = self.atlas.organ_at(x, y)
        if key is None or self.kind() not in ("study", "find"):
            return
        if self.mode != "study":
            self.answer(key)
            return
        self.pause_tour()                               # щелчок по органу прерывает экскурсию (к ней можно вернуться)
        self.set_spot(None)
        self.show_info(key)

    def show_info(self, key):
        """карточка органа; под ней - возврат к прерванной экскурсии или к списку экскурсий"""
        def back():
            if self.paused is not None:
                return t("tour_resume", title=tours.title(self.paused[0])), self.resume_tour
            return t("tours_back"), self.end_tour
        self.set_card(lambda: fill_card(self.card, key, on_3d=lambda: show_3d(self, key), back=back(),
                                        on_link=self.open_link))

    def open_link(self, key):
        """щелчок по названию органа в карточке: открыть его карточку и подсветить на схеме"""
        self.show_info(key)
        self.set_spot(key if key in self.organs() else None)

    def update_buttons(self):
        for mode, b in self.mode_buttons.items():
            set_button_bg(b, "accent" if mode == self.mode else "card")
        for code, b in self.lang_buttons.items():
            set_button_bg(b, "accent" if code == i18n.current() else "card")

    def set_mode(self, mode):
        """study - изучение; режим викторины сначала показывает карточку настройки"""
        self.mode = mode
        self.tour = self.paused = None
        if SEARCH in self.toggles:
            self.toggles[SEARCH].clear()                # поиск сбрасывается вместе с подсветкой
        self.spot = None
        self.update_buttons()
        self.stop_quiz()
        self.show_panel()
        self.apply_view()                               # в викторине скрытые органы снова видны
        if mode == "study":
            self.set_status(lambda: t("hint"))
            self.set_card(self.empty_card)
            return
        self.set_status(lambda: t("setup_status"))
        self.set_card(self.render_setup)

    def stop_quiz(self):
        """прервать текущую игру: таймеры, подсветка, кнопки-варианты"""
        for tm in (self.next_timer, self.tick_timer, self.results_timer):
            tm.stop()
        self.session = None
        self.choices = {}
        if self.atlas:
            self.on_leave()
            self.view.show_layer("target", None)

    # --- настройка викторины
    def question_keys(self, qset, data=None):
        """органы набора вопросов qset (all, missed, due) в выбранной теме"""
        keys = in_system(self.organs(), self.cfg["topic"])
        if qset == "missed":
            return progress.last_missed(self.mode, keys, data)
        if qset == "due":
            return progress.due(self.mode, keys, data)
        return keys

    def topics(self):
        """темы викторины: [(система или None - все органы, сколько органов)]; системы из одного органа
        не предлагаются - по ним нечего спрашивать"""
        out = [(None, len(self.organs()))]
        for name in SYSTEMS:
            n = len(in_system(self.organs(), name))
            if n >= 2:
                out.append((name, n))
        return out

    def render_setup(self):
        data = progress.load()
        topics = self.topics()
        if self.cfg["topic"] not in dict(topics):
            self.cfg["topic"] = None
        counts = {q: len(self.question_keys(q, data)) for q in ("all", "missed", "due")}
        if not counts.get(self.cfg["set"]):
            self.cfg["set"] = "all"
        n = counts[self.cfg["set"]]
        length = self.cfg["length"] if 0 < self.cfg["length"] < n else 0     # длиннее набора - значит «все»
        rows = [
            (t("setup_level"), [(t("level_" + v), v, True) for v in LEVELS], self.cfg["level"],
             lambda v: self.set_cfg("level", v), t("level_hint_" + self.cfg["level"]), False),
            (t("setup_timer"), [(t("timer_sec", sec=v) if v else t("timer_off"), v, True) for v in TIMERS],
             self.cfg["timer"], lambda v: self.set_cfg("timer", v), None, False),
            (t("setup_length"), [(t("length_all", n=n) if not v else str(v), v, not v or v < n) for v in LENGTHS],
             length, lambda v: self.set_cfg("length", v), None, False),
            (t("setup_topic"), [(t("topic_all", n=k) if name is None else
                                 t("topic_system", system=t("system_" + name), n=k), name, True) for name, k in topics],
             self.cfg["topic"], lambda v: self.set_cfg("topic", v), None, 2),
            (t("setup_set"), [(t("set_" + q, n=counts[q]), q, counts[q] > 0) for q in ("all", "missed", "due")],
             self.cfg["set"], lambda v: self.set_cfg("set", v), t("setup_set_hint"), True),
        ]
        history = [t("history_line", date=self.short_date(r.get("date")), level=t("level_" + r.get("level", "medium")),
                     right=r.get("first_try", 0), total=r.get("total", 0), time=format_time(r.get("seconds", 0)))
                   for r in progress.recent(self.mode, 3, data)
                   if r.get("level") in LEVELS] or [t("history_empty")]
        fill_setup(self.card, t("mode_" + self.mode), t("setup_desc_" + self.mode), rows, t("setup_start"),
                   self.start_quiz, t("setup_history"), history)

    @staticmethod
    def short_date(iso):
        """'2026-10-25T14:03' -> '25.10 14:03'"""
        try:
            d, hm = (iso or "").split("T")
            return "%s.%s %s" % (d[8:10], d[5:7], hm[:5])
        except ValueError:
            return iso or ""

    def set_cfg(self, key, value):
        self.cfg[key] = value
        if key in ("level", "timer", "length"):
            settings.save(**{"quiz_" + key: value})
        self.set_card(self.render_setup)

    def start_quiz(self, qset=None):
        """начать игру по текущим настройкам; qset - другой набор вопросов (кнопка «Повторить ошибки»)"""
        qset = qset or self.cfg["set"]
        keys = self.question_keys(qset)
        if not keys:
            qset, keys = "all", self.question_keys("all")
        self.stop_quiz()
        self.qset = qset
        self.session = QuizSession(keys, pool=self.organs(), mode=self.mode, level=self.cfg["level"],
                                   timer=self.cfg["timer"], count=game_length(self.cfg["length"], len(keys)))
        self.ask()

    # --- вопросы
    def progress_text(self):
        s = self.session
        text = t("progress", n=s.i + 1, total=s.total, errors=s.errors)
        rem = s.remaining()
        return text + "  ·  " + t("progress_timer", sec=math.ceil(rem)) if rem is not None else text

    def ask(self, feedback=None):
        """показать текущий вопрос в карточке справа;
        feedback - (ключ текста, орган, цвет[, номер вопроса со своими вариантами]): отзыв о прошлом ответе"""
        s = self.session
        if s.finished:
            self.set_status(lambda: t("quiz_done", errors=s.errors, mode=t("mode_" + self.mode)))
            return
        if s.deadline is None:                          # новый вопрос на экране - запускаем его время
            s.start_timer()
            self.tick_timer.stop()
            self.tick()
        self.feedback, self.wrong = feedback, set()
        self.set_status(lambda: t("quiz_status", mode=t("mode_" + self.mode)))
        self.set_card(self.render_question)

    def render_question(self):
        s = self.session
        fb = self.feedback and (self.feedback_text(*self.feedback), self.feedback[2])
        if s.kind == "find":
            self.progress, self.choices = fill_question(
                self.card, self.progress_text(), t("find_title", name=i18n.name(s.current)),
                t("find_hint"), fb)
            self.show_target()                          # во «Вперемешку» прячет подсветку прошлого вопроса
            return
        opts = s.options()
        if s.kind == "facts" and s.custom():             # вопрос со своими вариантами ответа
            title, hint = s.prompt(), t("custom_hint", n=len(opts))
        elif s.kind == "facts":
            title, hint = "«%s»" % s.prompt(), t("facts_hint", n=len(opts))
        elif s.kind == "where":
            title, hint = "«%s»" % s.prompt(), t("where_hint", n=len(opts))
        elif s.kind == "system":
            title, hint = t("system_title", name=i18n.name(s.current)), t("custom_hint", n=len(opts))
        elif s.kind == "disease":
            title, hint = "«%s»" % s.prompt(), t("disease_hint", n=len(opts))
        elif s.kind == "latin":
            title, hint = s.prompt(), t("latin_hint", n=len(opts))
        elif s.kind == "truth":
            title, hint = "«%s»" % s.prompt(), t("truth_hint", name=i18n.name(s.current))
        else:
            title, hint = t("name_title"), t("name_hint", n=len(opts))
        self.progress, self.choices = fill_question(
            self.card, self.progress_text(), title, hint, fb, [(k, s.option_label(k)) for k in opts], self.pick)
        for k in self.wrong:
            mark(self.choices[k], "wrong_bg")
        self.show_target()

    def feedback_text(self, key, organ, _color, i=None):
        """текст отзыва на текущем языке; i - номер вопроса, ответ на который не орган: назвать верный ответ"""
        if i is not None:
            return t(key, answer=self.session.answer_text(i))
        return t(key, name=i18n.name(organ))

    def tick(self):
        """раз в четверть секунды: обновить остаток времени, а когда он вышел - показать ответ и идти дальше"""
        s = self.session
        if s is None or s.finished or s.remaining() is None:
            return
        if not self.next_timer.isActive():              # во время зелёной паузы после ответа не считаем
            i = s.i if s.answer_text(s.i) is not None else None      # ответ - не орган: назовём его
            key = s.time_up()
            if key:
                self.flash(key, "ok")                   # показать, где был нужный орган
                if s.finished:
                    self.finish(key)
                    return
                self.ask(("time_up", key, "bad") if i is None else ("time_up_answer", key, "bad", i))
                return
            if alive(self.progress):
                self.progress.setText(self.progress_text())
        self.tick_timer.start()

    def show_target(self):
        """подсветить орган текущего вопроса «Угадай название», а в «Изучать» - орган поиска или экскурсии;
        у вопроса другого типа подсветки нет"""
        if not self.ready():
            return
        s = self.session
        key = s.current if s is not None and s.kind == "name" else self.spot if self.mode == "study" else None
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

    def answer(self, key):
        """клик по органу в режиме «Найди орган»"""
        s = self.session
        if s is None or s.finished:
            return
        right = s.answer(key)
        self.flash(key, "ok" if right else "bad")
        if not right:
            self.ask(("answer_wrong", key, "bad"))
            return
        if s.finished:
            self.finish(key)
            return
        self.ask(("answer_right", key, "ok"))

    def pick(self, key):
        """выбран вариант ответа в режимах «Угадай название» и «Угадай по факту»"""
        s = self.session
        if s is None or s.finished or self.next_timer.isActive() or key not in self.choices:
            return
        asked = s.current
        right = s.answer(key)
        btn = self.choices[key]
        if not right:
            self.wrong.add(key)
            mark(btn, "wrong_bg")
            self.progress.setText(self.progress_text())
            return
        mark(btn, "right_bg")
        self.flash(asked, "ok")
        self.next_timer.start()

    def next_question(self):
        self.next_timer.stop()
        s = self.session
        if s is None:
            return
        if s.finished:
            self.finish(s.q[-1])
            return
        self.ask()

    def finish(self, last):
        """игра закончена: сохранить результат, показать карточку последнего органа и итоги"""
        s = self.session
        self.choices = {}
        self.view.show_layer("target", None)
        self.new_achievements, self.streak = [], 0
        try:
            before = progress.load()
            after = progress.record(s, self.qset)
            self.new_achievements = achievements.new_ones(before, after)
            self.streak = achievements.streak(after)
            self.ach_button.setText(achievements_text(after))
        except Exception:                               # история - не повод сорвать конец игры
            traceback.print_exc()
        self.set_card(lambda: fill_card(self.card, last))
        self.ask()
        self.results_timer.start()

    def keyPressEvent(self, e):
        """Esc закрывает верхнюю панель; остальное - on_key"""
        if e.key() == Qt.Key_Escape:
            overlay.close_top(self)
            return
        names = {Qt.Key_Right: "Right", Qt.Key_Left: "Left", Qt.Key_Return: "Return", Qt.Key_Enter: "KP_Enter"}
        self.on_key(names.get(e.key(), ""), e.text())

    def on_key(self, keysym, char):
        """цифры выбирают вариант ответа, Enter на карточке настройки начинает игру, стрелки листают экскурсию
        (но не тогда, когда поверх открыта панель: настройки, итоги или 3D, и не при наборе в поиске)"""
        if overlay.top(self) is not None or isinstance(QApplication.focusWidget(), QLineEdit):
            return
        if self.mode == "study":
            if self.tour is not None and keysym in ("Right", "Left", "Return", "KP_Enter"):
                self.tour_go(-1 if keysym == "Left" else 1)
            return
        if self.session is None:
            if keysym in ("Return", "KP_Enter"):
                self.start_quiz()
            return
        if self.kind() != "find" and char.isdigit():
            keys = list(self.choices)
            i = int(char) - 1
            if 0 <= i < len(keys):
                self.pick(keys[i])

    # --- экскурсии
    def start_tour(self, name):
        self.tour, self.paused = (name, 0), None
        self.set_spot(None)
        self.set_card(self.tour_card)

    def tour_go(self, step):
        """на step шагов вперёд или назад; после последнего органа - карточка «экскурсия пройдена»"""
        name, i = self.tour
        keys = tours.steps(name, self.body)
        i = max(0, min(len(keys) + 1, i + step))
        if i == self.tour[1]:
            return
        self.tour = (name, i)
        self.set_spot(keys[i - 1] if 1 <= i <= len(keys) else None)
        self.set_card(self.tour_card)

    def end_tour(self):
        """закончить экскурсию и показать список экскурсий"""
        self.tour = self.paused = None
        self.set_spot(None)
        self.set_card(self.empty_card)

    def pause_tour(self):
        """прервать экскурсию (щелчок по органу, поиск): запомнить шаг, чтобы к нему вернуться"""
        if self.tour is not None:
            self.paused, self.tour = self.tour, None

    def resume_tour(self):
        """вернуться к прерванной экскурсии на тот же шаг"""
        if self.paused is None:
            return
        name, i = self.tour = self.paused
        self.paused = None
        keys = tours.steps(name, self.body)
        self.set_spot(keys[i - 1] if 1 <= i <= len(keys) else None)
        self.set_card(self.tour_card)

    def tour_quiz(self, topic):
        """викторина «Вперемешку» по системе органов экскурсии: карточка настройки с выбранной темой"""
        self.set_mode("mix")
        self.set_cfg("topic", topic)

    def tour_card(self):
        if self.tour is None:                           # экскурсию закончили, пока карточка перерисовывалась
            self.empty_card()
            return
        name, i = self.tour
        keys = tours.steps(name, self.body)
        n = len(keys)
        back = (t("tour_back"), lambda: self.tour_go(-1), "card", i > 0)
        if i == 0:
            route = " → ".join(i18n.name(k) for k in keys)
            fill_tour(self.card, t("tour_label"), tours.title(name), None,
                      tours.intro(name) + "\n\n" + t("tour_route", route=route), "accent",
                      [(t("tour_start"), lambda: self.tour_go(1), "accent", True)],
                      [(t("tour_exit"), self.end_tour)], t("tour_keys"))
        elif i > n:
            topic = tours.TOPICS.get(name)
            extra = [(t("tour_quiz"), lambda: self.tour_quiz(topic))] if topic in dict(self.topics()) else []
            fill_tour(self.card, tours.title(name), t("tour_done"), None, t("tour_done_text", n=n), "accent",
                      [back, (t("tour_finish"), self.end_tour, "accent", True)], extra)
        else:
            key = keys[i - 1]
            fill_tour(self.card, t("tour_progress", title=tours.title(name), n=i, total=n), i18n.name(key),
                      i18n.subtitle(key), tours.story(name, key), ORGANS[key]["color"],
                      [back, (t("tour_next") if i < n else t("tour_last"), lambda: self.tour_go(1), "accent", True)],
                      [(t("card_3d"), lambda: show_3d(self, key)), (t("tour_exit"), self.end_tour)])

    def show_results(self):
        s, mode = self.session, self.mode
        if s is None or self.mode != s.mode:            # пока ждали, пользователь ушёл в другой режим
            return

        def again(qset=None):
            if self.mode == mode:
                self.start_quiz(qset)

        return show_results_dialog(self, s, on_again=again, on_retry=lambda: again("missed"),
                                   due=len(progress.due(mode, self.organs())), streak=self.streak,
                                   new=self.new_achievements, on_achievements=lambda: show_achievements(self))

    def paintEvent(self, _e):
        QPainter(self).fillRect(self.rect(), color("bg"))
