"""Чтение карточки вслух (кнопка «Прочитать вслух» и клавиша R): голосом системы через speech.py.

CardReader помнит, какую карточку читают, и пока читают, раз в 400 мс сверяет подпись кнопки
(«Остановить» → снова «Прочитать вслух», когда голос дочитал)."""

from .. import i18n, speech
from ..i18n import t
from .cards import card_text
from .quiz_controller import timer
from .widgets import alive

POLL_MS = 400


class CardReader:
    def __init__(self, app):
        self.app = app
        self.key = None                        # ключ карточки, которую сейчас читают вслух
        self.timer = timer(app, self.refresh)

    def action(self, key):
        """кнопка «Прочитать вслух» для карточки key или None, если читать нечем"""
        if not speech.available():
            return None
        return (t("card_read_stop") if self.key == key and speech.speaking() else t("card_read"),
                lambda: self.toggle(key))

    def toggle(self, key):
        """прочитать карточку вслух; если её уже читают - остановить"""
        if not speech.available():
            return
        if self.key == key and speech.speaking():
            speech.stop()
            self.key = None
        else:
            self.key = key if speech.speak(card_text(key), i18n.base()) else None
        self.refresh()

    def stop(self):
        """смена режима: чтение карточки - только в «Изучать»"""
        if self.key:
            speech.stop()
            self.key = None

    def refresh(self):
        """подпись кнопки чтения: пока читают - «Остановить», потом снова «Прочитать вслух»"""
        b = getattr(self.app.card, "read_button", None)
        if self.key and not speech.speaking():
            self.key = None
        if alive(b):
            b.setText(t("card_read_stop") if self.key else t("card_read"))
        if self.key:
            self.timer.start(POLL_MS)
