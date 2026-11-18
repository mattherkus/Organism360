"""Чтение карточки вслух (значок-динамик у заголовка карточки и клавиша R): голосом системы через speech.py.

CardReader помнит, какую карточку читают, и пока читают, раз в 400 мс сверяет значок кнопки
(«стоп» → снова динамик, когда голос дочитал)."""

from .. import i18n, speech
from .cards import card_text, read_icon
from .widgets import alive, timer

POLL_MS = 400


class CardReader:
    def __init__(self, app):
        self.app = app
        self.key = None                        # ключ карточки, которую сейчас читают вслух
        self.timer = timer(app, self.refresh)

    def action(self, key):
        """кнопка чтения вслух для карточки key: (читают ли её сейчас, функция) или None, если читать нечем"""
        if not speech.available():
            return None
        return self.key == key and speech.speaking(), lambda: self.toggle(key)

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
        """значок кнопки чтения: пока читают - «стоп», потом снова динамик"""
        b = getattr(self.app.card, "read_button", None)
        if self.key and not speech.speaking():
            self.key = None
        if alive(b):
            b.set_icon(*read_icon(bool(self.key)))
        if self.key:
            self.timer.start(POLL_MS)
