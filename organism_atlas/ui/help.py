"""Панель «Горячие клавиши» (F1 или ?): какие клавиши что делают."""

from PySide6.QtWidgets import QGridLayout

from ..i18n import t
from .overlay import Panel
from .scaling import px
from .widgets import label, put, rounded_card, spacer

# (клавиши, ключ описания); клавиши - не слова, а значки, поэтому не переводятся (кроме «перетаскивания»)
KEYS = (
    ("1 … 6", "help_digits"),
    ("Enter", "help_enter"),
    ("← →", "help_arrows"),
    ("Alt + ← →", "help_history"),
    ("Ctrl + F", "help_search"),
    ("K", "help_knowledge"),
    ("↑ ↓  Enter", "help_updown"),
    ("R", "help_read"),
    ("␣  1  2", "help_flash"),
    ("+  −", "help_zoom"),
    ("0  Esc", "help_zoom_reset"),
    (None, "help_pan"),
    ("Esc", "help_esc"),
    ("F1  ?", "help_f1"),
)


class HelpPanel(Panel):
    title_key = "help_title"

    def __init__(self, host):
        super().__init__(host, t(self.title_key))
        self.build()

    def build(self):
        card = rounded_card(width=px(520))
        put(self.body, card, top=10, bottom=16)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(px(16))
        grid.setVerticalSpacing(px(8))
        grid.setColumnStretch(1, 1)
        for i, (keys, desc) in enumerate(KEYS):
            grid.addWidget(label(keys or t("help_drag"), "accent_fg", 10, bold=True, wrap=False), i, 0)
            grid.addWidget(label(t(desc), size=10), i, 1)
        put(card.lay, grid, top=14)
        spacer(card.lay, 14)


show_help = HelpPanel.open                 # открыть панель (если уже открыта - просто вернуть её)
