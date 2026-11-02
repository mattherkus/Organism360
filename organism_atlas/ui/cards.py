"""Содержимое карточки справа: карточка органа (со строкой «назад - вперёд»), стартовая карточка
с экскурсиями, шаг экскурсии, вопрос викторины и карточка настройки викторины. Строятся из общих
виджетов (widgets.py) и складываются столбиком через put()."""

from PySide6.QtWidgets import QGridLayout

from .. import i18n
from ..diseases import on_card
from ..i18n import t
from ..organs import ORGANS, fact_of_day
from .scaling import px
from .widgets import (QuizProgress, alive, bar, clear, flat_button, hbox, heading, joined, label, linked, put,
                      rich_label, rounded_card, section, set_button_bg, spacer, vbox)


def nav_row(lay, nav):
    """строка над карточкой органа: кнопки «назад» и «вперёд» по просмотренным карточкам и «крошки» -
    предыдущие карточки ссылками. nav - (назад (подсказка, функция или None), вперёд (то же),
    [(название, ключ-ссылка)], on_crumb(ключ))"""
    back, forward, crumbs, on_crumb = nav
    row = hbox(spacing=4)
    for text, (tip, command) in (("←", back), ("→", forward)):
        b = flat_button(text, command, size=9, padx=8, pady=1)
        b.setToolTip(tip)
        b.setEnabled(command is not None)
        row.addWidget(b)
    if crumbs:
        row.addSpacing(px(6))
        w = rich_label(joined(crumbs, "  ›  "), on_crumb, "muted", 9)
        w.setWordWrap(False)
        row.addWidget(w, 1)
    else:
        row.addStretch(1)
    put(lay, row, top=10)


def fill_card(card, key, on_3d=None, compact=False, back=None, on_link=None, nav=None):
    """карточка органа; compact - без заболеваний и факта дня (для 3D-просмотра, где мало места по высоте);
    back - (текст, функция) кнопки под кнопкой 3D: вернуться к экскурсиям;
    on_link(ключ) - упоминания других органов и болезней становятся ссылками на их карточки и статьи,
    а заболевания органа - ссылками на статьи справочника болезней;
    nav - история просмотренных карточек (см. nav_row)"""
    lay = card.lay
    clear(lay)
    c = ORGANS[key]["color"]
    seen = {key}                                                        # на себя ссылок нет
    bar(lay, c)                                                         # цветная полоска органа
    if nav:
        nav_row(lay, nav)
    put(lay, label(i18n.name(key), size=15, bold=True), top=8 if nav else 12)
    put(lay, label(i18n.subtitle(key), "muted", italic=True), bottom=6)
    put(lay, linked(i18n.organ(key, "desc"), on_link, seen), bottom=8)
    section(lay, t("card_location"), i18n.organ(key, "location"), on_link, seen)
    section(lay, t("card_system"), ", ".join(t("system_" + x) for x in ORGANS[key]["systems"]))
    heading(lay, t("card_facts"))
    for f in i18n.organ(key, "facts"):
        put(lay, linked("•  " + f, on_link, seen), top=2, bottom=2)
    if not compact:
        heading(lay, t("card_diseases"))
        put(lay, rich_label(joined(on_card(key), "  ·  "), on_link))   # ссылки на статьи справочника
        day = rounded_card(fill="day_bg", border=c, radius=10)
        put(day.lay, label("★  " + t("card_fact_of_day"), "day_title", 10, bold=True), top=8, bottom=2, x=10)
        put(day.lay, linked(fact_of_day(key), on_link, seen), bottom=8, x=10)
        put(lay, day, top=12)
    if on_3d:
        put(lay, flat_button(t("card_3d"), on_3d, bg="accent"), top=12, bottom=0 if back else 14, align="left")
    if back:
        put(lay, flat_button(back[0], back[1], anchor="w"), top=8 if on_3d else 12, bottom=14, align="left")
    if not on_3d and not back:
        spacer(lay, 10)


