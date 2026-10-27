"""Панель «Достижения»: серия дней и список достижений (полученные - ярко, остальные - приглушённо)."""

from PySide6.QtWidgets import QGridLayout

from .. import achievements, progress
from ..i18n import t
from .overlay import Panel, top
from .scaling import px
from .widgets import heading, hbox, label, put, rounded_card, spacer, vbox


def button_text(data=None):
    """подпись кнопки в верхней панели: сколько достижений получено"""
    return t("ach_button", got=len(achievements.earned(data or progress.load())), total=len(achievements.KEYS))


def show_achievements(host):
    """открыть панель (если уже открыта - просто поднять её)"""
    p = top(host)
    if isinstance(p, AchievementsPanel):
        return p
    return AchievementsPanel(host)


class AchievementsPanel(Panel):
    def __init__(self, host):
        super().__init__(host, t("ach_title"))
        data = progress.load()
        got = set(achievements.earned(data))
        card = rounded_card(width=px(640))
        put(self.body, card, top=10, bottom=16)
        lay = card.lay
        heading(lay, t("ach_streak_title"))
        put(lay, label(t("ach_streak", n=achievements.streak(data), best=achievements.best_streak(data)),
                       "accent_fg", 15, bold=True))
        put(lay, label(t("ach_streak_hint"), "muted", 9))
        heading(lay, t("ach_list_title", got=len(got), total=len(achievements.KEYS)))
        grid = QGridLayout()                             # в два столбца: так панель помещается по высоте
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(px(12))
        grid.setVerticalSpacing(px(4))
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for i, key in enumerate(achievements.KEYS):
            on = key in got
            row = hbox(spacing=8)
            star = label("★" if on else "☆", "day_title" if on else "muted", 13, bold=True, wrap=False)
            row.addWidget(star)
            text = vbox()
            text.addWidget(label(t("ach_" + key), "text" if on else "muted", 11, bold=True))
            text.addWidget(label(t("ach_%s_desc" % key), "muted", 9))
            text.addStretch(1)
            row.addLayout(text, 1)
            grid.addLayout(row, i // 2, i % 2)
        put(lay, grid, top=4)
        spacer(lay, 12)
