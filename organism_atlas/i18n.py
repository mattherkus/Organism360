"""Тексты интерфейса и карточек органов на разных языках.

Тексты лежат в lang/<код>.json, по файлу на язык; новый файл сразу появляется в переключателе.
Файл может быть неполным (как la.json, где только латинские названия органов): чего нет в нём,
берётся из языка, выбранного перед ним, а затем из русского (ru.json должен быть полным).
"""

import datetime
import json
from pathlib import Path

LANG_DIR = Path(__file__).with_name("lang")
BASE = "ru"                         # полный язык, на который всё откатывается в конце
PREFERRED = ("ru", "en", "la")      # порядок кнопок; остальные языки идут следом по алфавиту

_cache = {}
_current, _previous = BASE, BASE


def _load(code):
    if code not in _cache:
        path = LANG_DIR / (code + ".json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError("Ошибка в файле %s, строка %d, столбец %d: %s"
                             % (path.name, e.lineno, e.colno, e.msg)) from None
        data.setdefault("ui", {})
        data.setdefault("organs", {})
        _cache[code] = data
    return _cache[code]


def load_all():
    """прочитать все файлы сразу, чтобы ошибка в любом из них всплыла при запуске"""
    for code in available():
        _load(code)


def available():
    """коды языков в порядке кнопок"""
    codes = [p.stem for p in LANG_DIR.glob("*.json")]
    return sorted(codes, key=lambda c: (PREFERRED.index(c) if c in PREFERRED else len(PREFERRED), c))


def short_name(code):
    return _load(code).get("short", code.upper())


def language_name(code):
    return _load(code).get("language", code)


def current():
    return _current


def previous():
    return _previous


def set_lang(code):
    global _current, _previous
    _load(code)
    if code != _current:
        _previous, _current = _current, code


def restore(code, prev=None):
    """вернуть язык прошлого запуска; prev нужен латыни, чтобы остальной текст был на том же языке,
    что и тогда. Языки, файлов которых уже нет, пропускаются."""
    global _current, _previous
    codes = available()
    if code not in codes:
        return
    _previous = prev if prev in codes else BASE
    _current = code


def _chain(skip_current=False):
    out = []
    for c in (_current, _previous, BASE):
        if c not in out:
            out.append(c)
    return out[1:] if skip_current else out


def chain():
    """языки, из которых берётся текст: текущий, предыдущий, русский"""
    return _chain()


def t(key, **kw):
    """строка интерфейса; {имя} в тексте подставляется из kw"""
    for code in _chain():
        s = _load(code)["ui"].get(key)
        if s:
            return s.format(**kw) if kw else s
    return key                                    # видно на экране, какого ключа не хватает


def organ(key, field, skip_current=False):
    """поле карточки органа: name, desc, location, facts, diseases, daily"""
    for code in _chain(skip_current):
        v = _load(code)["organs"].get(key, {}).get(field)
        if v:
            return v
    return [] if field in ("facts", "diseases", "daily") else key


def name(key):
    return organ(key, "name")


def organ_in(code, key, field):
    """поле карточки органа на языке code как есть, без отката на другие языки ("" - поля нет)"""
    return _load(code)["organs"].get(key, {}).get(field) or ""


def all_names(key):
    """название органа на всех языках (чтобы факт не выдавал ответ ни на одном из них)"""
    out = []
    for code in available():
        n = _load(code)["organs"].get(key, {}).get("name")
        if n and n not in out:
            out.append(n)
    return out


def tour(name, field):
    """поле экскурсии name из раздела tours: title, intro (строки) или steps ({орган: рассказ}).
    У steps каждый орган откатывается на другой язык отдельно"""
    if field == "steps":
        out = {}
        for code in reversed(_chain()):
            out.update({k: v for k, v in _load(code).get("tours", {}).get(name, {}).get("steps", {}).items() if v})
        return out
    for code in _chain():
        v = _load(code).get("tours", {}).get(name, {}).get(field)
        if v:
            return v
    return ""


def part(organ_key, group):
    """название части анатомической 3D-модели органа (группы сетки) из раздела parts; нет - None"""
    for code in _chain():
        v = _load(code).get("parts", {}).get(organ_key, {}).get(group)
        if v:
            return v
    return None


def subtitle(key):
    """подпись под названием: латинское название, а в латинском режиме - обычное"""
    if _current == "la":
        return organ(key, "name", skip_current=True)
    return _load("la")["organs"].get(key, {}).get("name", "") if "la" in available() else ""


def fact_of_day(key, order, day=None):
    """«интересный факт дня»: меняется раз в сутки; order - номер органа в списке, чтобы у разных
    органов в один день попадались факты из разных позиций пула"""
    pool = organ(key, "daily")
    if not pool:
        return ""
    day = day or datetime.date.today()
    return pool[(day.toordinal() + order) % len(pool)]
