"""Логика викторины без привязки к интерфейсу: порядок вопросов, варианты ответа, таймер, вопросы по фактам."""

import random
import re
import time

from . import i18n, questions, settings
from .i18n import t

MODES = ("find", "name", "facts")                # найди орган / угадай название / угадай по факту
LEVELS = settings.CHOICES["quiz_level"]
TIMERS = settings.CHOICES["quiz_timer"]
OPTIONS = {"easy": 3, "medium": 4, "hard": 6}    # сколько вариантов ответа на кнопках


def _norm(s):
    return s.lower().replace("ё", "е")


def name_stems(key):
    """основы слов названия органа на всех языках: «желудок» -> «желуд», «лёгкие» -> «легк»"""
    stems = set()
    for n in i18n.all_names(key):
        for w in re.findall(r"\w+", _norm(n)):
            if len(w) >= 4:
                stems.add(w[:max(4, len(w) - 2)])
    return stems


def leaks(text, key):
    """выдаёт ли текст ответ: упоминает ли он сам орган"""
    s = _norm(text)
    return any(stem in s for stem in name_stems(key))


def _candidates(key, levels):
    """номера вопросов органа (questions/<орган>.json) нужных уровней, которые не выдают ответ.
    Вопрос со своими вариантами может называть орган: ответ на него - не орган."""
    return [i for i, q in enumerate(questions.for_organ(key))
            if q["level"] in levels and ("answer" in q or not leaks(questions.text(key, i), key))]


def fact_prompts(keys, level, rng=random):
    """{орган: номер вопроса} - что спросить про каждый орган; None - вопросов нет, спросим о функции"""
    out = {}
    for k in keys:
        cand = _candidates(k, questions.POOL[level]) or _candidates(k, questions.LEVELS)
        out[k] = rng.choice(cand) if cand else None
    return out


def prompt_text(key, idx):
    """текст вопроса по факту на текущем языке"""
    if idx is None or idx >= len(questions.for_organ(key)):
        return i18n.organ(key, "desc")
    return questions.text(key, idx)


class QuizSession:
    """Один проход викторины: вопросы в случайном порядке, подсчёт ошибок, таймер и результат.

    keys - органы, о которых спрашиваем; pool - из каких органов брать неверные варианты (по умолчанию keys);
    timer - секунд на вопрос (0 - без таймера); clock - источник времени (подменяется в тестах)."""

    def __init__(self, keys, rng=random, pool=None, mode="find", level="medium", timer=0, clock=time.monotonic):
        self.rng, self.mode, self.level, self.timer, self.clock = rng, mode, level, timer, clock
        self.q = rng.sample(list(keys), len(keys))   # порядок вопросов
        self.pool = list(pool) if pool is not None else list(self.q)
        self.i = 0                                   # номер текущего вопроса
        self.errors = 0                              # всего ошибок (включая вышедшее время)
        self.first_try = 0                           # верных с первой попытки
        self.timeouts = 0                            # сколько раз не успели
        self.slipped = False                         # на текущем вопросе уже была ошибка
        self.missed = []                             # ключи органов, на которых ошибались
        self.results = {}                            # {орган: True - с первой попытки, False - нет}
        self._options = {}                           # {номер вопроса: варианты ответа}
        self.prompts = fact_prompts(self.q, level, rng) if mode == "facts" else {}
        self.deadline = None                         # когда кончится время на текущий вопрос
        self.started, self.ended = clock(), None

    @property
    def total(self):
        return len(self.q)

    @property
    def finished(self):
        return self.i >= len(self.q)

    @property
    def current(self):
        """ключ органа, о котором текущий вопрос (None, когда вопросы закончились)"""
        return None if self.finished else self.q[self.i]

    @property
    def elapsed(self):
        """секунд с начала игры (после конца - длительность игры)"""
        return (self.ended if self.ended is not None else self.clock()) - self.started

    def _next(self, ok):
        self.results[self.q[self.i]] = ok
        self.slipped = False
        self.deadline = None
        self.i += 1
        if self.finished:
            self.ended = self.clock()

    def _miss(self):
        self.errors += 1
        self.slipped = True
        if self.q[self.i] not in self.missed:
            self.missed.append(self.q[self.i])

    def answer(self, key):
        """принять ответ; True - верно, False - ошибка, None - викторина уже закончена"""
        if self.finished:
            return None
        if key == self.correct():
            if not self.slipped:
                self.first_try += 1
            self._next(not self.slipped)
            return True
        self._miss()
        return False

    # --- таймер: интерфейс запускает его, когда вопрос появился на экране
    def start_timer(self):
        if self.timer and not self.finished:
            self.deadline = self.clock() + self.timer

    def remaining(self):
        """сколько секунд осталось на текущий вопрос; None - таймера нет или он не запущен"""
        if self.deadline is None or self.finished:
            return None
        return max(0.0, self.deadline - self.clock())

    def time_up(self):
        """если время на вопрос вышло: засчитать ошибку и перейти дальше; возвращает пропущенный орган"""
        rem = self.remaining()
        if rem is None or rem > 0:
            return None
        key = self.q[self.i]
        self.timeouts += 1
        if not self.slipped:                         # уже ошибся на этом вопросе - вторую ошибку не берём
            self._miss()
        self._next(False)
        return key

    # --- вопросы со своими вариантами ответа: варианты - «#0» (верный) и «#1», «#2»... (неверные)
    def custom(self):
        """у текущего вопроса свои варианты ответа (а не «какой это орган»)"""
        idx = self.prompts.get(self.current)
        return idx is not None and questions.has_answers(self.current, idx)

    def correct(self):
        """что считается верным ответом: ключ органа или «#0»"""
        return "#0" if self.custom() else self.current

    def option_label(self, opt):
        """текст на кнопке варианта на текущем языке"""
        if opt.startswith("#"):
            return questions.answer_text(self.current, self.prompts[self.current], int(opt[1:]))
        return i18n.name(opt)

    def options(self, n=None):
        """варианты ответа: верный и n-1 случайных неверных, в случайном порядке. Неверные - другие органы
        из pool или неверные ответы вопроса. n по умолчанию зависит от сложности. Для одного вопроса
        список не меняется."""
        if self.finished:
            return []
        if self.i not in self._options:
            n = n or OPTIONS[self.level]
            if self.custom():
                others = ["#%d" % j for j in range(1, questions.n_wrong(self.current, self.prompts[self.current]) + 1)]
            else:
                others = [k for k in self.pool if k != self.current]
            opts = self.rng.sample(others, min(n - 1, len(others))) + [self.correct()]
            self.rng.shuffle(opts)
            self._options[self.i] = opts
        return self._options[self.i]

    def prompt(self):
        """текст вопроса в режиме «по факту»"""
        return prompt_text(self.current, self.prompts[self.current]) if self.prompts and not self.finished else ""

    @property
    def percent(self):
        return round(100 * self.first_try / self.total) if self.total else 0

    @property
    def verdict(self):
        pct = self.percent
        if pct == 100:
            return t("verdict_perfect")
        if pct >= 70:
            return t("verdict_good")
        if pct >= 40:
            return t("verdict_ok")
        return t("verdict_bad")


def format_time(seconds):
    s = int(round(seconds))
    return "%d:%02d" % (s // 60, s % 60)
