"""Интерфейс уезжает к краям окна, когда схему сильно приблизили (scheme_view.HIDE_FROM): заголовок - вверх,
панель слоёв - влево, карточка - вправо; при возврате схемы - приезжает обратно.

Пока виджет едет, вместо него едет его картинка («призрак»): так выезд плавный и не перестраивает раскладку."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap, QRegion
from PySide6.QtWidgets import QLabel, QWidget

from .scheme_view import slide
from .widgets import alive


class UiSlide:
    def __init__(self, app):
        self.app = app
        self.hidden = False                    # схема приближена сильно: заголовок, слои и карточка уехали
        self.ghosts = {}                       # {виджет: его картинка, которая сейчас уезжает или возвращается}

    def parts(self):
        """что уезжает: (виджет, виден ли он, когда интерфейс на месте, куда уезжает)"""
        app = self.app
        return ((app.header, True, QPoint(0, -1)), (app.panel, app.mode == "study", QPoint(-1, 0)),
                (app.card_area, True, QPoint(1, 0)))

    def set_hidden(self, hide, animate=True):
        """увезти интерфейс за края окна (hide) или вернуть; без animate - сразу"""
        if hide == self.hidden:
            return
        app = self.app
        self.hidden = hide
        animate = animate and app.isVisible()
        for w, shown, d in self.parts():
            if not shown:
                continue
            if not animate:
                w.setVisible(not hide)
                continue
            at = w.mapTo(app, QPoint(0, 0))
            away = QPoint(-w.width() if d.x() < 0 else app.width() if d.x() > 0 else at.x(),
                          -w.height() if d.y() < 0 else at.y())
            g, pos = self.ghost(w)
            w.hide()                                     # пока едет - вместо виджета его картинка
            slide(g, pos or (at if hide else away), away if hide else at, lambda g=g, w=w: self.landed(g, w))
        app.stage.place(animate)

    def ghost(self, w):
        """картинка виджета для выезда; если прошлая ещё едет - новая начинает с её места"""
        old = self.ghosts.pop(w, None)
        pos = None
        if old is not None:
            pos = old.pos()
            if alive(old._slide):
                old._slide.stop()
            old.deleteLater()
        g = QLabel(self.app)
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
        if not self.hidden:
            self.app.show_panel() if w is self.app.panel else w.show()
