"""Общие виджеты (Qt): скруглённые кнопка и карточка, круглый флажок, строка поиска, карточки органа,
экскурсии и викторины, панель слоёв.

Цвета - роли текущей темы (theme.py). Кнопки, карточки, полоски и флажки рисуют себя сами (QPainter)
и берут цвет роли в момент рисования; у надписей роль цвета текста хранится на виджете (set_fg),
поэтому retheme() перекрашивает всё окно на лету, обойдя виджеты приложения.

Содержимое карточек складывается столбиком (QVBoxLayout) через put(): отступы слева-справа и сверху-снизу
задаются у каждого виджета, как pack(padx=..., pady=...) раньше."""

import colorsys

import shiboken6
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..organs import ORGANS, fact_of_day
from ..theme import C
from .scaling import fs, px


# --- цвета, шрифты, картинки

def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, w):
    """смешать цвета #rrggbb: w = 0 - a, 1 - b; результат - (r, g, b) 0..255"""
    return tuple(round(x + (y - x) * w) for x, y in zip(_rgb(a), _rgb(b)))


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def color(c):
    """QColor роли темы (bg, card, accent...) или цвета #rrggbb"""
    return QColor(C.get(c, c))


def font(size, bold=False, italic=False):
    """шрифт интерфейса: size - в пунктах при масштабе 100 %"""
    f = QFont(FONT)
    f.setPointSizeF(fs(size))
    f.setBold(bold)
    f.setItalic(italic)
    return f


def qimage(im):
    """картинка Pillow (RGB или RGBA) -> QImage (копия: данные Pillow можно отпускать)"""
    if im.mode == "RGBA":
        q = QImage(im.tobytes(), im.width, im.height, 4 * im.width, QImage.Format_RGBA8888)
        return q.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    im = im.convert("RGB")
    return QImage(im.tobytes(), im.width, im.height, 3 * im.width, QImage.Format_RGB888).copy()


def alive(w):
    return w is not None and shiboken6.isValid(w)


def set_fg(w, role):
    """цвет текста виджета - роль темы; запоминается, retheme() перекрасит её при смене темы"""
    w._fg = role
    pal = w.palette()
    for r in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(r, color(role))
    w.setPalette(pal)
    return w


def retheme(app=None):
    """перекрасить все виджеты в текущую тему (после theme.set_theme)"""
    app = app or QApplication.instance()
    for w in app.allWidgets():
        if hasattr(w, "_fg"):
            set_fg(w, w._fg)
        if hasattr(w, "retheme"):
            w.retheme()
        w.update()


# --- раскладка: столбик с отступами

def put(lay, w, top=0, bottom=0, x=16, align=None):
    """добавить виджет (или раскладку) в столбец lay с отступами в пикселях при масштабе 100 %:
    x - слева и справа (число или пара), top и bottom - сверху и снизу; align="left" - не растягивать
    по ширине, а прижать влево, "right" - вправо, "center" - по центру"""
    if top:
        lay.addSpacing(px(top))
    left, right = (x, x) if isinstance(x, (int, float)) else x
    row = QHBoxLayout()
    row.setContentsMargins(px(left), 0, px(right), 0)
    row.setSpacing(0)
    if align in ("right", "center"):
        row.addStretch(1)
    if isinstance(w, QWidget):
        row.addWidget(w)
    else:
        row.addLayout(w)
    if align in ("left", "center"):
        row.addStretch(1)
    lay.addLayout(row)
    if bottom:
        lay.addSpacing(px(bottom))
    return w


def clear(lay):
    """убрать всё содержимое раскладки (виджеты удаляются)"""
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear(item.layout())
            item.layout().deleteLater()


def hbox(spacing=0):
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(px(spacing))
    return lay


def vbox(parent=None, margins=(0, 0, 0, 0), spacing=0):
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(*(px(m) for m in margins))
    lay.setSpacing(px(spacing))
    return lay


# --- виджеты

