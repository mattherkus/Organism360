"""Окно настроек: тема, качество 3D, масштаб интерфейса и язык."""

import tkinter as tk

from .. import i18n, settings, theme
from ..config import FONT
from ..i18n import t
from ..theme import style
from .scaling import px
from .widgets import flat_button, frame, label, set_button_bg

_window = None                  # окно одно: повторное нажатие «Настройки» поднимает его


class SettingsWindow:
    """app - главное окно (App): через него настройки применяются и сохраняются"""

    def __init__(self, app):
        self.app = app
        win = self.win = style(tk.Toplevel(app.root), bg="bg")
        win.resizable(False, False)
        win.transient(app.root)
        win.bind("<Destroy>", self.close)
        win.bind("<Escape>", lambda e: win.destroy())
        self.body = style(frame(win, highlightthickness=1), highlightbackground="border")
        self.body.pack(padx=px(16), pady=px(16))
        self.refresh()
        win.update_idletasks()
        root = app.root
        x = root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - win.winfo_height()) // 3
        win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))

    def close(self, e):
        global _window
        if e.widget is self.win and _window is self:
            _window = None

    def raise_(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def refresh(self):
        """перестроить содержимое: после смены языка или любого выбора"""
        app, body = self.app, self.body
        for w in body.winfo_children():
            w.destroy()
        self.win.title(t("settings_title"))
        label(body, t("settings_title"), font=(FONT, 15, "bold"),
              anchor="w").pack(fill="x", padx=px(20), pady=(px(16), px(4)))

        self.row(t("settings_theme"), [(t("theme_" + n), n) for n in settings.CHOICES["theme"]],
                 theme.current(), app.set_theme)
        self.row(t("settings_quality"), [(t("quality_" + q), q) for q in settings.CHOICES["quality"]],
                 app.quality, app.set_quality, t("settings_quality_hint"))
        if app.pending_scale != app.ui_scale:
            hint, fg = t("settings_scale_pending", percent=round(app.pending_scale * 100)), "accent_fg"
        else:
            hint, fg = t("settings_scale_hint"), "muted"
        self.row(t("settings_scale"), [("%d%%" % round(v * 100), v) for v in settings.CHOICES["ui_scale"]],
                 app.pending_scale, app.set_ui_scale, hint, fg)
        self.row(t("settings_language"), [(i18n.language_name(c), c) for c in i18n.available()],
                 i18n.current(), app.set_lang)

        flat_button(body, t("settings_close"), self.win.destroy, bg="accent").pack(
            anchor="e", padx=px(20), pady=(px(14), px(16)))

    def row(self, title, options, selected, on_pick, hint=None, hint_fg="muted"):
        """заголовок и ряд кнопок-вариантов; выбранный вариант подсвечен акцентом"""
        label(self.body, title.upper(), fg="muted", font=(FONT, 9, "bold"),
              anchor="w").pack(fill="x", padx=px(20), pady=(px(12), px(4)))
        line = frame(self.body)
        line.pack(fill="x", padx=px(20))
        for i, (text, value) in enumerate(options):
            b = flat_button(line, text, lambda v=value: self.pick(on_pick, v))
            set_button_bg(b, "accent" if value == selected else "card")
            b.config(padx=px(10))
            b.pack(side="left", padx=(px(6) if i else 0, 0))
        if hint:
            label(self.body, hint, fg=hint_fg, font=(FONT, 9), justify="left", anchor="w",
                  wraplength=px(420)).pack(fill="x", padx=px(20), pady=(px(4), 0))

    def pick(self, on_pick, value):
        on_pick(value)
        if self.win.winfo_exists():
            self.refresh()


def show_settings(app):
    global _window
    if _window is None:
        _window = SettingsWindow(app)
    else:
        _window.raise_()


def refresh_settings():
    """перерисовать открытое окно настроек (смена языка из главного окна)"""
    if _window is not None:
        _window.refresh()
