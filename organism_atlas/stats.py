"""Статистика по истории игр и карточкам повторения (progress.json) и карта знаний. Без Qt.

Карточка повторения - пара «режим:ключ» (progress.py): сколько раз спросили (seen), сколько раз не с первой
попытки (wrong) и коробка Лейтнера (box). По ним считаются точность по органам и системам и уровень знания
органа для карты знаний на схеме.
"""


from . import achievements
from .quiz import MODES, NOT_ORGANS

LEARNED_BOX = 3              # орган выучен: в какой-то викторине дошёл до этой коробки (верно 3 раза подряд)
LEVELS = ("weak", "learning", "learned")     # слабо, учу, выучено; ещё не спрашивали - уровня нет
TREND = 30                   # сколько последних игр на графике
WEAK_MIN_SEEN = 2            # «слабое место» - орган, о котором спрашивали хотя бы столько раз


def _organ_cards(data):
    """{орган: [карточки]} - карточки викторин и флеш-карточек по органам (кости, мышцы и маршруты - не органы)"""
    from .organs import ORGANS
    out = {}
    for key, c in data["cards"].items():
        mode, _, organ = key.partition(":")
        if organ in ORGANS and mode not in NOT_ORGANS:
            out.setdefault(organ, []).append(c)
    return out


def _num(c, field):
    v = c.get(field, 0)
    return v if isinstance(v, int) and v >= 0 else 0


def organ_accuracy(data):
    """{орган: (сколько раз спросили, сколько из них с первой попытки)} по всем викторинам"""
    out = {}
    for organ, cards in _organ_cards(data).items():
        seen = sum(_num(c, "seen") for c in cards)
        wrong = sum(_num(c, "wrong") for c in cards)
        if seen:
            out[organ] = (seen, max(0, seen - wrong))
    return out


def mastery(data):
    """{орган: weak / learning / learned} для карты знаний; органов, о которых не спрашивали, нет"""
    out = {}
    for organ, cards in _organ_cards(data).items():
        seen = sum(_num(c, "seen") for c in cards)
        if not seen:
            continue
        best = max(_num(c, "box") for c in cards)
        wrong = sum(_num(c, "wrong") for c in cards)
        if best >= LEARNED_BOX:
            out[organ] = "learned"
        elif best <= 1 and wrong:
            out[organ] = "weak"
        else:
            out[organ] = "learning"
    return out


def summary(data, today=None):
    """сводка: игр, вопросов, с первой попытки, доля в %, минут в игре, серия дней сейчас и лучшая"""
    games = data["results"]
    total = sum(_num(r, "total") for r in games)
    right = sum(_num(r, "first_try") for r in games)
    return {"games": len(games), "questions": total, "right": right,
            "percent": round(100 * right / total) if total else None,
            "minutes": round(sum(_num(r, "seconds") for r in games) / 60),
            "streak": achievements.streak(data, today), "best_streak": achievements.best_streak(data)}


def by_mode(data):
    """[(режим, игр, вопросов, с первой попытки)] - режимы в порядке MODES, только сыгранные"""
    acc = {}
    for r in data["results"]:
        m = r.get("mode")
        if m in MODES:
            g, q, ok = acc.get(m, (0, 0, 0))
            acc[m] = (g + 1, q + _num(r, "total"), ok + _num(r, "first_try"))
    return [(m, *acc[m]) for m in MODES if m in acc and acc[m][1]]


def by_system(data, keys):
    """[(система, сколько раз спросили, с первой попытки)] по главной системе органов из keys, в порядке
    панели слоёв; системы, о которых не спрашивали, пропускаются"""
    from .organs import ORGANS, PANEL_SYSTEMS
    acc = organ_accuracy(data)
    out = []
    for system in PANEL_SYSTEMS:
        seen = right = 0
        for k in keys:
            if ORGANS[k]["systems"][0] == system and k in acc:
                seen += acc[k][0]
                right += acc[k][1]
        if seen:
            out.append((system, seen, right))
    return out


def weakest(data, keys, n=6):
    """до n органов из keys с самой низкой долей ответов с первой попытки (спрашивали хотя бы WEAK_MIN_SEEN раз,
    и ошибки были): [(орган, спросили, верно)]"""
    acc = organ_accuracy(data)
    cand = [(k, *acc[k]) for k in keys if k in acc and acc[k][0] >= WEAK_MIN_SEEN and acc[k][1] < acc[k][0]]
    cand.sort(key=lambda x: (x[2] / x[1], -x[1]))
    return cand[:n]


def trend(data, n=TREND):
    """последние n игр: [(дата ISO, режим, % с первой попытки)], от старых к новым"""
    out = []
    for r in data["results"][-n:]:
        total = _num(r, "total")
        if total:
            out.append((str(r.get("date", "")), r.get("mode"), round(100 * _num(r, "first_try") / total)))
    return out

