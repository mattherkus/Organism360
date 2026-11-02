"""История викторин и повторение по карточкам (упрощённая система Лейтнера).

Файл: progress.json рядом с settings.json; переменная окружения ORGANISM_ATLAS_PROGRESS задаёт другой путь
(нужна тестам). Испорченный файл не мешает: история просто начинается заново.

Карточка - пара «режим викторины + орган». Ответ с первой попытки переносит карточку в следующую
коробку, и её снова спросят через 1, 2, 4, 8 или 16 дней; ошибка (или вышедшее время) возвращает её
в первую коробку, и повторить её можно в тот же день.
"""

import datetime
import json
import os
from pathlib import Path

from . import settings
from .quiz import NO_CARDS

INTERVALS = (0, 1, 2, 4, 8, 16)      # через сколько дней повторять карточку из коробки 1..5
MAX_BOX = len(INTERVALS) - 1
KEEP = 200                           # сколько последних игр хранить в истории


def path():
    custom = os.environ.get("ORGANISM_ATLAS_PROGRESS")
    return Path(custom) if custom else settings.path().with_name("progress.json")


def load():
    """{"results": [игры, от старых к новым], "cards": {"режим:орган": карточка}[, "earned": {достижение: дата}]}"""
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    results = [r for r in data.get("results", []) if isinstance(r, dict)] \
        if isinstance(data.get("results"), list) else []
    cards = {k: c for k, c in data.get("cards", {}).items() if isinstance(c, dict)} \
        if isinstance(data.get("cards"), dict) else {}
    out = {"results": results, "cards": cards}
    if isinstance(data.get("earned"), dict):         # полученные достижения (achievements.remember)
        out["earned"] = {k: v for k, v in data["earned"].items() if isinstance(k, str)}
    return out


def save(data):
    """записать через временный файл; ошибки записи пропускаем - это не повод падать"""
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def _date(s):
    try:
        return datetime.date.fromisoformat(s)
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
        c = data["cards"].setdefault("%s:%s" % (session.mode, key), {"box": 0, "seen": 0, "wrong": 0})
        box = c.get("box", 0) if isinstance(c.get("box"), int) else 0
        c["box"] = min(box + 1, MAX_BOX) if ok else 1
        c["due"] = (today + datetime.timedelta(days=INTERVALS[c["box"]] if ok else 0)).isoformat()
        c["seen"] = c.get("seen", 0) + 1
        c["wrong"] = c.get("wrong", 0) + (0 if ok else 1)
        c["last"] = today.isoformat()
    from . import achievements                   # полученные достижения - запомнить, чтобы не пропали
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
        d = _date(c.get("due")) if c else None
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
