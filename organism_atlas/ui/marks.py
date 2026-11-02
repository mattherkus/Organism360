"""Подсветка на схеме: орган под курсором, орган вопроса (или поиска, шага экскурсии), вспышка «верно/ошибка»,
подсказка «верный орган здесь» после ошибки и органы-ошибки в итогах викторины.

Marks хранит готовые картинки подсветки (по органу и виду) и таймеры вспышки и подсказки; окно (App) даёт ему
схему (atlas, view), скрытые органы и орган, подсвеченный в «Изучать» (spot)."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter

from .. import i18n
from ..organs import ORGANS
from ..structures import STRUCTURES
from .quiz_controller import timer
from .widgets import qimage

FLASH_MS = 500                  # сколько видна вспышка «верно/ошибка»
REVEAL_MS = 500                 # сколько на лёгком уровне видна подсказка «верный орган здесь» после ошибки
LAYERS = ("target", "hover", "flash", "reveal", "missed")


class Marks:
    def __init__(self, app):
        self.app = app
        self.photos = {}                       # {(орган, вид подсветки): (QImage, (x, y))}
        self.missed = ()                       # органы-ошибки, отмеченные на схеме в итогах викторины
        self.flash_timer = timer(app, self.unflash, FLASH_MS)
        self.reveal_timer = timer(app, self.unreveal, REVEAL_MS)

    def drop(self):
        """забыть картинки подсветки (другой масштаб, другие скрытые органы)"""
        view = self.app.view
        for name in LAYERS:
            view.show_layer(name, None)
        view.set_pin(None)
        view.set_labels([])
        self.photos.clear()

    def photo(self, key, kind):
        if (key, kind) not in self.photos:
            im, pos = self.app.atlas.overlay(key, kind)
            self.photos[(key, kind)] = (qimage(im), pos)
        return self.photos[(key, kind)]

    def hover(self, key):
        """подсветка под курсором (None - снять)"""
        view = self.app.view
        view.show_layer("hover", None if key is None else self.photo(key, "hover"))
        view.setCursor(Qt.ArrowCursor if key is None else Qt.PointingHandCursor)

    def show_target(self):
        """подсветить орган текущего вопроса «Угадай название», а в «Изучать» - орган поиска или экскурсии;
        у вопроса другого типа подсветки нет"""
        app = self.app
        if not app.ready():
            return
        key = app.quiz.target() if app.mode != "study" else app.spot
        if key is None or key in app.hidden_now():
            app.view.show_layer("target", None)
            return
        app.view.show_layer("target", self.photo(key, "target"))

    def flash(self, key, kind):
        """на полсекунды закрасить орган зелёным (верно) или красным (ошибка)"""
        if not self.app.ready():
            return
        self.app.view.show_layer("flash", self.photo(key, kind))
        self.flash_timer.start()

    def unflash(self):
        self.flash_timer.stop()
        self.app.view.show_layer("flash", None)

    def reveal(self, key):
        """лёгкий уровень: после ошибки ненадолго показать на схеме, где верный орган, и подписать его"""
        app = self.app
        if not app.ready() or (key not in ORGANS and key not in STRUCTURES) or key in app.hidden_now():
            return
        app.view.show_layer("reveal", self.photo(key, "ok"))
        app.view.set_pin((*app.atlas.anchor(key), i18n.name(key)))
        self.reveal_timer.start()

    def unreveal(self):
        self.reveal_timer.stop()
        self.app.view.show_layer("reveal", None)
        self.app.view.set_pin(None)

    def show_missed(self, keys):
        """итоги викторины: органы (кости, мышцы), на которых ошибались, - красным на схеме и с подписью;
        пустой keys - снять отметки"""
        app, view = self.app, self.app.view
        self.missed = tuple(k for k in keys if k in ORGANS or k in STRUCTURES)
        if not (self.missed and app.ready()):
            view.show_layer("missed", None)
            view.set_labels([])
            return
        hidden = app.hidden_now()
        shown = [k for k in self.missed if k not in hidden]
        items = [self.photo(k, "bad") for k in shown]
        if not items:
            view.show_layer("missed", None)
            view.set_labels([])
            return
        box = QRect()
        for im, (x, y) in items:
            box = box.united(QRect(int(x), int(y), im.width(), im.height()))
        out = QImage(box.size(), QImage.Format_ARGB32_Premultiplied)
        out.fill(Qt.transparent)
        p = QPainter(out)
        for im, (x, y) in items:
            p.drawImage(int(x) - box.x(), int(y) - box.y(), im)
        p.end()
        view.show_layer("missed", (out, (box.x(), box.y())))
        view.set_labels([(*app.atlas.center(k), i18n.name(k)) for k in shown])
