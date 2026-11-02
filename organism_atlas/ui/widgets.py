"""Общие виджеты (Qt): цвета и шрифты, раскладка столбиком, скруглённые кнопка и карточка, полоски, надписи
со ссылками. Из них собраны карточки справа (cards.py) и панель слоёв (layers_panel.py).

Шрифт - FONT, а заголовки и текст статей (serif=True) - с засечками, как в атласе (config.SERIF).

Цвета - роли текущей темы (theme.py). Кнопки, карточки, полоски и флажки рисуют себя сами (QPainter)
и берут цвет роли в момент рисования; у надписей роль цвета текста хранится на виджете (set_fg),
поэтому retheme() перекрашивает всё окно на лету, обойдя виджеты приложения.

Содержимое карточек складывается столбиком (QVBoxLayout) через put(): отступы слева-справа и сверху-снизу
задаются у каждого виджета, как pack(padx=..., pady=...) раньше."""

import html

import shiboken6
from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
                               QWidget)

from .. import i18n
from ..config import FONT, SERIF
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


def font(size, bold=False, italic=False, serif=False):
    """шрифт интерфейса: size - в пунктах при масштабе 100 %; serif - с засечками (заголовки, статьи)"""
    f = QFont(FONT)
    if serif:
        f.setFamilies(list(SERIF))
    f.setPointSizeF(fs(size))
    f.setBold(bold)
    f.setItalic(italic)
    return f


