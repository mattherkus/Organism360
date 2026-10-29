"""Настройки пользователя, которые переживают перезапуск: язык, тема, качество 3D, масштаб интерфейса,
схема тела (женская или мужская), анимация схемы, вид, сложность, таймер и длина викторины,
развёрнут ли раздел «Слои».

Файл: %APPDATA%/organism_atlas/settings.json (на других системах ~/.config/organism_atlas/settings.json);
переменная окружения ORGANISM_ATLAS_SETTINGS задаёт другой путь (нужна тестам).
Испорченный или недоступный файл не мешает запуску: настройки просто берутся по умолчанию.
"""

import json
import os
from pathlib import Path

# допустимые значения и значения по умолчанию; чужое или испорченное значение заменяется умолчанием
CHOICES = {
    "theme": ("dark", "light", "contrast"),
    "quality": ("low", "medium", "high"),        # качество 3D-рендера
    "ui_scale": (0.9, 1.0, 1.1, 1.25, 1.5),      # множитель к масштабу Windows; действует после перезапуска
    "quiz_level": ("easy", "medium", "hard"),     # сложность викторины
    "quiz_timer": (0, 20, 10),                   # секунд на вопрос; 0 - без таймера
    "quiz_length": (5, 10, 15, 0),               # вопросов в игре; 0 - про все органы (их 18-19)
    "body": ("female", "male"),                  # схема тела: органы малого таза (organs.SEXES)
    "animation": ("on", "off"),                  # сердце бьётся, лёгкие дышат
    "quiz_mode": ("find", "name", "facts", "mix"),   # вид викторины, который открывает кнопка «Викторина»
    "layers_panel": ("open", "closed"),          # раздел «Слои» в панели слева развёрнут или свёрнут
}
DEFAULTS = {"theme": "dark", "quality": "medium", "ui_scale": 1.0, "quiz_level": "medium", "quiz_timer": 0,
            "quiz_length": 10, "body": "male", "animation": "on",
            "quiz_mode": "find", "layers_panel": "open"}


def path():
    custom = os.environ.get("ORGANISM_ATLAS_SETTINGS")
    if custom:
        return Path(custom)
    root = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(root) / "organism_atlas" / "settings.json"


def load():
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(**values):
    """дописать значения к сохранённым; ошибки записи молча пропускаем - это не повод падать"""
    data = {**load(), **values}
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")           # через временный файл: не оставим полузаписанный
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def get(saved, key):
    """значение настройки key из словаря load(), проверенное по CHOICES"""
    v = saved.get(key)
    return v if v in CHOICES[key] and not isinstance(v, bool) else DEFAULTS[key]
