"""Заметки и закладки: свой текст под карточкой органа, кости или мышцы и отметка «★ в закладках». Без Qt.

Файл: notes.json рядом с settings.json; переменная окружения ORGANISM_ATLAS_NOTES задаёт другой путь (нужна тестам).
Испорченный файл не мешает: заметки и закладки просто начинаются заново.
Вид файла: {"notes": {ключ: текст}, "starred": [ключи в порядке добавления]}.
По закладкам можно сыграть викторину (набор вопросов «Закладки» на её карточке настройки)."""

import json
import os
from pathlib import Path

from . import settings

MAX_LEN = 4000                  # длиннее заметка не сохраняется: это заметка на полях, а не конспект


def path():
    custom = os.environ.get("ORGANISM_ATLAS_NOTES")
    return Path(custom) if custom else settings.path().with_name("notes.json")


_parsed = None                  # (байты файла, проверенные данные): тот же файл не разбирается заново


def load():
    """{"notes": {ключ: текст}, "starred": [ключи]} - проверенное содержимое файла (копия - её можно менять).
    Каждая карточка читает файл: разбирается он, только если байты другие"""
    global _parsed
    try:
        raw = path().read_bytes()
    except OSError:
        raw = None
    if _parsed is None or _parsed[0] != raw:
        _parsed = (raw, _parse(raw))
    data = _parsed[1]
    return {"notes": dict(data["notes"]), "starred": list(data["starred"])}


def _parse(raw):
    try:
        data = json.loads(raw.decode("utf-8")) if raw is not None else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    notes = {k: v for k, v in notes.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
    starred = data.get("starred") if isinstance(data.get("starred"), list) else []
    return {"notes": notes, "starred": list(dict.fromkeys(k for k in starred if isinstance(k, str)))}


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


def note(key, data=None):
    """заметка к карточке key ("" - нет)"""
    return (data or load())["notes"].get(key, "")


def set_note(key, text):
    """сохранить заметку; пустая - удаляется"""
    data = load()
    text = (text or "")[:MAX_LEN].rstrip()
    if text.strip():
        data["notes"][key] = text
    else:
        data["notes"].pop(key, None)
    save(data)


def starred(data=None):
    """ключи в закладках, в порядке добавления"""
    return list((data or load())["starred"])


def is_starred(key, data=None):
    return key in (data or load())["starred"]


def toggle_star(key):
    """добавить в закладки или убрать из них; возвращает, в закладках ли ключ теперь"""
    data = load()
    on = key not in data["starred"]
    if on:
        data["starred"].append(key)
    else:
        data["starred"].remove(key)
    save(data)
    return on
