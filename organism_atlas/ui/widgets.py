"""Общие виджеты: плоская кнопка и карточка органа. Цвета - роли текущей темы (theme.py)."""

import tkinter as tk

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..organs import ORGANS, fact_of_day
from ..theme import style
from .scaling import px


def flat_button(parent, text, command, bg="card", **kw):
    """bg - роль фона: card для обычной кнопки, accent для главной"""
    b = tk.Button(parent, text=text, command=command, bd=0, relief="flat", cursor="hand2",
                  font=(FONT, 10, "bold"), padx=px(14), pady=px(6), highlightthickness=1, **kw)
    return set_button_bg(b, bg)


def set_button_bg(b, bg):
    """сменить роль фона кнопки (выбранный режим, язык, тема); текст подбирается к фону"""
    return style(b, bg=bg, fg="on_accent" if bg == "accent" else "text", activebackground="accent",
                 activeforeground="on_accent", highlightbackground="border")


def label(parent, text, fg="text", bg="card", **kw):
    return style(tk.Label(parent, text=text, **kw), bg=bg, fg=fg)


def frame(parent, bg="card", **kw):
    return style(tk.Frame(parent, **kw), bg=bg)


def heading(card, text):
    label(card, text.upper(), fg="muted", font=(FONT, 9, "bold"),
          anchor="w").pack(fill="x", padx=px(16), pady=(px(8), px(2)))


def section(card, title, text, wrap):
    heading(card, title)
    label(card, text, font=(FONT, 11), justify="left",
          anchor="w", wraplength=wrap).pack(fill="x", padx=px(16))


def fill_card(card, key, on_3d=None, empty=None, compact=False, wrap=None):
    """карточка органа; compact - без заболеваний и факта дня (для окна 3D, где мало места по высоте);
    wrap - ширина переноса текста (по умолчанию под правую колонку главного окна)"""
    for w in card.winfo_children():
        w.destroy()
    wrap = wrap or px(300)
    if empty:
        label(card, empty[0], font=(FONT, 15, "bold"),
              anchor="w").pack(fill="x", padx=px(16), pady=(px(14), px(4)))
        label(card, empty[1], fg="muted", font=(FONT, 11), justify="left",
              anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(0, px(14)))
        return
    color = ORGANS[key]["color"]
    tk.Frame(card, bg=color, height=3).pack(fill="x")               # цветная полоска органа
    label(card, i18n.name(key), font=(FONT, 15, "bold"), justify="left",
          anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(px(12), 0))
    label(card, i18n.subtitle(key), fg="muted", font=(FONT, 11, "italic"),
          anchor="w").pack(fill="x", padx=px(16), pady=(0, px(6)))
    label(card, i18n.organ(key, "desc"), font=(FONT, 11), justify="left",
          anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(0, px(8)))
    section(card, t("card_location"), i18n.organ(key, "location"), wrap)
    heading(card, t("card_facts"))
    for f in i18n.organ(key, "facts"):
        label(card, "•  " + f, font=(FONT, 11), justify="left",
              anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=2)
    if not compact:
        section(card, t("card_diseases"), "  ·  ".join(i18n.organ(key, "diseases")), wrap)
        day = frame(card, "day_bg", highlightbackground=color, highlightthickness=1)
        day.pack(fill="x", padx=px(16), pady=(px(12), 0))
        label(day, "★  " + t("card_fact_of_day"), fg="day_title", bg="day_bg", font=(FONT, 10, "bold"),
              anchor="w").pack(fill="x", padx=px(10), pady=(px(8), px(2)))
        label(day, fact_of_day(key), bg="day_bg", font=(FONT, 11), justify="left",
              anchor="w", wraplength=wrap - px(22)).pack(fill="x", padx=px(10), pady=(0, px(8)))
    if on_3d:
        flat_button(card, t("card_3d"), on_3d, bg="accent").pack(anchor="w", padx=px(16), pady=(px(12), px(14)))
    else:
        frame(card, height=px(10)).pack()


def fill_question(card, progress, title, hint, feedback=None, options=(), on_pick=None):
    """карточка вопроса викторины.
    progress - строка «Вопрос N из M · Ошибок: K»; feedback - (текст, роль цвета) после ответа или None;
    options - [(ключ, название)] для кнопок-вариантов, on_pick(ключ) по нажатию.
    Возвращает (метка прогресса, {ключ: кнопка})."""
    for w in card.winfo_children():
        w.destroy()
    wrap = px(270)
    frame(card, "accent", height=3).pack(fill="x")
    prog = label(card, progress, fg="muted", font=(FONT, 10, "bold"), anchor="w")
    prog.pack(fill="x", padx=px(16), pady=(px(12), 0))
    label(card, title, font=(FONT, 15, "bold"), justify="left",
          anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(px(4), px(4)))
    label(card, hint, fg="muted", font=(FONT, 11), justify="left",
          anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(0, px(10)))
    if feedback:
        label(card, feedback[0], fg=feedback[1], font=(FONT, 11, "bold"), justify="left",
              anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(0, px(10)))
    buttons = {}
    for i, (key, name) in enumerate(options):
        b = flat_button(card, "%d.  %s" % (i + 1, name), lambda k=key: on_pick(k), anchor="w")
        b.pack(fill="x", padx=px(16), pady=(0, px(8)))
        buttons[key] = b
    frame(card, height=px(6)).pack()
    return prog, buttons


