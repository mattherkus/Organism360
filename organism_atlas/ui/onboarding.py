"""Подсказки при первом запуске: окно чуть затемняется, нужная часть интерфейса - в светлой рамке, рядом -
плашка с объяснением и кнопками «Пропустить» и «Дальше». Пять шагов: схема, слои, карточка, вкладки, клавиши.

Показываются один раз (настройка onboarding: show -> done), когда схема уже нарисована; снова - кнопкой
в настройках. Пока подсказка на экране, щелчки по окну и клавиши идут ей: Enter, пробел и → - дальше,
← - назад, Esc - пропустить."""

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import settings
from ..i18n import t
from .scaling import px
from .widgets import clear, color, flat_button, hbox, label, put, rounded_card, spacer

STEPS = ("scheme", "panel", "card", "tabs", "keys")   # тексты - tip_<шаг>_title и tip_<шаг> в lang/*.json
WAIT_MS = 200                   # как часто проверять, нарисована ли схема, перед первой подсказкой
WAIT_MAX = 50                   # столько проверок, потом - всё равно показать
BUBBLE_W = 340
SHADE = 150                     # непрозрачность затемнения (из 255)


def targets(app):
    """{шаг: функция -> QRect в координатах окна или None (плашка по центру)}"""
    def rect_of(*widgets):
        out = QRect()
        for w in widgets:
            if w is not None and w.isVisible():
                out = out.united(QRect(w.mapTo(app, QPoint(0, 0)), w.size()))
        return out if not out.isEmpty() else None

    return {"scheme": lambda: rect_of(app.stage),
            "panel": lambda: rect_of(app.panel),
            "card": lambda: rect_of(app.card_area),
            "tabs": lambda: rect_of(*app.mode_buttons.values(), *app.panel_tabs.values()),
            "keys": lambda: None}


def maybe_start(app):
    """при запуске программы: показать подсказки, если их ещё не видели"""
    if settings.get(settings.load(), "onboarding") == "show":
        start(app)


def start(app, tries=WAIT_MAX):
    """показать подсказки, как только схема нарисована (окно уже на экране)"""
    if not app.isVisible():
        return
    if not app.ready() and tries > 0:
        QTimer.singleShot(WAIT_MS, lambda: start(app, tries - 1))
        return
    old = getattr(app, "coach", None)
    if old is not None:
        old.finish(save=False)
    app.coach = Coach(app)


class Coach(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.i = 0
        self.where = targets(app)
        self.setFocusPolicy(Qt.StrongFocus)
        self.bubble = rounded_card(width=px(BUBBLE_W), parent=self)
        self._follow = _Follow(self)
        app.installEventFilter(self._follow)
        self.setGeometry(app.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.render_step()

    def render_step(self):
        step = STEPS[self.i]
        lay = self.bubble.lay
        clear(lay)
        put(lay, label("%d / %d" % (self.i + 1, len(STEPS)), "muted", 9, bold=True), top=12)
        put(lay, label(t("tip_%s_title" % step), size=14, bold=True, serif=True), top=2)
        put(lay, label(t("tip_" + step), size=10, serif=True), top=6, bottom=10)
        row = hbox(spacing=6)
        last = self.i == len(STEPS) - 1
        if not last:
            row.addWidget(flat_button(t("tip_skip"), lambda: self.finish(), padx=10))
        row.addStretch(1)
        if self.i > 0:
            row.addWidget(flat_button("←", lambda: self.go(-1), padx=10))
        row.addWidget(flat_button(t("tip_done") if last else t("tip_next"), lambda: self.go(1), bg="accent", padx=12))
        put(lay, row)
        spacer(lay, 12)
        b = self.bubble                                  # высота - по тексту при постоянной ширине
        for w in b.findChildren(QWidget):                # новые виджеты на видимой плашке Qt показал бы
            w.show()                                     # только в следующем цикле - и высота была бы меньше
        lay.activate()
        h = b.heightForWidth(b.width())
        b.resize(b.width(), h if h > 0 else b.sizeHint().height())
        self.place()

    def hole(self):
        """рамка вокруг части интерфейса текущего шага (с запасом) или None"""
        r = self.where[STEPS[self.i]]()
        return r.adjusted(-px(6), -px(6), px(6), px(6)) if r is not None else None

    def place(self):
        """плашка - рядом с рамкой: справа, слева, снизу или сверху, где помещается; без рамки - по центру"""
        self.setGeometry(self.app.rect())
        b, r = self.bubble, self.hole()
        w, h, gap = b.width(), b.height(), px(14)
        if r is None:
            x, y = (self.width() - w) // 2, (self.height() - h) // 2
        elif r.right() + gap + w <= self.width():
            x, y = r.right() + gap, r.top() + px(10)
        elif r.left() - gap - w >= 0:
            x, y = r.left() - gap - w, r.top() + px(10)
        elif r.bottom() + gap + h <= self.height():
            x, y = r.left() + px(10), r.bottom() + gap
        else:
            x, y = r.left() + px(10), r.top() - gap - h
        x = max(px(8), min(x, self.width() - w - px(8)))
        y = max(px(8), min(y, self.height() - h - px(8)))
        b.move(x, y)
        b.raise_()
        self.update()

    def go(self, step):
        i = self.i + step
        if i >= len(STEPS):
            self.finish()
            return
        self.i = max(0, i)
        self.render_step()

    def finish(self, save=True):
        """подсказки пройдены или пропущены: больше сами не показываются"""
        if save:
            settings.save(onboarding="done")
        self.app.removeEventFilter(self._follow)
        if getattr(self.app, "coach", None) is self:
            self.app.coach = None
        self.hide()
        self.deleteLater()
        self.app.setFocus()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        r = self.hole()
        if r is not None:
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(r), px(12), px(12))
            shade = shade.subtracted(hole)
        p.fillPath(shade, QColor(0, 0, 0, SHADE))
        if r is not None:
            p.setPen(QPen(color("accent"), max(2, px(2))))
            p.drawRoundedRect(QRectF(r), px(12), px(12))
        p.end()

    def mousePressEvent(self, e):
        e.accept()                                       # окно под подсказкой не нажимается

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self.finish()
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space, Qt.Key_Right):
            self.go(1)
        elif k == Qt.Key_Left:
            self.go(-1)
        e.accept()


class _Follow(QObject):
    """окно поменяло размер - подсказка следует за ним"""

    def __init__(self, coach):
        super().__init__(coach)
        self.coach = coach

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            QTimer.singleShot(0, self.coach.place)
        return False
