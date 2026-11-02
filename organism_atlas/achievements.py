"""Серия дней и достижения по истории викторин (progress.json). Без Tk.

Серия - сколько дней подряд, по сегодня (или по вчера: сегодня ещё можно успеть), сыграна хотя бы одна игра.
Достижение - условие на историю игр и карточки повторения. Условия проверяются по progress.json, поэтому
новое достижение в коде засчитается и за игры, сыгранные раньше (история хранит последние progress.KEEP игр).
Полученное запоминается в progress.json (раздел earned, его пишет remember() при записи игры) и уже
не пропадает: ни когда старые игры уходят из истории, ни когда органов на схеме становится больше
и порог «Знатока» растёт. Тексты: ach_<ключ> и ach_<ключ>_desc в lang/*.json.
"""

import datetime

from .quiz import CLASSIC_MODES

LEGACY_ORGANS = 18          # столько органов было на мужской схеме, пока игры не записывали их число
MEMORY = 10                 # «Долгая память»: столько карточек дошли до коробки 4 (повтор через 8 дней)


def scholar_goal():
    """«Знаток»: столько органов хоть раз отвечены с первой попытки - все органы схемы с меньшим их числом
    (растёт сам, когда органов становится больше)"""
    from .organs import SEXES, for_body
    return min(len(for_body(s)) for s in SEXES)


def _all_organs(r):
    """игра про все органы схемы: вопросов не меньше, чем органов было на схеме (organs - с этой версии;
    None - игра не про органы, а про кости и мышцы)"""
    if "organs" in r and r["organs"] is None:
        return False
    organs = r.get("organs")
    return r.get("total", 0) >= (organs if isinstance(organs, int) and organs > 0 else LEGACY_ORGANS)


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
    from .organs import ORGANS
    out = set()
    for key, c in data["cards"].items():
        organ = key.split(":", 1)[-1]
        if c.get("seen", 0) > c.get("wrong", 0) and organ in ORGANS:          # кости и мышцы - не органы
            out.add(organ)
    return out


# (ключ, условие по данным progress.load()); порядок - порядок в списке достижений
ACHIEVEMENTS = (
    ("first", lambda d: bool(d["results"])),
    ("perfect", lambda d: any(_flawless(r) and r.get("total", 0) >= 5 for r in d["results"])),
    ("hard", lambda d: any(_flawless(r) and r.get("level") == "hard" and r.get("total", 0) >= 10
                           for r in d["results"])),
    ("speed", lambda d: any(_flawless(r) and r.get("timer") == 10 and r.get("total", 0) >= 10
                            for r in d["results"])),
    ("all_modes", lambda d: set(CLASSIC_MODES) <= {r.get("mode") for r in d["results"]}),
    ("marathon", lambda d: any(_all_organs(r) for r in d["results"])),
    ("review", lambda d: any(r.get("set") == "due" for r in d["results"])),
    ("fixer", lambda d: any(r.get("set") == "missed" and _flawless(r) for r in d["results"])),
    ("streak3", lambda d: best_streak(d) >= 3),
    ("streak7", lambda d: best_streak(d) >= 7),
    ("scholar", lambda d: len(_learned(d)) >= scholar_goal()),
    ("memory", lambda d: sum(isinstance(c.get("box"), int) and c["box"] >= 4 for c in d["cards"].values()) >= MEMORY),
)
KEYS = tuple(k for k, _ in ACHIEVEMENTS)


# условия прежних версий: по ним засчитывается полученное до того, как полученные стали запоминаться
LEGACY = (("scholar", lambda d: len(_learned(d)) >= LEGACY_ORGANS),)


def earned(data):
    """ключи полученных достижений, в порядке ACHIEVEMENTS: запомненные и те, чьё условие выполнено"""
    have = set(data.get("earned") or ())
    if "earned" not in data:                    # progress.json прежней версии: пороги тогда были ниже
        have |= {k for k, ok in LEGACY if ok(data)}
    return [k for k, ok in ACHIEVEMENTS if k in have or ok(data)]


def remember(data, today=None):
    """запомнить полученные достижения в data["earned"] ({ключ: дата получения}); возвращает новые"""
    today = (today or datetime.date.today()).isoformat()
    old = data.get("earned") if isinstance(data.get("earned"), dict) else {}
    got = earned(data)
    data["earned"] = {k: old.get(k, today) for k in got}
    return [k for k in got if k not in old]


def new_ones(before, after):
    """что получено между двумя состояниями progress (до игры и после)"""
    had = set(earned(before))
    return [k for k in earned(after) if k not in had]
