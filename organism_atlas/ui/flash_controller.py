"""Флеш-карточки в режиме «Изучать» (flashcards.py): колоды на стартовой карточке, затем карточка справа -
вопрос, «Показать ответ» и «Знал» / «Не знал». Орган ответа подсвечивается на схеме; в конце подхода - итог,
а новые достижения всплывают плашкой, как после викторины.

Щелчок по органу во время подхода открывает его карточку, а под ней - кнопка вернуться к флеш-карточкам."""

import traceback

from .. import flashcards, progress
from ..i18n import t
from ..organs import ORGANS
from ..structures import STRUCTURES
from .achievements import announce
from .cards import fill_flash


class FlashController:
    def __init__(self, app):
        self.app = app
        self.session = None                    # идущий подход (flashcards.FlashSession) или None
        self.before = None                     # progress.json в начале подхода: по нему ищутся новые достижения

    def reset(self):
        """смена режима или схемы тела: подход заканчивается без итогов (ответы уже сохранены)"""
        self.session = self.before = None

    def block(self):
        """раздел «Флеш-карточки» на стартовой карточке: колоды и сколько в каждой пора повторить"""
        try:
            data = progress.load()
        except Exception:                               # прогресс - не повод не показать карточку
            traceback.print_exc()
            data = {"results": [], "cards": {}}
        decks = []
        for deck in flashcards.DECKS:
            n = flashcards.due_count(deck, self.app.body, data)
            text = "▤  " + t("flash_deck_" + deck) + ("  ·  " + t("flash_due", n=n) if n else "")
            decks.append((text, lambda d=deck: self.start(d)))
        return t("flash_title"), t("flash_hint"), decks

    def start(self, deck):
        app = self.app
        app.tours.reset()                               # экскурсия и подход вместе не идут
        app.kb.key = None                               # Enter - ответ на карточку, а не выбранный стрелками орган
        try:
            self.before = progress.load()
        except Exception:
            traceback.print_exc()
            self.before = None
        self.session = flashcards.start(deck, app.body)
        self.show()

    def active(self):
        """подход идёт и не закончен"""
        return self.session is not None and not self.session.finished

    def show(self):
        """карточка справа и подсветка на схеме: орган видно сразу, если он не выдаёт ответ, иначе - с ответом"""
        s, app = self.session, self.app
        spot = None
        if s is not None and not s.finished:
            c = s.card()
            spot = c["spot"] if (s.shown or c["spot_first"]) else None
        app.set_spot(spot)
        app.set_card(self.card, fade=True)

    def card(self):
        s, app = self.session, self.app
        if s is None:                                   # подход закончили, пока карточка перерисовывалась
            app.empty_card()
            return
        title = t("flash_deck_" + s.deck)
        if s.finished:
            n, knew = len(s.knew), sum(s.knew)
            fill_flash(app.card, title, t("flash_done"), t("flash_done_text", knew=knew, n=n), None, "accent",
                       [(t("flash_again"), lambda: self.start(s.deck), "accent")], [(t("flash_exit"), self.end)])
            return
        c = s.card()
        spot = c["spot"]
        color = (ORGANS.get(spot) or STRUCTURES.get(spot) or {}).get("color", "accent")
        progress_text = t("flash_progress", title=title, n=s.i + 1, total=len(s.keys))
        if s.shown:
            buttons = [(t("flash_unknew"), lambda: self.answer(False), "card"),
                       (t("flash_knew"), lambda: self.answer(True), "accent")]
            hint = t("flash_keys_back")
        else:
            buttons = [(t("flash_show"), self.reveal, "accent")]
            hint = t("flash_keys_front")
        fill_flash(app.card, progress_text, c["title"], c["prompt"], c["answer"] if s.shown else None, color,
                   buttons, [(t("flash_exit"), self.end)], hint)

    def reveal(self):
        if not self.active() or self.session.shown:
            return
        self.session.reveal()
        self.show()

    def answer(self, ok):
        """«Знал» / «Не знал»: карточка уходит в свою коробку Лейтнера, дальше - следующая или итог"""
        s = self.session
        if not self.active() or not s.shown:
            return
        try:
            s.answer(ok)
        except Exception:                               # запись прогресса - не повод сорвать подход
            traceback.print_exc()
            s.knew.append(bool(ok))                     # ответ всё равно в счёт: итог - «знал N из M»
            s.i += 1
            s.shown = False
        if s.finished:
            self.finished()
        self.show()

    def finished(self):
        """подход окончен: новые достижения (например, «Долгая память») - плашкой и на кнопке «★»"""
        app = self.app
        try:
            announce(app, self.before, progress.load())
        except Exception:                               # история - не повод сорвать конец подхода
            traceback.print_exc()

    def resume(self):
        """вернуться к подходу после карточки органа"""
        if self.session is not None:
            self.show()

    def back_button(self):
        """кнопка под карточкой органа, пока идёт подход; None - подхода нет"""
        return (t("flash_resume"), self.resume) if self.active() else None

    def end(self):
        self.reset()
        self.app.set_spot(None)
        self.app.set_card(self.app.empty_card, fade=True)

    def on_key(self, keysym, char):
        """пробел или Enter открывают ответ; потом 1 или ← - «не знал», 2 или → - «знал». True - обработано"""
        if not self.active() or self.app.card_fn != self.card:
            return False
        if not self.session.shown:
            if char == " " or keysym in ("Return", "KP_Enter"):
                self.reveal()
                return True
            return False
        if char == "1" or keysym == "Left":
            self.answer(False)
            return True
        if char == "2" or keysym in ("Right", "Return", "KP_Enter"):
            self.answer(True)
            return True
        return False
