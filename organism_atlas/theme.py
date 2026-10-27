"""Темы оформления интерфейса: тёмная, светлая и высококонтрастная.

Виджеты получают цвета не числами, а ролями (bg, card, text, ...): кнопки и карточки берут цвет роли
в момент рисования, а надписи запоминают свою роль (ui/widgets.py: set_fg), поэтому ui.widgets.retheme()
перекрашивает всё окно на лету.
Фон схемы тела (scene_bg, scene_hi) и кадров 3D (view_bg, view_hi) тоже из темы.
"""

from . import config

DEFAULT = "dark"

THEMES = {
    "dark": {
        "bg": config.BG, "card": config.CARD, "border": config.BORDER,
        "text": config.TEXT, "muted": config.MUTED,
        "accent": config.ACCENT, "on_accent": config.TEXT,     # кнопка выбранного режима и её текст
        "accent_fg": config.ACCENT,                            # акцентный текст на карточке (счёт)
        "day_bg": "#1c3446", "day_title": "#f2c14e",           # плашка «факт дня»
        "ok": "#5fd08a", "bad": "#ff7a6e",                     # отзыв после верного / неверного ответа
        "right_bg": "#2e7d4f", "wrong_bg": "#8a2b26", "on_mark": config.TEXT,   # кнопки-варианты
        "tip_bg": "#000000", "tip_fg": config.TEXT,            # подсказка над схемой
        "scene_bg": config.BG, "scene_hi": "#1a3547",          # фон схемы тела и пятно за телом
        "view_bg": config.BG, "view_hi": "#1b3a50",            # фон кадра 3D и пятно в центре
    },
    "light": {
        "bg": "#eef2f5", "card": "#ffffff", "border": "#b9c7d2",
        "text": "#14232e", "muted": "#4b5d6a",
        "accent": "#1f62a3", "on_accent": "#ffffff",
        "accent_fg": "#1f62a3",
        "day_bg": "#fff5d6", "day_title": "#7a4f00",
        "ok": "#1b7340", "bad": "#b3261e",
        "right_bg": "#1b7340", "wrong_bg": "#b3261e", "on_mark": "#ffffff",
        "tip_bg": "#000000", "tip_fg": "#ffffff",
        "scene_bg": "#eef2f5", "scene_hi": "#ffffff",
        "view_bg": "#eef2f5", "view_hi": "#ffffff",
    },
    # каждый текст к своему фону - не ниже 7:1 (WCAG AAA), это проверяет tests/test_theme.py
    "contrast": {
        "bg": "#000000", "card": "#000000", "border": "#ffffff",
        "text": "#ffffff", "muted": "#e6e6e6",
        "accent": "#ffd400", "on_accent": "#000000",
        "accent_fg": "#ffd400",
        "day_bg": "#000000", "day_title": "#ffd400",
        "ok": "#7dff9b", "bad": "#ff9e94",
        "right_bg": "#005a1e", "wrong_bg": "#8b0000", "on_mark": "#ffffff",
        "tip_bg": "#000000", "tip_fg": "#ffffff",
        "scene_bg": "#000000", "scene_hi": "#0d1d29",
        "view_bg": "#000000", "view_hi": "#0d1d29",
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


def set_theme(name):
    global _name
    if name not in THEMES:
        name = DEFAULT
    _name = name
    C.clear()
    C.update(THEMES[name])


def contrast(a, b):
    """контраст двух цветов #rrggbb по WCAG 2: от 1 до 21"""
    def lum(c):
        ch = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