def qimage(im):
    """картинка Pillow (RGB или RGBA) -> QImage (копия: данные Pillow можно отпускать).
    Формат - родной для рисования Qt (RGB32 или ARGB32_Premultiplied): такая картинка кладётся на экран
    как есть, а RGB888 Qt перекодировал бы при каждой перерисовке (и медленно растягивал бы при приближении)"""
    if im.mode == "RGBA":
        q = QImage(im.tobytes(), im.width, im.height, 4 * im.width, QImage.Format_RGBA8888)
        return q.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    im = im.convert("RGB")
    return QImage(im.tobytes(), im.width, im.height, 3 * im.width, QImage.Format_RGB888).convertToFormat(
        QImage.Format_RGB32)


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
        self.key_hint = None        # клавиша, которая нажимает кнопку («1»): рисуется значком слева от текста
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

    def key_width(self):
        """место под значок клавиши слева (0 - значка нет)"""
        return self.key_size().width() + px(8) if self.key_hint else 0

    def key_size(self):
        fm = QFontMetrics(font(8, bold=True))
        h = fm.height() + px(2)
        return QSize(max(h, fm.horizontalAdvance(self.key_hint or "") + px(8)), h)

    def set_key_hint(self, key):
        self.key_hint = key
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + 2 * self.padx + 2 + self.key_width(),
                     fm.height() + 2 * self.pady)

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
        left = self.padx
        if self.key_hint:                        # значок клавиши - скруглённая «клавиша» в цвет текста
            ks = self.key_size()
            box = QRectF(left, (self.height() - ks.height()) / 2, ks.width(), ks.height())
            p.setPen(QPen(QColor(fg), bw))
            p.setBrush(Qt.NoBrush)
            p.setOpacity(0.55)
            p.drawRoundedRect(box, px(4), px(4))
            p.setOpacity(0.8)
            p.setFont(font(8, bold=True))
            p.drawText(box, Qt.AlignCenter, self.key_hint)
            p.setOpacity(1.0)
            left += self.key_width()
        p.setPen(QColor(fg))
        p.setFont(self.font())
        if self.anchor == "w":
            p.drawText(self.rect().adjusted(left, 0, -self.padx, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())
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


class Meter(QWidget):
    """тонкая полоска-шкала: дорожка цвета рамки и заполненная доля value (0..1) цвета c"""

    def __init__(self, c, value=0.0, height=6):
        super().__init__()
        self.c, self.value = c, value
        self.setFixedHeight(px(height))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set(self, value, c=None):
        value = max(0.0, min(1.0, value))
        if (value, c or self.c) != (self.value, self.c):
            self.value, self.c = value, c or self.c
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        h = r.height()
        p.setBrush(color("border"))
        p.drawRoundedRect(r, h / 2, h / 2)
        if self.value > 0:
            p.setBrush(color(self.c))
            p.drawRoundedRect(QRectF(r.x(), r.y(), max(h, r.width() * self.value), h), h / 2, h / 2)


class QuizProgress(QWidget):
    """шапка вопроса викторины: строка «Вопрос N из M · Ошибок: K», шкала пройденных вопросов
    и (если включён таймер) шкала оставшегося времени, которая к концу краснеет"""

    def __init__(self, text, done, time_left=None):
        super().__init__()
        lay = vbox(self, spacing=4)
        self.label = label(text, "muted", 10, bold=True)
        lay.addWidget(self.label)
        self.done = Meter("accent", done)
        lay.addWidget(self.done)
        self.time = Meter("ok", 1.0, height=4)
        lay.addWidget(self.time)
        self.time.setVisible(time_left is not None)
        self.set(text, done, time_left)

    def text(self):
        return self.label.text()

    def setText(self, text):
        self.label.setText(text)

    def set(self, text, done, time_left=None):
        """time_left - доля оставшегося времени (0..1) или None - таймера нет"""
        self.label.setText(text)
        self.done.set(done)
        if time_left is not None:
            self.time.set(time_left, "ok" if time_left > 0.5 else "day_title" if time_left > 0.25 else "bad")


def label(text, fg="text", size=11, bold=False, italic=False, wrap=True, align=Qt.AlignLeft, serif=False):
    w = QLabel(text)
    w.setFont(font(size, bold, italic, serif))
    w.setWordWrap(wrap)
    w.setAlignment(align | Qt.AlignTop)
    w.setTextFormat(Qt.PlainText)
    return set_fg(w, fg)


def rich_label(pieces, on_link, fg="text", size=11, bold=False, serif=False):
    """надпись из кусков [(текст, ключ или None)]: куски с ключом - ссылки, щелчок вызывает on_link(ключ).
    Без ссылок (или без on_link) - обычная надпись"""
    text = "".join(piece for piece, _ in pieces)
    w = label(text, fg, size, bold, serif=serif)
    if on_link is None or not any(key for _, key in pieces):
        return w
    rich = '<span style="white-space:pre-wrap">%s</span>' % "".join(          # пробелы как в тексте
        '<a href="%s" style="color:{link}">%s</a>' % (key, html.escape(piece)) if key else html.escape(piece)
        for piece, key in pieces)
    # цвет ссылки Qt берёт не из палитры надписи, поэтому он вписан в текст и обновляется при смене темы
    w.retheme = lambda: w.setText(rich.replace("{link}", C.get("accent_fg")))
    w.setTextFormat(Qt.RichText)
    w.retheme()
    w.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
    # окно пересобирается после щелчка, а не внутри него: надпись-отправитель ещё обрабатывает мышь
    w.linkActivated.connect(lambda key: QTimer.singleShot(0, lambda: on_link(key)))
    return w


def linked(text, on_link, seen, fg="text", size=11, serif=False):
    """надпись, где названия органов и болезней - ссылки, как в статье: щелчок вызывает on_link(ключ).
    seen - ключи, которые уже стали ссылкой выше (и сам орган или болезнь статьи): ссылка на каждый
    одна, при первом упоминании. Без on_link - обычная надпись. serif - шрифт статьи"""
    if on_link is None:
        return label(text, fg, size, serif=serif)
    pieces = []
    for piece, key in i18n.links(text):
        if key in seen:
            key = None
        elif key is not None:
            seen.add(key)
        pieces.append((piece, key))
    return rich_label(pieces, on_link, fg, size, serif=serif)


def joined(items, sep):
    """[(текст, ключ)] через разделитель -> куски для rich_label"""
    out = []
    for i, item in enumerate(items):
        if i:
            out.append((sep, None))
        out.append(item)
    return out


def spaced(w, percent=108):
    """разрядка букв надписи (подзаголовки прописными)"""
    f = w.font()
    f.setLetterSpacing(QFont.PercentageSpacing, percent)
    w.setFont(f)
    return w


def heading(lay, text, top=8, bottom=2, x=16):
    return put(lay, spaced(label(text.upper(), "muted", 9, bold=True, wrap=False)), top=top, bottom=bottom, x=x)


def section(lay, title, text, on_link=None, seen=None, serif=False):
    heading(lay, title)
    put(lay, linked(text, on_link, seen, serif=serif))


class Dot(QWidget):
    """цветной кружок-значок (система органов в карточке и в панели слоёв); c - роль темы или #rrggbb"""

    def __init__(self, c, size=9):
        super().__init__()
        self.c = c
        self.setFixedSize(px(size), px(size))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(color(self.c))
        p.drawEllipse(QRectF(self.rect()))


def kicker(lay, items, top=10, bottom=0, x=16):
    """строка над заголовком статьи: [(цвет значка или None, текст)] прописными цвета акцента, через « · »"""
    row = hbox(spacing=5)
    for i, (c, text) in enumerate(items):
        if i:
            row.addSpacing(px(3))
            row.addWidget(spaced(label("·", "accent_fg", 9, bold=True, wrap=False)))
            row.addSpacing(px(3))
        if c:
            row.addWidget(Dot(c), 0, Qt.AlignVCenter)
        row.addWidget(spaced(label(text.upper(), "accent_fg", 9, bold=True, wrap=False), 112))
    row.addStretch(1)
    return put(lay, row, top=top, bottom=bottom, x=x)


class TabButton(RoundButton):
    """вкладка в шапке окна (режим или панель): текст без заливки, у выбранной (роль фона accent) - черта акцента
    снизу, у невыбранной под курсором - черта цвета рамки; недоступная - бледная. Роль и цвета - как
    у RoundButton (set_button_bg)"""

    def __init__(self, text="", command=None, size=11, parent=None):
        super().__init__(text, command, "card", "center", size, 4, 6, parent)
        f = font(size)
        f.setWeight(QFont.DemiBold)
        self.setFont(f)

    def selected(self):
        return self.role == "accent"

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isEnabled() and (self.selected() or self.hover)
        p.setPen(color("text" if on else "muted"))
        if not self.isEnabled():
            p.setOpacity(0.45)
        p.setFont(self.font())
        p.drawText(self.rect().adjusted(0, 0, 0, -px(2)), Qt.AlignCenter, self.text())
        if on:
            h = max(2, px(2))
            p.fillRect(QRectF(self.padx, self.height() - h, self.width() - 2 * self.padx, h),
                       color("accent" if self.selected() else "border"))


class Ring(QWidget):
    """кольцо доли value (0..1) цвета c на дорожке цвета рамки, в середине - крупный текст (процент)
    и подпись под ним мелко: итоги викторины"""

    def __init__(self, value, c, text, caption="", size=128):
        super().__init__()
        self.value, self.c, self.text, self.caption = max(0.0, min(1.0, value)), c, text, caption
        self.setFixedSize(px(size), px(size))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = px(10)
        r = QRectF(self.rect()).adjusted(w / 2 + 1, w / 2 + 1, -w / 2 - 1, -w / 2 - 1)
        pen = QPen(color("border"), w)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 0, 360 * 16)
        if self.value > 0:
            pen.setColor(color(self.c))
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -round(360 * 16 * self.value))     # от верха по часовой стрелке
        big = font(22, bold=True, serif=True)
        fm = QFontMetrics(big)
        small = font(7.5, bold=True)
        sh = QFontMetrics(small).height() if self.caption else 0
        top = (self.height() - fm.height() - sh) / 2
        p.setPen(color("text"))
        p.setFont(big)
        p.drawText(QRectF(0, top, self.width(), fm.height()), Qt.AlignCenter, self.text)
        if self.caption:
            p.setPen(color("muted"))
            p.setFont(small)
            p.drawText(QRectF(0, top + fm.height(), self.width(), sh), Qt.AlignCenter, self.caption)


def spacer(lay, h):
    lay.addSpacing(px(h))
