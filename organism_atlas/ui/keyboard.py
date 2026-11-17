"""Без мыши: стрелки ↑ ↓ выбирают орган на схеме (подсветка, а в «Изучать» - и название рядом), Enter - как
щелчок по нему: в «Изучать» открывает карточку, в «Найди орган», «Кости и мышцы» и «Расставь по порядку» отвечает.

KeyboardChoice помнит выбранный орган (кость, мышцу); окно (App) передаёт ему стрелки и Enter (on_key)."""

from .. import i18n
from ..i18n import t
from ..structures import keys as structure_keys

KINDS = ("study", "find", "body", "order")      # где орган выбирают на схеме (в остальных - кнопками)


class KeyboardChoice:
    def __init__(self, app):
        self.app = app
        self.key = None                        # орган (кость, мышца), выбранный стрелками; None - главная мышь

    def keys(self):
        """что можно выбрать стрелками: в «Изучать» - видимые органы по порядку панели, в «Найди орган»
        и «Расставь по порядку» - органы схемы, в «Кости и мышцы» - кости и мышцы темы"""
        app = self.app
        kind = app.kind()
        if not app.ready() or kind not in KINDS:
            return []
        if kind == "body":
            return structure_keys(app.quiz.body_topic())
        hidden = app.hidden_now()
        return [k for _system, ks in app.groups() for k in ks if k not in hidden]

    def move(self, step):
        """выбрать следующий (step = 1) или предыдущий орган: подсветка, а в «Изучать» - и название рядом"""
        app = self.app
        keys = self.keys()
        i = keys.index(self.key) if self.key in keys else (-1 if step > 0 else 0)
        key = self.key = keys[(i + step) % len(keys)]
        app.cur = key
        app.view.bring_into_view(*app.atlas.center(key))        # приближенная схема - орган за краем окна
        if app.hover_allowed():                        # на сложном уровне и в экзамене контур выдал бы ответ
            app.marks.hover(key)
        name = i18n.name(key)
        if app.mode == "study":                        # в викторине название выдало бы ответ
            app.view.set_tip((*app.view.to_screen(*app.atlas.anchor(key)), name))
            app.set_status(lambda: t("kb_status", name=i18n.name(key)))     # при смене языка - на новом
        app.view.setAccessibleName(name if app.mode == "study" else t("kb_selected"))

    def choose(self):
        """Enter: выбранный стрелками орган - как щелчок по нему (карточка или ответ); True - обработано"""
        app = self.app
        key, kind = self.key, app.kind()
        if key is None:
            return False
        if kind == "study":
            if app.tours.tour is not None or app.flash.active():     # Enter листает экскурсию или карточки
                return False
            app.tours.pause()
            app.show_info(key)
            app.set_spot(key)
            return True
        if kind in ("find", "body", "order"):
            app.quiz.answer(key)
            return True
        return False
