"""История викторин и повторение по карточкам (упрощённая система Лейтнера).

Файл: progress.json рядом с settings.json; переменная окружения ORGANISM_ATLAS_PROGRESS задаёт другой путь
(нужна тестам). Испорченный файл не мешает: история начинается заново, а сам файл сохраняется в progress.json.bad.

Карточка - пара «режим викторины + орган». Ответ с первой попытки переносит карточку в следующую
коробку, и её снова спросят через 1, 2, 4, 8 или 16 дней; ошибка (или вышедшее время) возвращает её
в первую коробку, и повторить её можно в тот же день.
"""

import datetime
import os
from pathlib import Path

from . import jsonstore, settings
from .quiz import NO_CARDS

INTERVALS = (0, 1, 2, 4, 8, 16)      # через сколько дней повторять карточку из коробки 1..5
MAX_BOX = len(INTERVALS) - 1
KEEP = 200                           # сколько последних игр хранить в истории


def path():
    custom = os.environ.get("ORGANISM_ATLAS_PROGRESS")
    return Path(custom) if custom else settings.path().with_name("progress.json")


COUNTS = ("box", "seen", "wrong", "total", "first_try", "errors", "timeouts", "seconds")   # целые >= 0
TEXTS = ("due", "last", "date", "mode", "level", "set")                                   # строки


def _clean(item):
    """запись игры или карточку - с полями нужного типа: поле не того типа (файл правили руками) отбрасывается,
    чтобы счёт, сортировка и статистика не падали на нём. organs - число или None, missed - список ключей"""
    out = {}
    for k, v in item.items():
        if k in COUNTS:
            ok = isinstance(v, int) and not isinstance(v, bool) and v >= 0
        elif k in TEXTS:
            ok = isinstance(v, str)
        elif k == "organs":
            ok = v is None or isinstance(v, int) and not isinstance(v, bool)
        elif k == "missed":
            ok = isinstance(v, list)
            v = [x for x in v if isinstance(x, str)] if ok else v
        else:
            ok = True
        if ok:
            out[k] = v
    return out




def load():
    """{"results": [игры, от старых к новым], "cards": {"режим:орган": карточка}[, "earned": {достижение: дата}]}.
    Карточки окна читают историю на каждый щелчок: файл читается всегда (его могли поменять), а разбирается,
    только если байты другие. Возвращается копия - её можно менять"""
    data = _store.load(path())
    out = {"results": [dict(r, missed=list(r["missed"])) if "missed" in r else dict(r) for r in data["results"]],
           "cards": {k: dict(c) for k, c in data["cards"].items()}}
    if "earned" in data:
        out["earned"] = dict(data["earned"])
    return out


def _parse(raw, p=None):
    """байты файла (None - файла нет) -> проверенные данные; испорченный файл - пустая история"""
    data = jsonstore.decode(raw, p)
    results = [_clean(r) for r in data.get("results", []) if isinstance(r, dict)] \
        if isinstance(data.get("results"), list) else []
    cards = {k: _clean(c) for k, c in data.get("cards", {}).items() if isinstance(c, dict)} \
        if isinstance(data.get("cards"), dict) else {}
    out = {"results": results, "cards": cards}
    if isinstance(data.get("earned"), dict):         # полученные достижения (achievements.remember)
        out["earned"] = {k: v for k, v in data["earned"].items() if isinstance(k, str)}
    return out


def save(data):
    """записать атомарно (jsonstore.write); ошибки записи пропускаем - это не повод падать"""
    jsonstore.write(path(), data)


_store = jsonstore.Cached(_parse)       # тот же файл не разбирается заново


def iso_day(s):
    """'2026-10-25' или '2026-10-25T14:03' -> datetime.date; не строка или не дата - None"""
    try:
        return datetime.date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        return None


def record(session, question_set="all", today=None, now=None):
    """сохранить законченную игру (QuizSession) в историю и обновить карточки. Возвращает данные."""
    today = today or datetime.date.today()
    now = now or datetime.datetime.now()
    data = load()
    data["results"].append({
        "date": now.isoformat(timespec="minutes"), "mode": session.mode, "level": session.level,
        "timer": session.timer, "set": question_set, "total": session.total, "first_try": session.first_try,
        "errors": session.errors, "timeouts": session.timeouts, "missed": list(session.missed),
        "seconds": round(session.elapsed),
        "organs": session.organ_count,               # для «Марафона»: сколько органов было на схеме
    })
    data["results"] = data["results"][-KEEP:]
    for key, ok in (session.results.items() if session.mode not in NO_CARDS else ()):   # экзамен, испытание дня - без карточек
        _bump(data["cards"], "%s:%s" % (session.mode, key), ok, today)
    from . import achievements                   # полученные достижения - запомнить, чтобы не пропали
    achievements.remember(data, today)
    save(data)
    return data


def _bump(cards, card_key, ok, today):
    """ответ на карточку: верный переносит её в следующую коробку, ошибка возвращает в первую"""
    c = cards.setdefault(card_key, {"box": 0, "seen": 0, "wrong": 0})
    box = c.get("box", 0) if isinstance(c.get("box"), int) else 0
    c["box"] = min(box + 1, MAX_BOX) if ok else 1
    c["due"] = (today + datetime.timedelta(days=INTERVALS[c["box"]] if ok else 0)).isoformat()
    c["seen"] = c.get("seen", 0) + 1
    c["wrong"] = c.get("wrong", 0) + (0 if ok else 1)
    c["last"] = today.isoformat()


def mark(mode, key, ok, today=None):
    """ответ на одну карточку вне игры (флеш-карточки, flashcards.py): «знал» - ok. Сохраняется сразу,
    чтобы прерванный подход не пропал. Возвращает данные"""
    today = today or datetime.date.today()
    data = load()
    _bump(data["cards"], "%s:%s" % (mode, key), ok, today)
    from . import achievements
    achievements.remember(data, today)
    save(data)
    return data


def due(mode, keys, data=None, today=None):
    """органы режима, которые пора повторить (в порядке ключей keys): сначала просроченные сильнее"""
    today = today or datetime.date.today()
    cards = (data or load())["cards"]
    out = []
    for i, k in enumerate(keys):
        c = cards.get("%s:%s" % (mode, k))
        d = iso_day(c.get("due")) if c else None
        if d is not None and d <= today:
            out.append((d, c.get("box", 0), i, k))
    return [k for *_, k in sorted(out)]


def last_missed(mode, keys, data=None):
    """ошибки последней сыгранной игры этого режима (только органы, которые ещё есть в keys)"""
    for r in reversed((data or load())["results"]):
        if r.get("mode") == mode:
            return [k for k in r.get("missed", []) if k in keys]
    return []


def today_results(mode, data=None, today=None):
    """игры режима, сыгранные сегодня, первые сверху (для «Испытания дня»)"""
    today = (today or datetime.date.today()).isoformat()
    return [r for r in (data or load())["results"] if r.get("mode") == mode and str(r.get("date", ""))[:10] == today]


def recent(mode, n=5, data=None):
    """последние n игр режима, новые сверху"""
    return [r for r in reversed((data or load())["results"]) if r.get("mode") == mode][:n]
