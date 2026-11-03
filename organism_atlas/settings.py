"""Настройки пользователя, которые переживают перезапуск: язык, тема, качество 3D, масштаб интерфейса,
схема тела (женская или мужская), анимация схемы, вид, сложность, таймер и длина викторины,
развёрнут ли раздел «Слои».

Файл: %APPDATA%/organism_atlas/settings.json (на других системах ~/.config/organism_atlas/settings.json);
переменная окружения ORGANISM_ATLAS_SETTINGS задаёт другой путь (нужна тестам).
Испорченный или недоступный файл не мешает запуску: настройки просто берутся по умолчанию.
"""

import json
import os
import threading
from pathlib import Path

_lock = threading.Lock()

# допустимые значения и значения по умолчанию; чужое или испорченное значение заменяется умолчанием
CHOICES = {
    "theme": ("paper", "black", "system"),     # светлая, тёмная, как в системе (theme.SYSTEM)
    "quality": ("low", "medium", "high"),        # качество 3D-рендера
    "ui_scale": (0.9, 1.0, 1.1, 1.25, 1.5),      # множитель к масштабу Windows; действует после перезапуска
    "quiz_level": ("easy", "medium", "hard"),     # сложность викторины
    "quiz_timer": (0, 20, 10),                   # секунд на вопрос; 0 - без таймера
    "quiz_length": (5, 10, 15, 0),               # вопросов в игре; 0 - про все органы схемы
    "body": ("female", "male"),                  # схема тела: органы малого таза (organs.SEXES)
    "animation": ("on", "off"),                  # сердце бьётся, лёгкие дышат
    # вид викторины, который открывает кнопка «Викторина» (quiz.MODES)
    "quiz_mode": ("find", "name", "facts", "mix", "model", "body", "order", "exam", "daily"),
    "layers_panel": ("open", "closed"),          # раздел «Слои» в панели слева развёрнут или свёрнут
    "updates": ("on", "off"),                    # раз в день спрашивать GitHub о новой версии (updates.py)
    "onboarding": ("show", "done"),              # подсказки при первом запуске (ui/onboarding.py): ещё не видели
}
DEFAULTS = {"theme": "paper", "quality": "medium", "ui_scale": 1.0, "quiz_level": "medium", "quiz_timer": 0,
            "quiz_length": 10, "body": "male", "animation": "on",
            "quiz_mode": "find", "layers_panel": "open", "updates": "on", "onboarding": "show"}


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
    """дописать значения к сохранённым; ошибки записи молча пропускаем - это не повод падать.
    Пишут и окно, и фоновый поток (проверка обновлений): прочитать-дописать-записать - под замком, иначе
    одна запись затёрла бы другую, а общий временный файл перемешал бы их"""
    with _lock:
        data = {**load(), **values}
        p = path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")       # через временный файл: не оставим полузаписанный
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, p)
        except OSError:
            pass


# темы, которых больше нет, - к ближайшей оставшейся
_RENAMED = {"theme": {"light": "paper", "dark": "black", "contrast": "black"}}


def get(saved, key):
    """значение настройки key из словаря load(), проверенное по CHOICES"""
    v = saved.get(key)
    if isinstance(v, str):
        v = _RENAMED.get(key, {}).get(v, v)
    return v if v in CHOICES[key] and not isinstance(v, bool) else DEFAULTS[key]
