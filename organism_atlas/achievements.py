"""Серия дней и достижения по истории викторин (progress.json). Без Tk.

Серия - сколько дней подряд, по сегодня (или по вчера: сегодня ещё можно успеть), сыграна хотя бы одна игра.
Достижение - условие на историю игр и карточки повторения. Полученные не хранятся, а считаются заново
по progress.json, поэтому новое достижение в коде засчитается и за игры, сыгранные раньше
(история хранит последние progress.KEEP игр). Тексты: ach_<ключ> и ach_<ключ>_desc в lang/*.json.
"""

import datetime

from .quiz import MODES

ALL_ORGANS = 18             # «Все органы»: игра хотя бы из стольких вопросов (на мужской схеме органов 18)
SCHOLAR = 18                # «Знаток»: столько органов хоть раз отвечены с первой попытки
MEMORY = 10                 # «Долгая память»: столько карточек дошли до коробки 4 (повтор через 8 дней)


def _day(r):
    try:
        return datetime.date.fromisoformat(str(r.get("date", ""))[:10])
    except ValueError:
        return None


def play_days(data):
    """дни, в которые была хотя бы одна игра, по возрастанию"""
    return sorted({d for d in map(_day, data["results"]) if d is not None})


def streak(data, today=None):
    """текущая серия: дней подряд с игрой, заканчивая сегодня или вчера (0 - серия прервалась)"""
    today = today or datetime.date.today()
    days = set(play_days(data))
    d = today if today in days else today - datetime.timedelta(days=1)
    n = 0
    while d in days:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def best_streak(data):
    """самая длинная серия за всю сохранённую историю"""
    best = run = 0
    prev = None
    for d in play_days(data):
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        best, prev = max(best, run), d
    return best


def _flawless(r):
    return r.get("total", 0) > 0 and r.get("first_try") == r.get("total")


def _learned(data):
    """органы, на которые хоть раз ответили с первой попытки (в любом режиме)"""
    out = set()
    for key, c in data["cards"].items():
        if c.get("seen", 0) > c.get("wrong", 0):
            out.add(key.split(":", 1)[-1])
    return out


# (ключ, условие по данным progress.load()); порядок - порядок в списке достижений
ACHIEVEMENTS = (
    ("first", lambda d: bool(d["results"])),
    ("perfect", lambda d: any(_flawless(r) and r.get("total", 0) >= 5 for r in d["results"])),
    ("hard", lambda d: any(_flawless(r) and r.get("level") == "hard" and r.get("total", 0) >= 10
                           for r in d["results"])),
    ("speed", lambda d: any(_flawless(r) and r.get("timer") == 10 and r.get("total", 0) >= 10
                            for r in d["results"])),
    ("all_modes", lambda d: set(MODES) <= {r.get("mode") for r in d["results"]}),
    ("marathon", lambda d: any(r.get("total", 0) >= ALL_ORGANS for r in d["results"])),
    ("review", lambda d: any(r.get("set") == "due" for r in d["results"])),
    ("fixer", lambda d: any(r.get("set") == "missed" and _flawless(r) for r in d["results"])),
    ("streak3", lambda d: best_streak(d) >= 3),
    ("streak7", lambda d: best_streak(d) >= 7),
    ("scholar", lambda d: len(_learned(d)) >= SCHOLAR),
    ("memory", lambda d: sum(isinstance(c.get("box"), int) and c["box"] >= 4 for c in d["cards"].values()) >= MEMORY),
)
KEYS = tuple(k for k, _ in ACHIEVEMENTS)


def earned(data):
    """ключи полученных достижений, в порядке ACHIEVEMENTS"""
    return [k for k, ok in ACHIEVEMENTS if ok(data)]


def new_ones(before, after):
    """что получено между двумя состояниями progress (до игры и после)"""
    had = set(earned(before))
    return [k for k in earned(after) if k not in had]
