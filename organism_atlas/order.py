"""«Расставь по порядку»: органы маршрута (путь пищи, кислорода, мочи...) нужно назвать по порядку - кнопками
или щелчками по схеме. Без Qt.

OrderSession похожа на quiz.QuizSession: тот же счёт (с первой попытки, ошибки, время), запись в историю
и повторение по Лейтнеру (карточка - маршрут), только «вопрос» - целый маршрут, а ответ - органы по очереди.
Маршрут - ROUTES; органы, которых нет на схеме тела, пропускаются. Названия маршрутов - route_<ключ>
в разделе ui файлов lang/*.json.
"""

import random
import time

from . import i18n
from .i18n import t
from .organs import for_body

# маршруты: органы по порядку. Только то, что действительно идёт друг за другом
ROUTES = {
    "food": ["esophagus", "stomach", "intestines", "rectum"],          # путь пищи
    "oxygen": ["trachea", "lungs", "heart", "aorta"],                 # кислород: вдох - лёгкие - сердце - тело
    "venous": ["vena_cava", "heart", "lungs"],                        # венозная кровь: от тела к лёгким
    "bile": ["liver", "gallbladder", "intestines"],                   # жёлчь: печень делает, пузырь копит, кишка
    "urine": ["kidneys", "bladder", "prostate"],                      # моча (у мужчин проходит сквозь простату)
    "stress": ["brain", "pituitary", "adrenals"],                     # гормоны стресса: гипоталамус - гипофиз
}
DISTRACTORS = {"easy": 0, "medium": 1, "hard": 2}                     # лишних органов среди кнопок


def steps(route, body):
    """органы маршрута, которые есть на схеме тела body"""
    have = set(for_body(body))
    return [k for k in ROUTES[route] if k in have]


def available(body):
    """маршруты, в которых на этой схеме хотя бы два органа (иначе расставлять нечего)"""
    return [r for r in ROUTES if len(steps(r, body)) >= 2]


def title(route):
    return t("route_" + route)


class OrderSession:
    """Одна игра: маршруты в случайном порядке, в каждом - органы по очереди.

    routes - какие маршруты (ключи ROUTES); count - сколько из них сыграть (None - все); body - схема тела;
    level - сколько лишних органов среди кнопок (DISTRACTORS); timer - секунд на маршрут (0 - без таймера)."""

    mode = "order"

    def __init__(self, routes, body="male", rng=random, level="medium", timer=0, clock=time.monotonic, count=None):
        self.rng, self.level, self.timer, self.clock, self.body = rng, level, timer, clock, body
        routes = [r for r in routes if len(steps(r, body)) >= 2]
        n = len(routes) if not count or count > len(routes) else count
        self.q = rng.sample(routes, n)
        self.pool = list(self.q)
        self.i = 0
        self.placed = []                             # органы текущего маршрута, уже названные по порядку
        self.errors = self.first_try = self.timeouts = 0
        self.planned = len(self.q)
        self.gave_up = False
        self.slipped = False
        self.missed = []                             # маршруты, на которых ошибались
        self.results = {}
        self.wrong = set()                           # ошибочно выбранные органы текущего маршрута
        self._options = {}
        self.deadline = None
        self.started, self.ended = clock(), None
        self.organ_count = None                      # «Марафон» - не про маршруты
        self.total_time = 0

    # --- как у QuizSession
    @property
    def total(self):
        return len(self.q)

    @property
    def finished(self):
        return self.i >= len(self.q)

    @property
    def current(self):
        return None if self.finished else self.q[self.i]

    @property
    def kind(self):
        return None if self.finished else "order"

    @property
    def elapsed(self):
        return (self.ended if self.ended is not None else self.clock()) - self.started

    @property
    def time_limit(self):
        return self.timer

    def route(self):
        """органы текущего маршрута по порядку"""
        return steps(self.current, self.body) if not self.finished else []

    def correct(self):
        """какой орган следующий"""
        r = self.route()
        return r[len(self.placed)] if len(self.placed) < len(r) else None

    def options(self):
        """кнопки: органы маршрута и лишние органы (по сложности) в случайном порядке; один список на маршрут"""
        if self.finished:
            return []
        if self.i not in self._options:
            r = self.route()
            others = [k for k in for_body(self.body) if k not in r]
            extra = self.rng.sample(others, min(DISTRACTORS[self.level], len(others)))
            opts = r + extra
            self.rng.shuffle(opts)
            self._options[self.i] = opts
        return self._options[self.i]

    def option_label(self, key):
        return i18n.name(key)

    def answer_text(self, _i):
        return None

    def step(self, key):
        """назвать следующий орган: right - верно, маршрут продолжается; done - верно, маршрут пройден;
        wrong - не тот орган (ошибка); None - игра закончена"""
        if self.finished:
            return None
        if key == self.correct():
            self.placed.append(key)
            if len(self.placed) < len(self.route()):
                return "right"
            if not self.slipped:
                self.first_try += 1
            self._next(not self.slipped)
            return "done"
        self.errors += 1
        self.wrong.add(key)
        if not self.slipped:
            self.slipped = True
            self.missed.append(self.current)
        return "wrong"

    def answer(self, key):
        """щелчок по органу на схеме - то же, что кнопка; True - маршрут пройден"""
        return self.step(key) == "done"

    def _next(self, ok):
        self.results[self.q[self.i]] = ok
        self.placed, self.wrong, self.slipped = [], set(), False
        self.deadline = None
        self.i += 1
        if self.finished:
            self.ended = self.clock()

    # --- таймер на маршрут
    def start_timer(self):
        if self.timer and not self.finished and self.deadline is None:
            self.deadline = self.clock() + self.timer

    def remaining(self):
        if self.deadline is None or self.finished:
            return None
        return max(0.0, self.deadline - self.clock())

    def time_up(self):
        rem = self.remaining()
        if rem is None or rem > 0:
            return None
        self.timeouts += 1
        return self._skip()

    def _skip(self):
        key = self.correct()
        if not self.slipped:
            self.errors += 1
            self.missed.append(self.current)
        self._next(False)
        return key

    def give_up(self):
        if self.finished:
            return None
        self.gave_up = True
        del self.q[self.i + 1:]
        return self._skip()

    @property
    def percent(self):
        return round(100 * self.first_try / self.total) if self.total else 0

    @property
    def verdict(self):
        from .quiz import QuizSession
        return QuizSession.verdict.fget(self)

