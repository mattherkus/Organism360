"""Заметки и закладки в карточках (notes.py): поле «Моя заметка» под карточкой органа, кости или мышцы, кнопка-звезда
закладки у заголовка и раздел «Закладки» на стартовой карточке с викториной по ним.

Заметка сохраняется сама - через SAVE_MS после последней правки (и при закрытии окна), а не на каждую букву."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QPlainTextEdit

from .. import i18n, notes
from ..i18n import t
from ..organs import ORGANS
from ..structures import STRUCTURES
from ..theme import C
from .scaling import px
from .widgets import alive, color, font

SAVE_MS = 600
LINES = 3                       # высота поля заметки в строках (длиннее - листается)


class NoteBox(QPlainTextEdit):
    """поле заметки в цветах темы с подсказкой внутри, пока оно пустое; on_edit(текст) - при каждой правке.
    Esc уводит фокус из поля обратно к окну (а не закрывает панель)"""

    def __init__(self, text, placeholder, on_edit):
        super().__init__(text)
        self.setPlaceholderText(placeholder)
        self.setFont(font(10))
        self.setTabChangesFocus(True)
        self.setFixedHeight(self.fontMetrics().lineSpacing() * LINES + px(16))
        self.textChanged.connect(lambda: on_edit(self.toPlainText()))
        self.setStyleSheet("QPlainTextEdit {background: %s; color: %s; border: %dpx solid %s; border-radius: %dpx;"
                           " padding: %dpx; selection-background-color: %s; selection-color: %s}"
                           " QPlainTextEdit:focus {border-color: %s}"
                           % (C["bg"], C["text"], max(1, px(1)), C["border"], px(6), px(4), C["accent"],
                              C["on_accent"], C["accent"]))
        pal = self.palette()
        pal.setColor(QPalette.PlaceholderText, color("muted"))
        self.setPalette(pal)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.clearFocus()
            self.window().setFocus()
            e.accept()
            return
        super().keyPressEvent(e)


class CardNotes:
    def __init__(self, app):
        self.app = app
        self.pending = None                    # (ключ, текст) - правка, которая ещё не записана в notes.json
        self.timer = QTimer(app)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.flush)

    def block(self, key):
        """для карточки key: (в закладках ли, переключить закладку, текст заметки, при правке)"""
        data = notes.load()
        text = self.pending[1] if self.pending and self.pending[0] == key else notes.note(key, data)
        return notes.is_starred(key, data), lambda: self.toggle(key), text, lambda s: self.edit(key, s)

    def edit(self, key, text):
        if self.pending and self.pending[0] != key:
            self.flush()
        self.pending = (key, text)
        self.timer.start(SAVE_MS)

    def flush(self):
        """записать отложенную правку заметки"""
        self.timer.stop()
        if self.pending:
            key, text = self.pending
            self.pending = None
            notes.set_note(key, text)

    def toggle(self, key):
        """звезда-контур «В закладки» / залитая «Убрать из закладок»: значок меняется на месте,
        карточка не перерисовывается"""
        on = notes.toggle_star(key)
        b = getattr(self.app.card, "star_button", None)
        if alive(b):
            b.set_icon(*star_icon(on))

    def starred(self):
        """закладки, которые есть на схеме (органы другого пола - нет): органы и кости с мышцами"""
        have = set(self.app.organs()) | set(STRUCTURES)
        return [k for k in notes.starred() if k in have]

    def home_block(self):
        """раздел «Закладки» на стартовой карточке: (заголовок, [(название, открыть карточку)], кнопка викторины)
        или None, если закладок нет"""
        keys = self.starred()
        if not keys:
            return None
        links = [("★  " + i18n.name(k), lambda k=k: self.app.open_link(k)) for k in keys]
        return t("home_starred"), links, (t("home_starred_quiz"), self.quiz)

    def quiz(self):
        """викторина по закладкам: органы - «Вперемешку», а если в закладках только кости и мышцы - «Кости и мышцы»"""
        keys = self.starred()
        mode = "mix" if any(k in ORGANS for k in keys) else "body"
        self.app.quiz.cfg["topic"] = None               # до смены режима: по теме «Кости и мышцы» видны слои
        self.app.quiz.cfg["set"] = "starred"
        self.app.set_mode(mode)
        self.app.quiz.start("starred")


def star_icon(on):
    """(значок, подсказка) кнопки закладки"""
    return ("star_on", t("card_star_on")) if on else ("star", t("card_star_off"))
