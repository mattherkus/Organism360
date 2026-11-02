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


def load():
    """{"notes": {ключ: текст}, "starred": [ключи]} - проверенное содержимое файла"""
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    raw = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    notes = {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
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
