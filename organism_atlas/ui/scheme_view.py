"""Схема тела на экране (SchemeView): слои-картинки поверх готовой схемы (подсветка, анимация), приближение
колесом, кнопками и клавишами, перетаскивание мышью. Рисуется под всем окном; Stage - её место в раскладке
окна, а slide() плавно уводит интерфейс к краям, когда схема сильно приближена."""

import math

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, QSizeF, Qt,
                            QVariantAnimation)
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .scaling import px
from .widgets import color, flat_button, font


ZOOM_STEPS = (1.0, 1.25, 1.6, 2.0, 2.5, 3.2, 4.0)     # приближение схемы колесом и кнопками
HIDE_FROM = ZOOM_STEPS[2]                              # с такого приближения интерфейс уезжает к краям окна
ZOOM_MS = 220                                          # длительность анимации приближения
SLIDE_MS = 260                                         # длительность выезда интерфейса
DRAG_PX = 5                                            # сдвиг мыши, после которого нажатие - перетаскивание


def slide(w, start, end, done=None):
    """плавно передвинуть виджет из start в end (координаты родителя); done - после"""
    old = getattr(w, "_slide", None)
    if old is not None:
        old.stop()
    a = QPropertyAnimation(w, b"pos", w)
    a.setDuration(SLIDE_MS)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(QEasingCurve.InOutCubic)
    if done:
        a.finished.connect(done)
    w._slide = a
    a.start()


