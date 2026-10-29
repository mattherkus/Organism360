"""Настройки (встроенная панель): тема, качество 3D, масштаб интерфейса, схема тела, анимация и язык."""

from .. import i18n, settings, theme
from ..i18n import t
from ..render3d import gpu
from .overlay import Panel
from .scaling import px
from .widgets import alive, clear, flat_button, hbox, heading, label, put, rounded_card, set_button_bg, set_fg

_window = None                  # панель одна: повторное нажатие «Настройки» поднимает её


class SettingsWindow:
    """app - главное окно (App): через него настройки применяются и сохраняются"""

    def __init__(self, app):
        self.app = app
        win = self.win = Panel(app.host, t("settings_title"))
        win.closed.connect(self.close)
        self.card = rounded_card()
        put(win.body, self.card, top=10, bottom=16)
        self.parts = None
        self.refresh()

    def close(self):
        global _window
        if _window is self:
            _window = None

    def raise_(self):
        self.win.raise_panel()

    def rows(self):
        app = self.app
        if app.pending_scale != app.ui_scale:
            scale_hint = t("settings_scale_pending", percent=round(app.pending_scale * 100)), "accent_fg"
        else:
            scale_hint = t("settings_scale_hint"), "muted"
        renderer = gpu.info()
        quality_hint = t("settings_quality_hint") + "\n" + (t("settings_gpu", name=renderer) if renderer
                                                            else t("settings_no_gpu"))
        return [
            (t("settings_theme"), [(t("theme_" + n), n) for n in settings.CHOICES["theme"]],
             theme.current(), app.set_theme, None),
            (t("settings_quality"), [(t("quality_" + q), q) for q in settings.CHOICES["quality"]],
             app.quality, app.set_quality, (quality_hint, "muted")),
            (t("settings_scale"), [("%d%%" % round(v * 100), v) for v in settings.CHOICES["ui_scale"]],
             app.pending_scale, app.set_ui_scale, scale_hint),
            (t("settings_body"), [(t("body_" + v), v) for v in settings.CHOICES["body"]],
             app.body, app.set_body, (t("settings_body_hint"), "muted")),
            (t("settings_animation"), [(t("animation_" + v), v) for v in settings.CHOICES["animation"]],
             app.animation, app.set_animation, (t("settings_animation_hint"), "muted")),
            (t("settings_language"), [(i18n.language_name(c), c) for c in i18n.languages()],
             i18n.base(), app.set_lang, None),
            (t("settings_latin"), [(t("latin_on"), True), (t("latin_off"), False)],
             i18n.latin(), app.set_latin, (t("latin_hint"), "muted")),
        ]

    def refresh(self):
        """обновить содержимое после смены языка или любого выбора: на месте, без пересоздания (не мигает)"""
        self.win.title(t("settings_title"))
        rows = self.rows()
        shape = [(len(options), bool(hint)) for _title, options, _selected, _on_pick, hint in rows]
        parts = self.parts
        if not (parts and parts[0] == shape and all(alive(w) for w in parts[1])):
            self.build(rows)
            return
        _shape, _all, close, lines = parts
        close.setText(t("settings_close"))
        for (head, options, selected, on_pick, hint), (head_w, buttons, hint_w) in zip(rows, lines):
            head_w.setText(head.upper())
            for b, (text, value) in zip(buttons, options):
                b.setText(text)
                b.set_command(lambda v=value, f=on_pick: self.pick(f, v))
                set_button_bg(b, "accent" if value == selected else "card")
            if hint:
                set_fg(hint_w, hint[1]).setText(hint[0])

    def build(self, rows):
        lay = self.card.lay
        clear(lay)
        lines = [self.row(*r) for r in rows]
        close = flat_button(t("settings_close"), self.win.close_panel, bg="accent")
        put(lay, close, top=14, bottom=16, x=20, align="right")
        widgets = [close] + [w for head, buttons, hint in lines for w in (head, *buttons, hint) if w]
        self.parts = ([(len(b), h is not None) for _w, b, h in lines], widgets, close, lines)

    def row(self, title, options, selected, on_pick, hint=None):
        """заголовок и ряд кнопок-вариантов; выбранный вариант подсвечен акцентом;
        hint - (текст, роль цвета) подсказки под рядом. Возвращает (заголовок, [кнопки], подсказка или None)"""
        lay = self.card.lay
        head = heading(lay, title, top=14, bottom=4, x=20)
        line = hbox(spacing=6)
        buttons = []
        for text, value in options:
            b = flat_button(text, lambda v=value, f=on_pick: self.pick(f, v), padx=10)
            set_button_bg(b, "accent" if value == selected else "card")
            line.addWidget(b)
            buttons.append(b)
        line.addStretch(1)
        put(lay, line, x=20)
        hint_w = None
        if hint:
            hint_w = put(lay, label(hint[0], hint[1], 9), top=4, x=20)
            hint_w.setMaximumWidth(px(460))
        return head, buttons, hint_w

    def pick(self, on_pick, value):
        on_pick(value)
        if self.win.is_open:
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
