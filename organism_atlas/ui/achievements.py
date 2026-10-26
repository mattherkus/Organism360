"""Панель «Достижения»: серия дней и список достижений (полученные - ярко, остальные - приглушённо)."""

from .. import achievements, progress
from ..config import FONT
from ..i18n import t
from .overlay import Panel, top
from .scaling import px
from .widgets import frame, heading, label, rounded_card


def button_text(data=None):
    """подпись кнопки в верхней панели: сколько достижений получено"""
    return t("ach_button", got=len(achievements.earned(data or progress.load())), total=len(achievements.KEYS))


def show_achievements(root):
    """открыть панель (если уже открыта - просто поднять её)"""
    p = top(root)
    if isinstance(p, AchievementsPanel):
        return p
    return AchievementsPanel(root)


class AchievementsPanel(Panel):
    def __init__(self, root):
        super().__init__(root, t("ach_title"))
        data = progress.load()
        got = set(achievements.earned(data))
        box, card = rounded_card(self.body, width=px(640))
        box.pack(padx=px(16), pady=(px(10), px(16)))
        heading(card, t("ach_streak_title"))
        label(card, t("ach_streak", n=achievements.streak(data), best=achievements.best_streak(data)),
              fg="accent_fg", font=(FONT, 15, "bold"), anchor="w").pack(fill="x", padx=px(16))
        label(card, t("ach_streak_hint"), fg="muted", font=(FONT, 9), anchor="w", justify="left",
              wraplength=px(580)).pack(fill="x", padx=px(16))
        heading(card, t("ach_list_title", got=len(got), total=len(achievements.KEYS)))
        grid = frame(card)                              # в два столбца: так панель помещается по высоте
        grid.pack(fill="x", padx=px(16))
        grid.columnconfigure((0, 1), weight=1, uniform="col")
        for i, key in enumerate(achievements.KEYS):
            row = frame(grid)
            row.grid(row=i // 2, column=i % 2, sticky="new", pady=(px(4), 0), padx=(0, px(12) if i % 2 == 0 else 0))
            on = key in got
            label(row, "★" if on else "☆", fg="day_title" if on else "muted",
                  font=(FONT, 13, "bold")).pack(side="left", anchor="n", padx=(0, px(8)))
            text = frame(row)
            text.pack(side="left", fill="x", expand=True)
            label(text, t("ach_" + key), fg="text" if on else "muted", font=(FONT, 11, "bold"),
                  anchor="w").pack(fill="x")
            label(text, t("ach_%s_desc" % key), fg="muted", font=(FONT, 9), anchor="w", justify="left",
                  wraplength=px(250)).pack(fill="x")
        frame(card, height=px(12)).pack()