class SchemeView(QWidget):
    """схема тела: картинки в пикселях экрана (масштаб Z подобран под них) и поверх - кусок анимации,
    подсветка органа-вопроса, органа под курсором и вспышка ответа, подсказка с названием, подпись
    верного ответа и надпись «рисуется»/«перерисовывается». Координаты мыши передаются окну в пикселях схемы.
    Схему можно приблизить (колесо, +/−) и двигать мышью: k - во сколько раз, pan - где левый верхний угол.
    Виджет лежит под всем окном: приближенная схема продолжается под панелями и карточкой, без рамки.
    Перерисовывается только то, что поменялось: кадр анимации, подсветка или подсказка - своим прямоугольником,
    а не всё окно с панелями и карточкой поверх схемы (их Qt иначе перерисовывал бы вместе с ней)"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.base = None                # QImage схемы (пока чёткая не готова - прежняя, растягивается)
        self.layers = {"anim": None, "target": None, "hover": None, "flash": None, "reveal": None}
        self.tip = None                 # (x, y, текст) в логических пикселях
        self.pin = None                 # (x, y, текст) - подпись органа в пикселях схемы (верный ответ)
        self.message = None             # (текст, внизу ли) - «Рисуется схема...» или «перерисовывается»
        self.k, self.pan = 1.0, QPointF(0, 0)
        self.scheme = QSizeF(1, 1)      # размер схемы при k = 1 в логических пикселях
        self.start = self.goal = None   # (k, угол схемы в координатах окна) в начале и в конце анимации
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(ZOOM_MS)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self.step)
        self.anim.finished.connect(self.finish)
        self.press = None               # (точка нажатия, pan в тот момент, кнопка) или None
        self.dragging = False
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)       # закрашивает себя целиком: окно под ней не рисуется

    def dpr(self):
        return self.devicePixelRatioF()

    def area(self, x, y, w, h):
        """прямоугольник схемы (пиксели схемы) -> накрывающий его прямоугольник виджета с запасом на сглаживание"""
        d, k = self.dpr(), self.k
        r = QRectF(self.pan.x() + k * x / d, self.pan.y() + k * y / d, k * w / d, k * h / d)
        return r.toAlignedRect().adjusted(-2, -2, 2, 2)

    def show_layer(self, name, item):
        """item - (QImage, (x, y)) в пикселях схемы или None - спрятать. Перерисовываются только прежнее
        и новое место слоя"""
        old = self.layers[name]
        new = None if item is None else (item[0], item[1][0], item[1][1])
        self.layers[name] = new
        for it in (old, new):
            if it is not None:
                self.update(self.area(it[1], it[2], it[0].width(), it[0].height()))

    def set_tip(self, tip):
        """подсказка с названием у курсора: (x, y, текст) в логических пикселях или None"""
        if tip == self.tip:
            return
        for it in (self.tip, tip):
            if it is not None:
                self.update(self.tip_rect(it).toAlignedRect().adjusted(-3, -3, 3, 3))
        self.tip = tip

    def set_pin(self, pin):
        """подпись органа со стрелкой (верный ответ): (x, y, текст) в пикселях схемы или None"""
        if pin == self.pin:
            return
        for it in (self.pin, pin):
            if it is not None:
                self.update(self.pin_rect(it).toAlignedRect().adjusted(-3, -3, 3, 3))
        self.pin = pin

    # --- приближение
    def to_screen(self, x, y):
        """точка схемы (пиксели схемы) -> логические пиксели виджета с учётом приближения"""
        d = self.dpr()
        return self.pan.x() + self.k * x / d, self.pan.y() + self.k * y / d

    def to_scheme(self, pos):
        """логическая точка виджета -> пиксели схемы"""
        d = self.dpr()
        return (pos.x() - self.pan.x()) / self.k * d, (pos.y() - self.pan.y()) / self.k * d

    def set_size(self, w, h):
        """новый размер схемы (масштаб окна поменялся): она снова целиком на своём месте"""
        self.scheme = QSizeF(w, h)
        self.reset_zoom(animate=False)

    def home(self):
        """левый верхний угол схемы при k = 1: на её месте в раскладке окна (по центру сверху)"""
        stage = self.app.stage
        x = max(0, (stage.width() - math.ceil(self.scheme.width())) // 2)
        return QPointF(stage.mapTo(self.app, QPoint(x, 0)))

    def rehome(self):
        """раскладка окна сдвинула место схемы: неприближенная встаёт на него"""
        if self.aim() == 1:
            self.reset_zoom(animate=False)

    @staticmethod
    def clamped(pan, size, room):
        """схема больше окна - не уезжает краем внутрь, меньше - не уходит за край"""
        def axis(pan, size, room):
            return min(max(pan, room - size), 0.0) if size >= room else min(max(pan, 0.0), room - size)
        return QPointF(axis(pan.x(), size.width(), room.width()), axis(pan.y(), size.height(), room.height()))

    def clamp_pan(self):
        self.pan = self.clamped(self.pan, self.scheme * self.k, QSizeF(self.size()))

    def aim(self):
        """приближение, к которому идёт схема (во время анимации - конечное)"""
        return self.goal[0] if self.goal else self.k

    def zoom_to(self, k, at=None):
        """приблизить в k раз (1 - вся схема); at - логическая точка, которая остаётся на месте
        (по умолчанию середина схемы)"""
        k = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], k))
        k0, o0 = self.goal or (self.k, self.pan)
        if k == k0:
            return
        if k == ZOOM_STEPS[0]:
            self.reset_zoom()
            return
        at = at or o0 + QPointF(self.scheme.width(), self.scheme.height()) * (k0 / 2)
        self.move_to(k, self.clamped(at - (at - o0) * (k / k0), self.scheme * k, QSizeF(self.size())))

    def zoom_step(self, n, at=None):
        """на n ступенек ZOOM_STEPS ближе (n < 0 - дальше)"""
        i = min(range(len(ZOOM_STEPS)), key=lambda j: abs(ZOOM_STEPS[j] - self.aim()))
        self.zoom_to(ZOOM_STEPS[max(0, min(len(ZOOM_STEPS) - 1, i + n))], at)

    def reset_zoom(self, animate=True):
        self.move_to(1.0, self.home(), animate)

    def move_to(self, k, pan, animate=True):
        """плавно (animate) или сразу приблизить в k раз так, чтобы угол схемы был в pan"""
        self.anim.stop()
        self.tip = None
        if animate and self.isVisible():
            self.start, self.goal = (self.k, QPointF(self.pan)), (k, pan)
            self.anim.start()
        else:
            self.goal = None
            self.apply(k, pan)
        self.app.zoom_changed(animate)

    def step(self, t):
        """кадр анимации приближения: t от 0 до 1 (уже с замедлением к концу)"""
        if self.goal is None:
            return
        (k0, o0), (k1, o1) = self.start, self.goal
        self.apply(k0 + (k1 - k0) * t, o0 + (o1 - o0) * t)

    def finish(self):
        """анимация приближения дошла до конца или её прервали: схема сразу на конечном месте"""
        if self.goal is not None:
            goal, self.goal = self.goal, None
            self.anim.stop()
            self.apply(*goal)

    def apply(self, k, pan):
        self.k, self.pan = k, pan
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), color("bg"))             # фон схемы тот же: где она кончается, не видно
        d = self.dpr()
        if self.base is not None:
            ready = self.app.ready()
            p.save()
            p.translate(self.pan)
            p.scale(self.k, self.k)
            # готовая схема без приближения ложится на экран пиксель в пиксель: без сглаживания она чёткая
            # и кладётся простым копированием. Растянутую (прежнего масштаба или приближенную) - сглаживаем
            p.setRenderHint(QPainter.SmoothPixmapTransform, not (ready and self.k == 1))
            size = QSizeF(self.base.width() / d, self.base.height() / d) if ready else self.scheme
            p.drawImage(QRectF(QPointF(0, 0), size), self.base)
            if ready:
                for name in ("anim", "target", "hover", "reveal", "flash"):
                    item = self.layers[name]
                    if item is not None:
                        im, x, y = item
                        p.drawImage(QRectF(x / d, y / d, im.width() / d, im.height() / d), im)
            p.restore()
        if self.pin and self.app.ready():
            x, y = self.to_screen(*self.pin[:2])
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(color("ok"), px(2)))
            p.drawLine(QPointF(x, y - px(2)), QPointF(x, y - px(18)))     # указатель от подписи к органу
            self.bubble(p, self.bubble_rect(x, y - px(18), self.pin[2], 12, above=True), self.pin[2], 12, "ok",
                        above=True)
        if self.tip:
            self.bubble(p, self.tip_rect(self.tip), self.tip[2], 10, "border")
        if self.message:
            text, bottom = self.message
            p.setPen(color("muted"))
            p.setFont(font(9 if bottom else 12))
            r = QRectF(self.home(), self.scheme)         # надпись - посередине места схемы
            r = r.adjusted(0, 0, 0, -px(6)) if bottom else r
            p.drawText(r, (Qt.AlignBottom | Qt.AlignHCenter) if bottom else Qt.AlignCenter, text)

    def bubble_rect(self, x, y, text, size, above=False):
        """где плашка с текстом: левый верхний угол в (x, y) или (above) середина нижнего края там;
        не вылезает за край"""
        fm = QFontMetrics(font(size, bold=True), self)
        w, h = fm.horizontalAdvance(text) + px(12), fm.height() + px(6)
        if above:
            x, y = x - w / 2, y - h
        x = max(2, min(x, self.width() - w - 6))
        y = max(2, min(y, self.height() - h - 2))
        return QRectF(x, y, w, h)

    def tip_rect(self, tip):
        x, y, text = tip
        return self.bubble_rect(x + 14, y + 14, text, 10)

    def pin_rect(self, pin):
        """плашка подписи вместе с указателем от неё к органу"""
        x, y = self.to_screen(*pin[:2])
        return self.bubble_rect(x, y - px(18), pin[2], 12, above=True).united(QRectF(x - px(2), y - px(18), px(4),
                                                                                        px(18)))

    def bubble(self, p, r, text, size, edge, above=False):
        """плашка с текстом в прямоугольнике r (из bubble_rect)"""
        p.setFont(font(size, bold=True))
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(color(edge), max(1, px(2) if above else 1)))
        p.setBrush(color("tip_bg"))
        p.drawRoundedRect(r, px(4), px(4))
        p.setPen(color("tip_fg"))
        p.drawText(r, Qt.AlignCenter, text)

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120
        if steps:
            self.zoom_step(1 if steps > 0 else -1, e.position())
        e.accept()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.press is not None:
            start, pan, button = self.press
            if not self.dragging and (pos - start).manhattanLength() > px(DRAG_PX) and self.k > 1:
                self.dragging = True
                self.app.on_leave()
                self.setCursor(Qt.ClosedHandCursor)
            if self.dragging:
                self.pan = pan + (pos - start)
                self.clamp_pan()
                self.update()
                return
        self.app.on_move(*self.to_scheme(pos))

    def leaveEvent(self, _e):
        self.app.on_leave()

    def mousePressEvent(self, e):
        if e.button() in (Qt.BackButton, Qt.ForwardButton):
            e.ignore()                                   # кнопки мыши «назад/вперёд» - окну
            return
        self.app.setFocus()                              # стрелки и цифры - снова окну, а не строке поиска
        self.finish()                                    # двигаем уже с конечного места
        self.press, self.dragging = (e.position(), QPointF(self.pan), e.button()), False

    def mouseReleaseEvent(self, e):
        press, dragged = self.press, self.dragging
        self.press, self.dragging = None, False
        if dragged:
            self.setCursor(Qt.ArrowCursor)
            self.app.on_move(*self.to_scheme(e.position()))
            return
        if press is not None and e.button() == Qt.LeftButton:
            self.app.on_click(*self.to_scheme(e.position()))


class Stage(QWidget):
    """место под схему в раскладке окна, которое растягивается вместе с окном; схема - по центру сверху.
    Сама схема рисуется под всем окном (SchemeView), а это место пропускает мышь к ней"""

    def __init__(self, app, view):
        super().__init__()
        self.app, self.view = app, view
        self.hint = QSize(px(200), px(200))              # размер схемы для раскладки окна при запуске
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        # кнопки приближения - столбиком у правого края схемы, а когда интерфейс скрыт - у края окна
        self.zoom_buttons = {name: flat_button(text, command, size=11, padx=0, pady=2, parent=app)
                             for name, text, command in (("zoom_in", "+", lambda: view.zoom_step(1)),
                                                         ("zoom_out", "−", lambda: view.zoom_step(-1)),
                                                         ("zoom_reset", "⟲", view.reset_zoom))}
        for b in self.zoom_buttons.values():
            b.setFixedSize(px(30), px(30))

    def buttons_at(self, edge):
        """где кнопки приближения: у края схемы (edge=False) или окна"""
        app = self.app
        if edge:
            return QPoint(app.width() - px(38), px(8))
        right = self.mapTo(app, QPoint(int(min((self.width() + self.view.scheme.width()) / 2, self.width())), 0))
        return QPoint(right.x() - px(38), right.y() + px(8))

    def place(self, animate=False):
        """кнопки приближения - на своё место (плавно, если интерфейс уезжает или возвращается)"""
        to = self.buttons_at(self.app.ui_hidden)
        for i, b in enumerate(self.zoom_buttons.values()):
            b.raise_()
            end = to + QPoint(0, i * px(36))
            if animate and self.isVisible():
                slide(b, b.pos(), end)
            else:
                b.move(end)

    def sizeHint(self):                                  # раскладка окна при запуске - под размер схемы
        return self.hint

    def minimumSizeHint(self):
        return QSize(px(200), px(200))

    def resizeEvent(self, e):
        self.view.rehome()
        self.place()
        self.app.on_resize()

    def moveEvent(self, e):
        self.view.rehome()
        self.place()