def fill_start(card, title, hint, tours_title, tours, review=None, organ=None):
    """карточка режима «Изучать», пока орган не выбран: подсказка, кнопки экскурсий, повторение и орган дня.
    tours - [(текст кнопки, функция)];
    review - (заголовок, [(текст, роль цвета)], кнопка (текст, функция) или None): сколько пора повторить, серия дней;
    organ - (заголовок, ключ органа, факт, кнопка (текст, функция)): орган дня"""
    lay = card.lay
    clear(lay)
    put(lay, label(title, size=15, bold=True), top=14, bottom=4)
    put(lay, label(hint, "muted"), bottom=6)
    if tours:
        heading(lay, tours_title)
        for text, command in tours:
            put(lay, flat_button(text, command, anchor="w", pady=4), top=3)
    if review:
        head, lines, button = review
        heading(lay, head, top=12)
        for text, fg in lines:
            put(lay, label(text, fg, 10, bold=fg != "muted"), top=2)
        if button:
            put(lay, flat_button(button[0], button[1], bg="accent", pady=4), top=6, align="left")
    if organ:
        head, key, fact, button = organ
        c = ORGANS[key]["color"]
        day = rounded_card(fill="day_bg", border=c, radius=10)
        put(day.lay, label("★  " + head, "day_title", 10, bold=True), top=8, bottom=2, x=10)
        put(day.lay, label(i18n.name(key), size=12, bold=True), x=10)
        put(day.lay, label(fact, size=10), top=2, bottom=6, x=10)
        put(day.lay, flat_button(button[0], button[1], pady=3, size=9), bottom=10, x=10, align="left")
        put(lay, day, top=14)
    spacer(lay, 14)


def fill_tour(card, progress, title, subtitle, text, c, buttons, extra=(), hint=None):
    """карточка шага экскурсии. progress - «Путь пищи · шаг 2 из 8»; c - цвет полоски (орган или роль);
    buttons - [(текст, функция, роль фона, доступна)] в строку (назад / дальше);
    extra - [(текст, функция)] кнопки столбиком под ними; hint - мелкая подсказка внизу"""
    lay = card.lay
    clear(lay)
    bar(lay, c)
    put(lay, label(progress, "muted", 10, bold=True), top=12)
    put(lay, label(title, size=15, bold=True), top=4)
    if subtitle:
        put(lay, label(subtitle, "muted", italic=True))
    put(lay, label(text), top=8, bottom=12)
    row = QGridLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setHorizontalSpacing(px(6))
    for i, (txt, command, bg, enabled) in enumerate(buttons):
        b = flat_button(txt, command, bg=bg)
        b.setEnabled(enabled)
        row.addWidget(b, 0, i)
        row.setColumnStretch(i, 1)
    put(lay, row)
    for txt, command in extra:
        put(lay, flat_button(txt, command, anchor="w"), top=6)
    if hint:
        put(lay, label(hint, "muted", 9), top=8)
    spacer(lay, 14)


def fill_question(card, progress, title, hint, feedback=None, options=(), on_pick=None, give_up=None):
    """карточка вопроса викторины.
    progress - (строка «Вопрос N из M · Ошибок: K», доля пройденных вопросов, доля оставшегося времени или None);
    feedback - (текст, роль цвета) после ответа или None;
    options - [(ключ, название)] для кнопок-вариантов, on_pick(ключ) по нажатию; на кнопке - значок
    клавиши-цифры, которая её нажимает; give_up - (текст, функция) кнопки «Сдаться» под вариантами.
    Возвращает (шапку QuizProgress, {ключ: кнопка})."""
    lay = card.lay
    clear(lay)
    bar(lay, "accent")
    prog = put(lay, QuizProgress(*progress), top=12)
    put(lay, label(title, size=15, bold=True), top=8, bottom=4)
    put(lay, label(hint, "muted"), bottom=10)
    if feedback:
        put(lay, label(feedback[0], feedback[1], bold=True), bottom=10)
    buttons = {}
    for i, (key, name) in enumerate(options):
        b = put(lay, flat_button(name, lambda k=key: on_pick(k), anchor="w", padx=10), bottom=8)
        b.set_key_hint(str(i + 1))
        buttons[key] = b
    if give_up:
        b = flat_button(give_up[0], give_up[1], bg="bg", size=9, padx=10, pady=3)
        b.fg = "muted"
        put(lay, b, top=4 if options else 0, bottom=8, align="left")
    spacer(lay, 6)
    return prog, buttons