def toggle(parent, text, on, command, enabled=True, color=None):
    """переключатель-строка панели слоёв: ☑/☐ и подпись; color - цветная метка органа слева"""
    row = frame(parent)
    row.pack(fill="x", pady=(0, px(1)))
    if color:
        tk.Frame(row, bg=color, width=px(4)).pack(side="left", fill="y")
    b = flat_button(row, "", command, anchor="w")
    b.config(font=(FONT, 9), padx=px(8), pady=px(1), highlightthickness=0)
    set_toggle(b, text, on)
    if not enabled:
        style(b, disabledforeground="muted")
        b.config(state="disabled", cursor="")
    b.pack(side="left", fill="x", expand=True)
    return b


SHOW_ALL = "_show_all"            # ключ кнопки «Показать всё» в словаре, который отдаёт fill_layers


def show_all_button(buttons, visible):
    """показать или спрятать кнопку «Показать всё», не пересоздавая панель"""
    b = buttons[SHOW_ALL]
    if visible and not b.winfo_manager():
        b.pack(side="right")
    elif not visible and b.winfo_manager():
        b.pack_forget()


def set_toggle(b, text, on):
    """обновить переключатель на месте (без пересоздания панели: так щелчок срабатывает сразу)"""
    b.config(text=("☑  " if on else "☐  ") + text)
    style(b, fg="text" if on else "muted")


def fill_layers(card, title, layers, organs_title, organs, on_layer, on_organ, organs_enabled=True,
                note=None, show_all=None):
    """панель слоёв слева от схемы.
    layers - [(ключ, текст, виден)] слоёв тела; organs - [(ключ, название, цвет, виден)];
    organs_enabled - можно ли скрывать органы (в викторине нельзя), note - пояснение под списком;
    show_all - (текст, функция, видна ли) кнопки «Показать всё» (видна, когда что-то скрыто).
    Возвращает {ключ слоя или органа: переключатель} для set_toggle и кнопку «Показать всё» под SHOW_ALL."""
    for w in card.winfo_children():
        w.destroy()
    frame(card, "accent", height=3).pack(fill="x")
    box = frame(card)
    box.pack(fill="x", padx=px(12), pady=(0, px(10)))
    # «Показать всё» - в строке заголовка, а пояснение - над списком органов: низ панели может
    # не поместиться в невысокое окно, а они должны быть видны всегда
    head = frame(box)
    head.pack(fill="x", pady=(px(8), px(4)))
    label(head, title.upper(), fg="muted", font=(FONT, 9, "bold"), anchor="w").pack(side="left")
    b = flat_button(head, show_all[0], show_all[1])
    b.config(font=(FONT, 8, "bold"), padx=px(6), pady=0)
    buttons = {SHOW_ALL: b}
    show_all_button(buttons, show_all[2])
    for key, text, on in layers:
        buttons[key] = toggle(box, text, on, lambda k=key: on_layer(k))
    label(box, organs_title.upper(), fg="muted", font=(FONT, 9, "bold"),
          anchor="w").pack(fill="x", pady=(px(8), px(4)))
    if note:
        label(box, note, fg="muted", font=(FONT, 9), justify="left", anchor="w",
              wraplength=px(170)).pack(fill="x", pady=(0, px(4)))
    for key, text, color, on in organs:
        buttons[key] = toggle(box, text, on, lambda k=key: on_organ(k), enabled=organs_enabled, color=color)
    return buttons


def fill_setup(card, title, desc, rows, start_text, on_start, history_title, history):
    """карточка настройки викторины перед стартом.
    rows - [(заголовок, [(текст, значение, доступен)], выбранное, on_pick(значение), подсказка, столбиком)];
    history - строки списка «последние игры» (если игр не было - одна строка-заглушка)."""
    for w in card.winfo_children():
        w.destroy()
    wrap = px(300)
    frame(card, "accent", height=3).pack(fill="x")
    label(card, title, font=(FONT, 15, "bold"), anchor="w").pack(fill="x", padx=px(16), pady=(px(10), 0))
    label(card, desc, fg="muted", font=(FONT, 11), justify="left", anchor="w",
          wraplength=wrap).pack(fill="x", padx=px(16), pady=(0, px(4)))
    for head, options, selected, on_pick, hint, vertical in rows:
        heading(card, head)
        line = frame(card)
        line.pack(fill="x", padx=px(16))
        for i, (text, value, enabled) in enumerate(options):
            b = flat_button(line, text, lambda v=value: on_pick(v), anchor="w" if vertical else "center")
            set_button_bg(b, "accent" if value == selected else "card")
            if not enabled:
                style(b, disabledforeground="muted")
                b.config(state="disabled", cursor="")
            if vertical:
                b.config(pady=px(4))
                b.pack(fill="x", pady=(px(3) if i else 0, 0))
            else:
                b.config(padx=px(10))
                b.pack(side="left", padx=(px(6) if i else 0, 0))
        if hint:
            label(card, hint, fg="muted", font=(FONT, 9), justify="left", anchor="w",
                  wraplength=wrap).pack(fill="x", padx=px(16), pady=(px(4), 0))
    flat_button(card, start_text, on_start, bg="accent").pack(fill="x", padx=px(16), pady=(px(12), px(2)))
    heading(card, history_title)
    for line in history:
        label(card, line, fg="muted", font=(FONT, 10), justify="left", anchor="w",
              wraplength=wrap).pack(fill="x", padx=px(16))
    frame(card, height=px(10)).pack()
