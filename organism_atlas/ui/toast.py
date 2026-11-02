"""Всплывающие уведомления внизу окна (новое достижение): плашка выезжает снизу и проявляется, через несколько
секунд гаснет сама; щелчок по ней - действие (открыть достижения) и плашка закрывается. Несколько плашек
встают столбиком, новая - внизу."""

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from .scaling import px
from .widgets import alive, color, hbox, label, vbox

SHOW_MS = 4500                  # сколько плашка видна
FADE_MS = 220                   # появление и угасание
GAP = 8                         # между плашками и от нижнего края окна (пиксели при масштабе 100 %)


def toasts(host):
    """плашки, которые сейчас на экране окна host (снизу вверх)"""
    items = [w for w in getattr(host, "_toasts", []) if alive(w)]
    host._toasts = items
    return items


def toast(host, title, text, command=None, tip=None):
    """показать плашку: title - мелко сверху (что случилось), text - крупно (что именно); command - по щелчку"""
    t = Toast(host, title, text, command, tip)
    toasts(host).insert(0, t)
    place(host, animate=True)
    t.appear()
    return t


def place(host, animate=False):
    """расставить плашки столбиком у нижнего края окна, по середине"""
    y = host.height() - px(GAP) - px(16)
    for t in toasts(host):
        y -= t.height()
        end = QPoint((host.width() - t.width()) // 2, y)
        if animate and t.isVisible() and t.pos() != end:
            t.move_to(end)
        else:
            t.move(end)
        y -= px(GAP)


class Toast(QWidget):
    def __init__(self, host, title, text, command=None, tip=None):
        super().__init__(host)
        self.host, self.command = host, command
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setCursor(Qt.PointingHandCursor if command else Qt.ArrowCursor)
        if tip:
            self.setToolTip(tip)
        row = hbox(spacing=12)
        row.setContentsMargins(px(16), px(10), px(20), px(10))
        self.setLayout(row)
        row.addWidget(label("★", "day_title", 18, bold=True, wrap=False), 0, Qt.AlignVCenter)
        col = vbox(spacing=1)
        col.addWidget(label(title.upper(), "muted", 8, bold=True, wrap=False))
        col.addWidget(label(text, "text", 12, bold=True, wrap=False, serif=True))
        row.addLayout(col)
        self.adjustSize()
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self.anims = []
        self.closing = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.vanish)

    def animate(self, prop, target, start, end, ms=FADE_MS, done=None):
        a = QPropertyAnimation(target, prop, self)
        a.setDuration(ms)
        a.setStartValue(start)
        a.setEndValue(end)
        a.setEasingCurve(QEasingCurve.OutCubic)
        if done:
            a.finished.connect(done)
        self.anims = [x for x in self.anims if x.state() == QPropertyAnimation.Running] + [a]
        a.start()

    def appear(self):
        """выехать снизу на px(16) и проявиться; через SHOW_MS - погаснуть"""
        self.show()
        self.raise_()
        end = self.pos()
        self.animate(b"pos", self, end + QPoint(0, px(16)), end)
        self.animate(b"opacity", self.effect, 0.0, 1.0)
        self.timer.start(SHOW_MS)

    def move_to(self, end):
        self.animate(b"pos", self, self.pos(), end)

    def vanish(self):
        if self.closing:
            return
        self.closing = True
        self.timer.stop()
        self.animate(b"opacity", self.effect, self.effect.opacity(), 0.0, done=self.drop)

    def drop(self):
        host = self.host
        if self in getattr(host, "_toasts", []):
            host._toasts.remove(self)
        self.hide()
        self.deleteLater()
        if alive(host):
            place(host, animate=True)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            command = self.command
            self.vanish()
            if command:
                QTimer.singleShot(0, command)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bw = max(1, px(1))
        r = QRectF(self.rect()).adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2)
        p.setPen(QPen(color("border"), bw))
        p.setBrush(color("card"))
        p.drawRoundedRect(r, px(10), px(10))