def mark(b, role):
    """покрасить кнопку-вариант: right_bg - верный ответ, wrong_bg - ошибка (такую больше не нажать)"""
    set_button_bg(b, role)
    if role == "wrong_bg":
        b.setEnabled(False)


# --- карточка настройки викторины

def setup_button(b, text, command, selected, enabled):
    """кнопка варианта на карточке настройки: текст, действие, выбрана ли, доступна ли"""
    b.setText(text)
    b.set_command(command)
    b.setEnabled(enabled)
    set_button_bg(b, "accent" if selected else "card")


def fill_setup(card, title, desc, rows, start_text, on_start, history_title, history):
    """карточка настройки викторины перед стартом.
    rows - [(заголовок, [(текст, значение, доступен)], выбранное, on_pick(значение), подсказка, раскладка)];
    раскладка: False - в строку, True - столбиком, число - сеткой в столько столбцов;
    history - строки списка «последние игры» (если игр не было - одна строка-заглушка).
    Если в карточке уже такая же настройка (те же строки и столько же вариантов), она обновляется на месте:
    после щелчка по варианту карточка не пересоздаётся и не мигает."""
    texts = [title, desc]                                   # все надписи карточки по порядку
    for head, _options, _selected, _on_pick, hint, _vertical in rows:
        texts += [head.upper()] + ([hint] if hint else [])
    texts += [history_title.upper()] + list(history)
    choices = [(text, lambda v=value, f=on_pick: f(v), value == selected, enabled)
               for _head, options, selected, on_pick, _hint, _vertical in rows
               for text, value, enabled in options] + [(start_text, on_start, None, True)]
    shape = [(len(options), bool(hint), vertical) for _h, options, _s, _p, hint, vertical in rows] + [len(history)]
    old = getattr(card, "setup", None)
    if old and old[0] == shape and all(alive(w) and w.parentWidget() is card for w in old[1] + old[2]):
        for w, text in zip(old[1], texts):
            w.setText(text)
        for b, (text, command, selected, enabled) in zip(old[2], choices):
            if selected is None:                                        # «Начать»
                b.setText(text)
                b.set_command(command)
            else:
                setup_button(b, text, command, selected, enabled)
        return
    lay = card.lay
    clear(lay)
    labels, buttons = [], []
    bar(lay, "accent")
    labels.append(put(lay, label(title, size=15, bold=True), top=10))
    labels.append(put(lay, label(desc, "muted"), bottom=4))
    for head, options, _selected, _on_pick, hint, vertical in rows:
        labels.append(heading(lay, head))
        cols = vertical if isinstance(vertical, int) and vertical > 1 else 0          # True - тоже int (1)
        if cols:
            line = QGridLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setHorizontalSpacing(px(6))
            line.setVerticalSpacing(px(6))
            for c in range(cols):
                line.setColumnStretch(c, 1)
        elif vertical:
            line = vbox(spacing=3)
        else:
            line = hbox(spacing=6)
        for i in range(len(options)):
            text, command, selected, enabled = choices[len(buttons)]
            b = flat_button(text, command, anchor="w" if vertical else "center",
                            padx=10 if not vertical else 14, pady=4 if vertical else 6)
            setup_button(b, text, command, selected, enabled)
            buttons.append(b)
            if cols:
                line.addWidget(b, i // cols, i % cols)
            else:
                line.addWidget(b)
        if not vertical:
            line.addStretch(1)
        put(lay, line)
        if hint:
            labels.append(put(lay, label(hint, "muted", 9), top=4))
    buttons.append(put(lay, flat_button(start_text, on_start, bg="accent"), top=12, bottom=2))
    labels.append(heading(lay, history_title))
    for line in history:
        labels.append(put(lay, label(line, "muted", 10)))
    spacer(lay, 10)
    card.setup = (shape, labels, buttons)
