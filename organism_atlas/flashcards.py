"""Флеш-карточки в режиме «Изучать»: на лицевой стороне вопрос, на обороте ответ, дальше - «знал» или «не знал».
Без Qt.

Колоды (DECKS): organs - что делает орган и где он лежит, latin - латинские названия органов, костей и мышц,
facts - вопросы «Угадай по факту» (questions/*.json), diseases - какие органы поражает болезнь и что это такое.
Каждая карточка повторяется по той же системе Лейтнера, что и викторина (progress.py): её ключ в progress.json -
«flash_<колода>:<карточка>». Поэтому карточки колод organs и latin (их ключ - орган) идут и в карту знаний.
За один подход - SIZE карточек: сначала те, что пора повторить, затем новые, затем остальные."""

import random

from . import diseases, i18n, progress, questions
from .i18n import t
from .organs import for_body
from .quiz import latin_name, leaks, plain_name
from .structures import STRUCTURES

DECKS = ("organs", "latin", "facts", "diseases")
SIZE = 10                       # карточек за один подход


def mode(deck):
    """режим в progress.json: карточки колоды хранятся как «flash_<колода>:<карточка>»"""
    return "flash_" + deck


def _fact(item):
    key, _, idx = item.partition("#")
    return key, int(idx)


def items(deck, body):
    """ключи карточек колоды на схеме тела body (female / male)"""
    organs = for_body(body)
    if deck == "organs":
        return list(organs)
    if deck == "latin":
        return [k for k in [*organs, *STRUCTURES] if latin_name(k)]
    if deck == "facts":                         # вопрос, который называет сам орган, ответ выдал бы сразу
        return ["%s#%d" % (k, i) for k in organs for i in range(len(questions.for_organ(k)))
                if questions.has_answers(k, i) or not leaks(questions.text(k, i), k)]
    if deck == "diseases":
        return [d for d in diseases.KEYS if set(diseases.ORGANS_OF[d]) & set(organs)]
    raise ValueError(deck)


def card(deck, item, body):
    """что на карточке: {"title", "prompt"} - лицевая сторона, "answer" - оборот, "spot" - орган (кость, мышца),
    который подсветить на схеме, "spot_first" - подсветить сразу, а не вместе с ответом (иначе подсветка выдала бы
    ответ)"""
    if deck == "organs":
        answer = i18n.organ(item, "desc") + "\n\n" + i18n.organ(item, "location")
        return {"title": plain_name(item), "prompt": t("flash_q_organs"), "answer": answer, "spot": item,
                "spot_first": True}
    if deck == "latin":
        return {"title": plain_name(item), "prompt": t("flash_q_latin"), "answer": latin_name(item), "spot": item,
                "spot_first": True}
    if deck == "facts":
        key, idx = _fact(item)
        own = questions.has_answers(key, idx)
        return {"title": t("flash_q_question") if own else t("flash_q_facts"), "prompt": questions.text(key, idx),
                "answer": questions.answer_text(key, idx, 0) if own else i18n.name(key), "spot": key,
                "spot_first": False}
    if deck == "diseases":
        organs = [o for o in diseases.ORGANS_OF[item] if o in for_body(body)]
        answer = ", ".join(i18n.name(o) for o in organs) + ".\n\n" + diseases.text(item, "desc")
        return {"title": diseases.text(item, "name"), "prompt": t("flash_q_diseases"), "answer": answer,
                "spot": organs[0] if organs else None, "spot_first": False}
    raise ValueError(deck)


def due_count(deck, body, data=None, today=None):
    """сколько карточек колоды пора повторить"""
    return len(progress.due(mode(deck), items(deck, body), data, today))


class FlashSession:
    """один подход: карточки по очереди; shown - открыт ли оборот текущей карточки; knew - ответы «знал»"""

    def __init__(self, deck, keys, body):
        self.deck, self.keys, self.body = deck, list(keys), body
        self.i = 0
        self.shown = False
        self.knew = []                          # [True / False] по пройденным карточкам

    @property
    def finished(self):
        return self.i >= len(self.keys)

    @property
    def current(self):
        return None if self.finished else self.keys[self.i]

    def card(self):
        return card(self.deck, self.current, self.body)

    def reveal(self):
        self.shown = True

    def answer(self, ok, today=None):
        """«знал» (ok) или «не знал»: карточка переходит в следующую коробку или возвращается в первую"""
        if self.finished:
            return
        progress.mark(mode(self.deck), self.current, ok, today)
        self.knew.append(bool(ok))
        self.i += 1
        self.shown = False


def start(deck, body, data=None, size=SIZE, rng=random, today=None):
    """новый подход: сначала карточки, которые пора повторить, затем новые, затем остальные (по порядку - вперемешку)"""
    keys = items(deck, body)
    data = data or progress.load()
    due = progress.due(mode(deck), keys, data, today)
    seen = {k for k in keys if "%s:%s" % (mode(deck), k) in data["cards"]}
    new = [k for k in keys if k not in seen]
    rest = [k for k in keys if k in seen and k not in due]
    rng.shuffle(new)
    rng.shuffle(rest)
    pick = (due + new + rest)[:size]
    rng.shuffle(pick)
    return FlashSession(deck, pick, body)
