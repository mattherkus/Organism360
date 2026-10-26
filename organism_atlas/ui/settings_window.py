"""Настройки (встроенная панель): тема, качество 3D, масштаб интерфейса, схема тела, анимация и язык."""

from .. import i18n, settings, theme
from ..config import FONT
from ..i18n import t
from ..theme import style
from .overlay import Panel
from .scaling import px
from .widgets import flat_button, frame, label, rounded_card, set_button_bg

_window = None                  # панель одна: повторное нажатие «Настройки» поднимает её


class SettingsWindow:
    """app - главное окно (App): через него настройки применяются и сохраняются"""

    def __init__(self, app):
        self.app = app
        win = self.win = Panel(app.root, t("settings_title"))
        win.bind("<Destroy>", self.close)
        box, self.body = rounded_card(win.body)
        box.pack(padx=px(16), pady=(px(10), px(16)))
        self.refresh()

    def close(self, e):
        global _window
        if e.widget is self.win and _window is self:
            _window = None

    def raise_(self):
        self.win.raise_()

    def refresh(self):
        """обновить содержимое после смены языка или любого выбора: на месте, без пересоздания (не мигает)"""
        app = self.app
        self.win.title(t("settings_title"))
        if app.pending_scale != app.ui_scale:
            scale_hint = t("settings_scale_pending", percent=round(app.pending_scale * 100)), "accent_fg"
        else:
            scale_hint = t("settings_scale_hint"), "muted"
        rows = [
            (t("settings_theme"), [(t("theme_" + n), n) for n in settings.CHOICES["theme"]],
             theme.current(), app.set_theme, None),
            (t("settings_quality"), [(t("quality_" + q), q) for q in settings.CHOICES["quality"]],
             app.quality, app.set_quality, (t("settings_quality_hint"), "muted")),
            (t("settings_scale"), [("%d%%" % round(v * 100), v) for v in settings.CHOICES["ui_scale"]],
             app.pending_scale, app.set_ui_scale, scale_hint),
            (t("settings_body"), [(t("body_" + v), v) for v in settings.CHOICES["body"]],
             app.body, app.set_body, (t("settings_body_hint"), "muted")),
            (t("settings_animation"), [(t("animation_" + v), v) for v in settings.CHOICES["animation"]],
             app.animation, app.set_animation, (t("settings_animation_hint"), "muted")),
            (t("settings_language"), [(i18n.language_name(c), c) for c in i18n.available()],
             i18n.current(), app.set_lang, None),
        ]
        shape = [(len(options), bool(hint)) for _title, options, _selected, _on_pick, hint in rows]
        parts = getattr(self, "parts", None)
        if not (parts and parts[0] == shape and all(w.winfo_exists() for w in parts[1])):
            self.build(rows)
            return
        _shape, _all, close, lines = parts
        close.config(text=t("settings_close"))
        for (head, options, selected, on_pick, hint), (head_w, buttons, hint_w) in zip(rows, lines):
            head_w.config(text=head.upper())
            for b, (text, value) in zip(buttons, options):
                b.config(text=text, command=lambda v=value, f=on_pick: self.pick(f, v))
                set_button_bg(b, "accent" if value == selected else "card")
            if hint:
                style(hint_w, fg=hint[1]).config(text=hint[0])

    def build(self, rows):
        body = self.body
        for w in body.winfo_children():
            w.destroy()
        lines = [self.row(*r) for r in rows]
        close = flat_button(body, t("settings_close"), self.win.destroy, bg="accent")
        close.pack(anchor="e", padx=px(20), pady=(px(14), px(16)))
        widgets = [close] + [w for head, buttons, hint in lines for w in (head, *buttons, hint) if w]
        self.parts = ([(len(b), h is not None) for _w, b, h in lines], widgets, close, lines)

    def row(self, title, options, selected, on_pick, hint=None):
        """заголовок и ряд кнопок-вариантов; выбранный вариант подсвечен акцентом;
        hint - (текст, роль цвета) подсказки под рядом. Возвращает (заголовок, [кнопки], подсказка или None)"""
        head = label(self.body, title.upper(), fg="muted", font=(FONT, 9, "bold"), anchor="w")
        head.pack(fill="x", padx=px(20), pady=(px(14), px(4)))
        line = frame(self.body)
        line.pack(fill="x", padx=px(20))
        buttons = []
        for i, (text, value) in enumerate(options):
            b = flat_button(line, text, lambda v=value, f=on_pick: self.pick(f, v))
            set_button_bg(b, "accent" if value == selected else "card")
            b.config(padx=px(10))
            b.pack(side="left", padx=(px(6) if i else 0, 0))
            buttons.append(b)
        hint_w = None
        if hint:
            hint_w = label(self.body, hint[0], fg=hint[1], font=(FONT, 9), justify="left", anchor="w",
                           wraplength=px(420))
            hint_w.pack(fill="x", padx=px(20), pady=(px(4), 0))
        return head, buttons, hint_w

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
    """перерисовать открытую панель настроек (смена языка из главного окна)"""
    if _window is not None:
        _window.refresh()