class RoundButton(QAbstractButton):
    """плоская кнопка со скруглёнными углами. bg - роль фона (card - обычная, accent - главная,
    bg - цвета окна, right_bg / wrong_bg - верный и неверный ответ). Под курсором кнопка чуть светлее,
    при нажатии - цвета акцента; цвета меняются плавно"""

    FADE_MS, PRESS_MS = 150, 70     # длительность смены цвета: наведение и отпускание, нажатие

    def __init__(self, text="", command=None, bg="card", anchor="center", size=10, padx=14, pady=6, parent=None):
        super().__init__(parent)
        self.command = command
        self.anchor = anchor
        self.padx, self.pady = px(padx), px(pady)
        self.role, self.fg, self.dis_fg = bg, "text", "muted"
        self.shown = None           # (заливка, рамка, текст), которые сейчас на экране
        self.anim = None            # QVariantAnimation плавной смены цвета
        self.hover = False
        self.setText(text)
        self.setFont(font(size, bold=True))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.clicked.connect(self.invoke)
        set_button_bg(self, bg)

    def invoke(self):
        if self.isEnabled() and self.command:
            self.command()

    def set_command(self, command):
        self.command = command

    def set_padding(self, padx=None, pady=None):
        if padx is not None:
            self.padx = px(padx)
        if pady is not None:
            self.pady = px(pady)
        self.updateGeometry()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + 2 * self.padx + 2, fm.height() + 2 * self.pady)

    def minimumSizeHint(self):
        return self.sizeHint()

    def setText(self, text):
        if text != self.text():
            super().setText(text)
            self.updateGeometry()
            self.update()

    def colors(self):
        """(заливка, рамка, цвет текста) по состоянию кнопки; кнопка цвета фона - с рамкой"""
        bg, active = C[self.role], C["accent"]
        plain = self.role in ("card", "bg")
        if not self.isEnabled():
            return bg, C["border"] if plain else bg, C[self.dis_fg]
        if self.isDown():
            return active, active, C["on_accent"]
        fill = _hex(_mix(bg, active, 0.22) if bg != active else _mix(bg, "#ffffff", 0.16)) if self.hover else bg
        return fill, C["border"] if plain else fill, C[self.fg]

    def fade(self, ms=None):
        """плавно перейти от показанных сейчас цветов к цветам состояния за ms миллисекунд"""
        if self.anim is not None:
            self.anim.stop()
            self.anim = None
        end = self.colors()
        if self.shown is None or not self.isVisible() or self.shown == end:
            self.shown = end
            self.update()
            return
        start = self.shown
        a = QVariantAnimation(self)
        a.setDuration(ms or self.FADE_MS)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutQuad)

        def step(k):
            self.shown = tuple(_hex(_mix(x, y, k)) for x, y in zip(start, end))
            self.update()

        def done():
            if self.anim is a:
                self.anim = None
                self.shown = end
                self.update()

        a.valueChanged.connect(step)
        a.finished.connect(done)
        self.anim = a
        a.start()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.EnabledChange:
            self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)
            self.fade()

    def enterEvent(self, e):
        self.hover = True
        self.fade()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.fade()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.fade(self.PRESS_MS)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if alive(self):                          # команда могла удалить кнопку (новая карточка)
            self.fade()

    def retheme(self):
        if self.anim is not None:
            self.anim.stop()
            self.anim = None
        self.shown = self.colors()

    def paintEvent(self, _e):
        fill, outline, fg = self.shown or self.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = min(px(8), self.height() / 2)
        bw = max(1, px(1))
        p.setPen(QPen(QColor(outline), bw))
        p.setBrush(QColor(fill))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2), r, r)
        p.setPen(QColor(fg))
        p.setFont(self.font())
        if self.anchor == "w":
            p.drawText(self.rect().adjusted(self.padx, 0, -self.padx, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        else:
            p.drawText(self.rect(), Qt.AlignCenter, self.text())


def flat_button(text, command, bg="card", anchor="center", size=10, padx=14, pady=6, parent=None):
    return RoundButton(text, command, bg, anchor, size, padx, pady, parent)


def set_button_bg(b, bg, fg=None):
    """сменить роль фона кнопки (выбранный режим, язык, тема); текст подбирается к фону.
    У кнопки, которая уже на экране, цвет меняется плавно"""
    b.role = bg
    b.fg = fg or ("on_accent" if bg == "accent" else "on_mark" if bg in ("right_bg", "wrong_bg") else "text")
    b.dis_fg = "on_mark" if bg in ("right_bg", "wrong_bg") else "muted"
    b.fade()
    return b


class RoundCard(QFrame):
    """карточка со скруглёнными углами: заливка fill и рамка border (роли темы или #rrggbb).
    Содержимое - в self.lay (столбик). width - постоянная ширина"""

    def __init__(self, fill="card", border="border", radius=12, width=None, parent=None):
        super().__init__(parent)
        self.fill, self.border = fill, border
        self.r, self.bw = px(radius), max(1, px(1))
        self.lay = vbox(self)
        m = self.bw + px(2)
        self.lay.setContentsMargins(m, m, m, m)
        if width:
            self.setFixedWidth(width)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(color(self.border), self.bw))
        p.setBrush(color(self.fill))
        b = self.bw / 2
        p.drawRoundedRect(QRectF(self.rect()).adjusted(b, b, -b, -b), self.r, self.r)


def rounded_card(fill="card", border="border", radius=12, width=None, parent=None):
    return RoundCard(fill, border, radius, width, parent)


class Bar(QWidget):
    """цветная полоска со скруглёнными концами вверху карточки; c - роль темы или #rrggbb"""

    def __init__(self, c):
        super().__init__()
        self.c = c
        self.setFixedHeight(px(3))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(color(self.c))
        h = self.height()
        p.drawRoundedRect(QRectF(self.rect()), h / 2, h / 2)


def bar(lay, c):
    put(lay, Bar(c), top=1, x=8)


def label(text, fg="text", size=11, bold=False, italic=False, wrap=True, align=Qt.AlignLeft):
    w = QLabel(text)
    w.setFont(font(size, bold, italic))
    w.setWordWrap(wrap)
    w.setAlignment(align | Qt.AlignTop)
    w.setTextFormat(Qt.PlainText)
    return set_fg(w, fg)


def heading(lay, text, top=8, bottom=2, x=16):
    return put(lay, label(text.upper(), "muted", 9, bold=True, wrap=False), top=top, bottom=bottom, x=x)


def section(lay, title, text):
    heading(lay, title)
    put(lay, label(text))


def spacer(lay, h):
    lay.addSpacing(px(h))


def fill_card(card, key, on_3d=None, compact=False, back=None):
    """карточка органа; compact - без заболеваний и факта дня (для 3D-просмотра, где мало места по высоте);
    back - (текст, функция) кнопки под кнопкой 3D: вернуться к экскурсиям"""
    lay = card.lay
    clear(lay)
    c = ORGANS[key]["color"]
    bar(lay, c)                                                         # цветная полоска органа
    put(lay, label(i18n.name(key), size=15, bold=True), top=12)
    put(lay, label(i18n.subtitle(key), "muted", italic=True), bottom=6)
    put(lay, label(i18n.organ(key, "desc")), bottom=8)
    section(lay, t("card_location"), i18n.organ(key, "location"))
    section(lay, t("card_system"), ", ".join(t("system_" + x) for x in ORGANS[key]["systems"]))
    heading(lay, t("card_facts"))
    for f in i18n.organ(key, "facts"):
        put(lay, label("•  " + f), top=2, bottom=2)
    if not compact:
        section(lay, t("card_diseases"), "  ·  ".join(i18n.organ(key, "diseases")))
        day = rounded_card(fill="day_bg", border=c, radius=10)
        put(day.lay, label("★  " + t("card_fact_of_day"), "day_title", 10, bold=True), top=8, bottom=2, x=10)
        put(day.lay, label(fact_of_day(key)), bottom=8, x=10)
        put(lay, day, top=12)
    if on_3d:
        put(lay, flat_button(t("card_3d"), on_3d, bg="accent"), top=12, bottom=0 if back else 14, align="left")
    if back:
        put(lay, flat_button(back[0], back[1], anchor="w"), top=8 if on_3d else 12, bottom=14, align="left")
    if not on_3d and not back:
        spacer(lay, 10)


def fill_start(card, title, hint, tours_title, tours):
    """карточка режима «Изучать», пока орган не выбран: подсказка и кнопки экскурсий.
    tours - [(текст кнопки, функция)]"""
    lay = card.lay
    clear(lay)
    put(lay, label(title, size=15, bold=True), top=14, bottom=4)
    put(lay, label(hint, "muted"), bottom=6)
    if tours:
        heading(lay, tours_title)
        for text, command in tours:
            put(lay, flat_button(text, command, anchor="w", pady=4), top=3)
    spacer(lay, 14)


def fill_tour(card, progress, title, subtitle, text, c, buttons, extra=(), hint=None):
    """карточка шага экскурсии. progress - «Путь пищи · шаг 2 из 8»; c - цвет полоски (орган или роль);
    buttons - [(текст, функция, роль фона, доступна)] в строку (назад / дальше);
    extra - [(текст, функция)] кнопки столбиком под ними; hint - мелкая подсказка внизу"""
    lay = card.lay
    clear(lay)
    bar(lay, c)
    put(lay, label(progress, "muted", 10, bold=True), top=12)
    put(lay, label(title, size=15, bold=True), top=4)
    if subtitle:
        put(lay, label(subtitle, "muted", italic=True))
    put(lay, label(text), top=8, bottom=12)
    row = QGridLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setHorizontalSpacing(px(6))
    for i, (txt, command, bg, enabled) in enumerate(buttons):
        b = flat_button(txt, command, bg=bg)
        b.setEnabled(enabled)
        row.addWidget(b, 0, i)
        row.setColumnStretch(i, 1)
    put(lay, row)
    for txt, command in extra:
        put(lay, flat_button(txt, command, anchor="w"), top=6)
    if hint:
        put(lay, label(hint, "muted", 9), top=8)
    spacer(lay, 14)


def fill_question(card, progress, title, hint, feedback=None, options=(), on_pick=None):
    """карточка вопроса викторины.
    progress - строка «Вопрос N из M · Ошибок: K»; feedback - (текст, роль цвета) после ответа или None;
    options - [(ключ, название)] для кнопок-вариантов, on_pick(ключ) по нажатию.
    Возвращает (метка прогресса, {ключ: кнопка})."""
    lay = card.lay
    clear(lay)
    bar(lay, "accent")
    prog = put(lay, label(progress, "muted", 10, bold=True), top=12)
    put(lay, label(title, size=15, bold=True), top=4, bottom=4)
    put(lay, label(hint, "muted"), bottom=10)
    if feedback:
        put(lay, label(feedback[0], feedback[1], bold=True), bottom=10)
    buttons = {}
    for i, (key, name) in enumerate(options):
        b = put(lay, flat_button("%d.  %s" % (i + 1, name), lambda k=key: on_pick(k), anchor="w"), bottom=8)
        buttons[key] = b
    spacer(lay, 6)
    return prog, buttons


def mark(b, role):
    """покрасить кнопку-вариант: right_bg - верный ответ, wrong_bg - ошибка (такую больше не нажать)"""
    set_button_bg(b, role)
    if role == "wrong_bg":
        b.setEnabled(False)


# --- панель слоёв

def dot_colors(on, state):
    """(заливка, рамка, галочка) круглого флажка; state: normal, hover, press"""
    accent, ring, tick = C["accent"], C["muted"], C["on_accent"]
    if on:
        fill = {"normal": accent, "hover": _hex(_mix(accent, "#ffffff", 0.22)),
                "press": _hex(_mix(accent, "#000000", 0.25))}[state]
        return QColor(fill), QColor(fill), QColor(tick)
    outline = ring if state == "normal" else _hex(_mix(accent, "#ffffff", 0.22))
    fill = {"normal": QColor(0, 0, 0, 0), "hover": QColor(*_mix(accent, "#000000", 0.45), 110),
            "press": QColor(*_mix(accent, "#000000", 0.2), 200)}[state]
    return fill, QColor(outline), None


class Toggle(QWidget):
    """строка панели слоёв: круглый флажок и подпись; c - цветная метка органа слева.
    Щелчок по любому месту строки переключает, а подсвечивается при наведении и нажатии только кружок"""

    def __init__(self, text, on, command, c=None):
        super().__init__()
        self.command, self.on, self.c, self.text = command, on, c, text
        self.state = "normal"
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(font(9))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set(self, text, on):
        """обновить на месте (без пересоздания панели: так щелчок срабатывает сразу)"""
        if (text, on) != (self.text, self.on):
            self.text, self.on = text, on
            self.updateGeometry()
            self.update()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(px(4 + 8 + 16 + 7) + fm.horizontalAdvance(self.text), max(fm.height(), px(16)) + 2 * px(3))

    def minimumSizeHint(self):
        return QSize(px(40), self.sizeHint().height())

    def show_state(self, state):
        self.state = state
        self.update()

    def enterEvent(self, e):
        self.show_state("hover")

    def leaveEvent(self, e):
        self.show_state("normal")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.show_state("press")

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.rect().contains(e.position().toPoint()):
            self.show_state("hover")
            self.command()
        else:
            self.show_state("normal")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        if self.c:
            p.fillRect(0, 0, px(4), h, color(self.c))
        size = px(16)
        x, y = px(4 + 8), (h - size) / 2
        fill, outline, tick = dot_colors(self.on, self.state)
        w = max(1.0, size * 0.11)
        p.setPen(QPen(outline, w) if not self.on else Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(QRectF(x + w / 2, y + w / 2, size - w, size - w))
        if tick is not None:
            pen = QPen(tick, size * 0.12)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolyline([QPointF(x + a * size, y + b * size) for a, b in ((0.28, 0.52), (0.44, 0.68), (0.73, 0.36))])
        p.setPen(color("text" if self.on else "muted"))
        p.setFont(self.font())
        p.drawText(self.rect().adjusted(px(4 + 8 + 16 + 7), 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text)


def color_family(c):
    """семейство цвета #rrggbb для группировки органов в панели: 0 - розовые, 1 - красные, 2 - тёмно-красные,
    3 - тёплые (персиковые, песочные), 4 - зелёные, 5 - прочие. Возвращает (семейство, светлота)"""
    h, light, _ = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(c)))
    h *= 360
    if h >= 300 or h < 15:                                   # красные тона делятся по светлоте
        fam = 0 if light >= 0.65 else 2 if light < 0.4 else 1
    elif h < 60:
        fam = 3
    elif h < 180:
        fam = 4
    else:
        fam = 5
    return fam, light


def by_color(keys):
    """органы по семействам цвета, внутри семейства - от светлых к тёмным"""
    def order(k):
        fam, light = color_family(ORGANS[k]["color"])
        return fam, -light
    return sorted(keys, key=order)


SHOW_ALL = "_show_all"            # ключи кнопок в заголовках в словаре, который отдаёт fill_layers
ORGANS_ALL = "_organs_all"
ORGANS_LIST = "_organs_list"      # прокручиваемый список органов (ScrollArea)
SEARCH = "_search"                # строка поиска органа (SearchBox)
GROUPS = "_groups"                # [(подзаголовок системы, [органы группы])] - для фильтра поиска
NOTHING = "_nothing"              # надпись «ничего не найдено»


class SearchBox(QLineEdit):
    """строка поиска с подсказкой внутри (видна, пока поле пустое).
    on_change(текст) - при каждом изменении, on_enter(текст) - по Enter; Esc очищает поле"""

    def __init__(self, placeholder, text, on_change, on_enter):
        super().__init__(text)
        self.setPlaceholderText(placeholder)
        self.setFont(font(9))
        self.textChanged.connect(on_change)
        self.returnPressed.connect(lambda: on_enter(self.text()))
        self.retheme()

    def keyPressEvent(self, e):
        """Esc очищает поле; пустое поле Esc не трогает - он закроет панель поверх окна"""
        if e.key() == Qt.Key_Escape and self.text():
            self.clear()
            e.accept()
            return
        if e.key() == Qt.Key_Escape:
            e.ignore()
            return
        super().keyPressEvent(e)

    def retheme(self):
        self.setStyleSheet("QLineEdit {background: %s; color: %s; border: %dpx solid %s; border-radius: %dpx;"
                           " padding: %dpx %dpx; selection-background-color: %s; selection-color: %s}"
                           " QLineEdit:focus {border-color: %s}"
                           % (C["bg"], C["text"], max(1, px(1)), C["border"], px(6), px(3), px(6), C["accent"],
                              C["on_accent"], C["accent"]))
        pal = self.palette()
        pal.setColor(QPalette.PlaceholderText, color("muted"))
        self.setPalette(pal)


class ScrollArea(QScrollArea):
    """прокручиваемый список: содержимое - в self.lay, высота растёт за ним, пока хватает места в окне,
    а дальше список листается колесом, тачпадом или тонким ползунком справа"""

    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.inner = QWidget()
        self.inner.setObjectName("scrollInner")
        self.lay = vbox(self.inner)
        self.lay.setContentsMargins(0, 0, px(8), 0)                  # место под ползунок - всегда
        self.setWidget(self.inner)
        self.viewport().setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.retheme()

    def sizeHint(self):
        return QSize(self.inner.sizeHint().width(), self.inner.sizeHint().height())

    def minimumSizeHint(self):
        return QSize(self.inner.minimumSizeHint().width(), px(60))

    def retheme(self):
        w = px(4)
        self.setStyleSheet("QScrollArea, QWidget#scrollInner {background: transparent}"
                           " QScrollBar:vertical {background: transparent; width: %dpx; margin: 0}"
                           " QScrollBar::handle:vertical {background: %s; border-radius: %dpx; min-height: %dpx}"
                           " QScrollBar::add-line, QScrollBar::sub-line {height: 0}"
                           " QScrollBar::add-page, QScrollBar::sub-page {background: transparent}"
                           % (w, C["muted"], w // 2, px(16)))

    def refit(self):
        self.updateGeometry()


def filter_organs(buttons, visible):
    """оставить в списке органов панели слоёв только visible (и подзаголовки систем, где они есть);
    если не осталось ничего - надпись «ничего не найдено». Порядок прежний"""
    first = True
    for head, keys in buttons[GROUPS]:
        shown = [k for k in keys if k in visible]
        head.setVisible(bool(shown))
        for k in keys:
            buttons[k].setVisible(k in visible)
        if shown:
            first = False
    buttons[NOTHING].setVisible(first)
    area = buttons[ORGANS_LIST]
    area.refit()
    area.verticalScrollBar().setValue(0)


def show_all_button(buttons, visible):
    """показать или спрятать кнопку «Показать всё», не пересоздавая панель"""
    buttons[SHOW_ALL].setVisible(visible)


def header(lay, title, button, top):
    """заголовок раздела панели с маленькой кнопкой справа; button - (текст, функция)"""
    row = hbox()
    row.addWidget(label(title.upper(), "muted", 9, bold=True, wrap=False))
    row.addStretch(1)
    b = flat_button(button[0], button[1], size=8, padx=6, pady=0)
    row.addWidget(b)
    put(lay, row, top=top, bottom=4, x=0)
    return b


def fill_layers(card, title, layers, organs_title, groups, on_layer, on_organ, show_all, organs_all, search=None):
    """панель слоёв слева от схемы (только в режиме «Изучать»).
    layers - [(ключ, текст, виден)] слоёв тела; groups - [(название системы, [(ключ, название, цвет, виден)])]:
    органы по системам, у каждой группы - свой маленький подзаголовок;
    show_all - (текст, функция, видна ли) кнопки «Показать всё» (видна, когда что-то скрыто);
    organs_all - (текст, функция) кнопки «Скрыть все» / «Показать все» в заголовке органов;
    search - (подсказка, текст, on_change, on_enter, «ничего не найдено») строки поиска над списком органов.
    Кнопки - в строках заголовков, а список органов листается: низ панели может не поместиться в окно.
    Возвращает {ключ слоя или органа: Toggle}, кнопки заголовков под SHOW_ALL и ORGANS_ALL,
    ScrollArea списка органов под ORGANS_LIST, строку поиска под SEARCH и всё нужное для filter_organs."""
    lay = card.lay
    clear(lay)
    bar(lay, "accent")
    box = vbox()
    put(lay, box, bottom=10, x=12)
    buttons = {SHOW_ALL: header(box, title, show_all, 8)}
    show_all_button(buttons, show_all[2])
    for key, text, on in layers:
        buttons[key] = Toggle(text, on, lambda k=key: on_layer(k))
        box.addWidget(buttons[key])
        box.addSpacing(px(1))
    buttons[ORGANS_ALL] = header(box, organs_title, organs_all, 8)
    if search:
        buttons[SEARCH] = SearchBox(*search[:4])
        box.addWidget(buttons[SEARCH])
        box.addSpacing(px(6))
    area = buttons[ORGANS_LIST] = ScrollArea()
    box.addWidget(area, 1)
    buttons[GROUPS] = []
    for i, (system, organs) in enumerate(groups):
        head = label(system, "muted", 8, wrap=False)
        if i:
            area.lay.addSpacing(px(5))
        area.lay.addWidget(head)
        area.lay.addSpacing(px(1))
        for key, text, c, on in organs:
            buttons[key] = Toggle(text, on, lambda k=key: on_organ(k), c=c)
            area.lay.addWidget(buttons[key])
            area.lay.addSpacing(px(1))
        buttons[GROUPS].append((head, [k for k, *_ in organs]))
    buttons[NOTHING] = label(search[4] if search else "", "muted", 9)
    buttons[NOTHING].hide()
    area.lay.addWidget(buttons[NOTHING])
    area.lay.addStretch(1)
    return buttons


# --- карточка настройки викторины

def setup_button(b, text, command, selected, enabled):
    """кнопка варианта на карточке настройки: текст, действие, выбрана ли, доступна ли"""
    b.setText(text)
    b.set_command(command)
    b.setEnabled(enabled)
    set_button_bg(b, "accent" if selected else "card")


def fill_setup(card, title, desc, rows, start_text, on_start, history_title, history):
    """карточка настройки викторины перед стартом.
    rows - [(заголовок, [(текст, значение, доступен)], выбранное, on_pick(значение), подсказка, раскладка)];
    раскладка: False - в строку, True - столбиком, число - сеткой в столько столбцов;
    history - строки списка «последние игры» (если игр не было - одна строка-заглушка).
    Если в карточке уже такая же настройка (те же строки и столько же вариантов), она обновляется на месте:
    после щелчка по варианту карточка не пересоздаётся и не мигает."""
    texts = [title, desc]                                   # все надписи карточки по порядку
    for head, _options, _selected, _on_pick, hint, _vertical in rows:
        texts += [head.upper()] + ([hint] if hint else [])
    texts += [history_title.upper()] + list(history)
    choices = [(text, lambda v=value, f=on_pick: f(v), value == selected, enabled)
               for _head, options, selected, on_pick, _hint, _vertical in rows
               for text, value, enabled in options] + [(start_text, on_start, None, True)]
    shape = [(len(options), bool(hint), vertical) for _h, options, _s, _p, hint, vertical in rows] + [len(history)]
    old = getattr(card, "setup", None)
    if old and old[0] == shape and all(alive(w) and w.parentWidget() is card for w in old[1] + old[2]):
        for w, text in zip(old[1], texts):
            w.setText(text)
        for b, (text, command, selected, enabled) in zip(old[2], choices):
            if selected is None:                                        # «Начать»
                b.setText(text)
                b.set_command(command)
            else:
                setup_button(b, text, command, selected, enabled)
        return
    lay = card.lay
    clear(lay)
    labels, buttons = [], []
    bar(lay, "accent")
    labels.append(put(lay, label(title, size=15, bold=True), top=10))
    labels.append(put(lay, label(desc, "muted"), bottom=4))
    for head, options, _selected, _on_pick, hint, vertical in rows:
        labels.append(heading(lay, head))
        cols = vertical if isinstance(vertical, int) and vertical > 1 else 0          # True - тоже int (1)
        if cols:
            line = QGridLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setHorizontalSpacing(px(6))
            line.setVerticalSpacing(px(6))
            for c in range(cols):
                line.setColumnStretch(c, 1)
        elif vertical:
            line = vbox(spacing=3)
        else:
            line = hbox(spacing=6)
        for i in range(len(options)):
            text, command, selected, enabled = choices[len(buttons)]
            b = flat_button(text, command, anchor="w" if vertical else "center",
                            padx=10 if not vertical else 14, pady=4 if vertical else 6)
            setup_button(b, text, command, selected, enabled)
            buttons.append(b)
            if cols:
                line.addWidget(b, i // cols, i % cols)
            else:
                line.addWidget(b)
        if not vertical:
            line.addStretch(1)
        put(lay, line)
        if hint:
            labels.append(put(lay, label(hint, "muted", 9), top=4))
    buttons.append(put(lay, flat_button(start_text, on_start, bg="accent"), top=12, bottom=2))
    labels.append(heading(lay, history_title))
    for line in history:
        labels.append(put(lay, label(line, "muted", 10)))
    spacer(lay, 10)
    card.setup = (shape, labels, buttons)
