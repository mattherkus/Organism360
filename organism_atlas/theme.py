"""Темы оформления интерфейса: светлая (как страница анатомического атласа), тёмная (тот же атлас в чёрных
тонах) и «как в системе» - светлая или тёмная по настройке Windows (ui/app.py следит, когда её меняют).

Виджеты получают цвета не числами, а ролями (bg, card, text, ...): кнопки и карточки берут цвет роли
в момент рисования, а надписи запоминают свою роль (ui/widgets.py: set_fg), поэтому ui.widgets.retheme()
перекрашивает всё окно на лету.
Фон схемы тела (scene_bg, scene_hi) и кадров 3D (view_bg, view_hi) тоже из темы. В обеих темах схема
лежит прямо на странице: её фон - фон окна.
"""

from . import config

DEFAULT = "paper"
SYSTEM = "system"                  # не палитра: светлая или тёмная, как в системе

THEMES = {
    "paper": {
        "bg": "#f5f3ee", "card": "#fbfaf7", "border": "#d6cfbf",
        "text": "#1d2a36", "muted": "#56626e",
        "accent": "#24508a", "on_accent": "#ffffff",
        "accent_fg": "#24508a",
        "day_bg": "#f1e8cc", "day_title": "#6b4800",
        "ok": "#1b6b3f", "bad": "#a8261d",
        "right_bg": "#1b6b3f", "wrong_bg": "#a8261d", "on_mark": "#ffffff",
        "tip_bg": "#1d2a36", "tip_fg": "#f5f3ee",
        "scene_bg": "#f5f3ee", "scene_hi": "#fdfcf8",          # схема - прямо на странице
        "view_bg": config.BG, "view_hi": "#1b3a50",
    },
    "black": {
        "bg": "#0b0b0c", "card": "#141416", "border": "#2e2d2b",
        "text": "#ecebe6", "muted": "#a3a19a",
        "accent": "#8cb4e8", "on_accent": "#0b0b0c",           # светлые чернила на чёрном
        "accent_fg": "#8cb4e8",
        "day_bg": "#1d1912", "day_title": "#e0b860",
        "ok": "#5fd08a", "bad": "#ff7a6e",
        "right_bg": "#2e7d4f", "wrong_bg": "#8a2b26", "on_mark": "#ffffff",
        "tip_bg": "#000000", "tip_fg": "#ecebe6",
        "scene_bg": "#0b0b0c", "scene_hi": "#16232c",          # схема - прямо на чёрной странице
        "view_bg": "#10161b", "view_hi": "#1b3a50",
    },
}

# пары (текст, фон), которые встречаются в интерфейсе
TEXT_PAIRS = [("text", "bg"), ("muted", "bg"), ("text", "card"), ("muted", "card"),
              ("on_accent", "accent"), ("accent_fg", "card"),
              ("text", "day_bg"), ("day_title", "day_bg"), ("ok", "card"), ("bad", "card"),
              ("on_mark", "right_bg"), ("on_mark", "wrong_bg"), ("tip_fg", "tip_bg")]

C = dict(THEMES[DEFAULT])          # цвета текущей темы; словарь один и тот же, меняется на месте
_name = DEFAULT


def current():
    return _name


def system_theme():
    """светлая или тёмная тема - как в системе: спрашиваем Qt, а до QApplication - реестр Windows"""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance():
            scheme = QGuiApplication.styleHints().colorScheme()
            if scheme != Qt.ColorScheme.Unknown:
                return "black" if scheme == Qt.ColorScheme.Dark else "paper"
    except ImportError:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return "paper" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "black"
    except (ImportError, OSError):
        return DEFAULT


def set_theme(name):
    """name - палитра из THEMES или SYSTEM; current() вернёт именно name, а цвета в C - уже палитры"""
    global _name
    if name not in THEMES and name != SYSTEM:
        name = DEFAULT
    _name = name
    C.clear()
    C.update(THEMES[system_theme() if name == SYSTEM else name])


def contrast(a, b):
    """контраст двух цветов #rrggbb по WCAG 2: от 1 до 21"""
    def lum(c):
        ch = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
