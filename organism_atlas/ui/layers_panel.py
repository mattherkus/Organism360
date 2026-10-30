"""Панель слоёв слева: круглые флажки слоёв и органов (Toggle), органы по семействам цвета,
строка поиска органа, прокручиваемый список и ползунок прозрачности кожи. SearchBox и ScrollArea
нужны и справочнику болезней (diseases.py), Toggle - списку частей в 3D-просмотре."""

import colorsys

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QScrollArea, QSizePolicy, QSlider, QWidget

from ..organs import ORGANS
from ..theme import C
from .scaling import px
from .widgets import _hex, _mix, _rgb, bar, clear, color, flat_button, font, hbox, label, put, set_fg, vbox


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
SKIN = "_skin"                    # ползунок прозрачности кожи (Slider)


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


class ClickLabel(QLabel):
    """надпись, которая нажимается как кнопка: под курсором светлеет, щелчок вызывает command()"""

    def __init__(self, text, command, fg="muted", size=9, bold=False, tip=None):
        super().__init__(text)
        self.command, self.fg = command, fg
        self.setFont(font(size, bold))
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)
        set_fg(self, fg)

    def enterEvent(self, e):
        set_fg(self, "text")
        self._fg = self.fg                       # при смене темы - обычный цвет
        super().enterEvent(e)

    def leaveEvent(self, e):
        set_fg(self, self.fg)
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            QTimer.singleShot(0, self.command)  # панель может пересобраться: надпись ещё обрабатывает мышь


class Slider(QSlider):
    """горизонтальный ползунок в цветах темы"""

    def __init__(self, value, lo, hi, step, on_change, tip=None):
        super().__init__(Qt.Horizontal)
        self.setRange(lo, hi)
        self.setSingleStep(step)
        self.setPageStep(step * 4)
        self.setValue(value)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        if tip:
            self.setToolTip(tip)
        self.valueChanged.connect(on_change)
        self.retheme()

    def retheme(self):
        h = px(14)
        self.setStyleSheet(
            "QSlider {background: transparent; height: %dpx}"
            " QSlider::groove:horizontal {height: %dpx; background: %s; border-radius: %dpx}"
            " QSlider::sub-page:horizontal {background: %s; border-radius: %dpx}"
            " QSlider::handle:horizontal {background: %s; width: %dpx; margin: -%dpx 0; border-radius: %dpx}"
            % (h + 2, px(4), C["border"], px(2), C["accent"], px(2), C["text"], h, (h - px(4)) // 2, h // 2))


def header(lay, title, button, top, on_title=None, tip=None):
    """заголовок раздела панели с маленькой кнопкой справа; button - (текст, функция);
    on_title - щелчок по самому заголовку (свернуть раздел)"""
    row = hbox()
    if on_title:
        row.addWidget(ClickLabel(title.upper(), on_title, size=9, bold=True, tip=tip))
    else:
        row.addWidget(label(title.upper(), "muted", 9, bold=True, wrap=False))
    row.addStretch(1)
    b = flat_button(button[0], button[1], size=8, padx=6, pady=0)
    row.addWidget(b)
    put(lay, row, top=top, bottom=4, x=0)
    return b


def fill_layers(card, title, layers, organs_title, groups, on_layer, on_organ, show_all, organs_all, search=None,
                fold=None, skin=None, on_system=None, system_tip=None):
    """панель слоёв слева от схемы (только в режиме «Изучать»).
    layers - [(ключ, текст, виден)] слоёв тела; groups - [(система, название системы, [(ключ, название, цвет, виден)])]:
    органы по системам, у каждой группы - свой маленький подзаголовок; щелчок по нему - on_system(система);
    show_all - (текст, функция, видна ли) кнопки «Показать всё» (видна, когда что-то скрыто);
    organs_all - (текст, функция) кнопки «Скрыть все» / «Показать все» в заголовке органов;
    search - (подсказка, текст, on_change, on_enter, «ничего не найдено») строки поиска над списком органов;
    fold - (раскрыт ли раздел слоёв, функция): щелчок по заголовку «Слои» сворачивает и разворачивает его;
    skin - (прозрачность кожи 0..100, on_change, подсказка): ползунок под строкой кожи.
    Кнопки - в строках заголовков, а список органов листается: низ панели может не поместиться в окно.
    Возвращает {ключ слоя или органа: Toggle}, кнопки заголовков под SHOW_ALL и ORGANS_ALL,
    ScrollArea списка органов под ORGANS_LIST, строку поиска под SEARCH, ползунок кожи под SKIN
    и всё нужное для filter_organs."""
    lay = card.lay
    clear(lay)
    bar(lay, "accent")
    box = vbox()
    put(lay, box, bottom=10, x=12)
    is_open = fold is None or fold[0]
    title = ("▾  " if is_open else "▸  ") + title if fold else title
    buttons = {SHOW_ALL: header(box, title, show_all, 8, on_title=fold and fold[1])}
    show_all_button(buttons, show_all[2])
    for key, text, on in layers:
        buttons[key] = Toggle(text, on, lambda k=key: on_layer(k))
        box.addWidget(buttons[key])
        box.addSpacing(px(1))
        if not is_open:                            # прятать - уже в раскладке: без родителя виджет стал бы окном
            buttons[key].hide()
        if key == "skin" and skin:
            buttons[SKIN] = Slider(skin[0], 0, 100, 5, skin[1], skin[2])
            row = hbox()
            row.setContentsMargins(px(4 + 8 + 16 + 7), 0, px(6), px(2))
            row.addWidget(buttons[SKIN])
            box.addLayout(row)
            if not (is_open and on):
                buttons[SKIN].hide()
    buttons[ORGANS_ALL] = header(box, organs_title, organs_all, 8)
    if search:
        buttons[SEARCH] = SearchBox(*search[:4])
        box.addWidget(buttons[SEARCH])
        box.addSpacing(px(6))
    area = buttons[ORGANS_LIST] = ScrollArea()
    box.addWidget(area, 1)
    buttons[GROUPS] = []
    for i, (system, name, organs) in enumerate(groups):
        if on_system:
            head = ClickLabel(name, lambda s=system: on_system(s), size=8, tip=system_tip)
        else:
            head = label(name, "muted", 8, wrap=False)
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
