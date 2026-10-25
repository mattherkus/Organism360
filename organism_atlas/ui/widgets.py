"""Общие виджеты: плоская кнопка, круглый флажок, карточка органа. Цвета - роли текущей темы (theme.py)."""

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..organs import ORGANS, fact_of_day
from ..theme import C, style
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


_dots = {}                      # готовые картинки кружков: {(размер, включён, состояние, цвета): PhotoImage}
_dots_tk = None                 # интерпретатор Tk, которому принадлежат картинки из _dots


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, w):
    """смешать цвета #rrggbb: w = 0 - a, 1 - b; результат - (r, g, b) 0..255"""
    return tuple(round(x + (y - x) * w) for x, y in zip(_rgb(a), _rgb(b)))


def dot_image(master, size, on, state):
    """круглый флажок (сглаженный, с прозрачным фоном). state: normal, hover, press.
    Включён - залитый кружок цвета акцента с галочкой, выключен - кольцо. Наведение и нажатие
    меняют только кружок: при наведении он светлее (у кольца появляется заливка), при нажатии темнее.
    master - виджет, в котором картинка будет показана (картинки Tk принадлежат своему окну Tk)"""
    global _dots_tk
    accent, ring, mark = C["accent"], C["muted"], C["on_accent"]
    key = (size, on, state, accent, ring, mark)
    if _dots_tk is not master.tk:                          # новое окно Tk: старые картинки ему не годятся
        _dots.clear()
        _dots_tk = master.tk
    if key not in _dots:
        ss = 4
        S = size * ss
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        w = max(ss, round(S * 0.11))                       # толщина кольца
        box = (w // 2, w // 2, S - 1 - w // 2, S - 1 - w // 2)
        if on:
            fill = {"normal": _rgb(accent), "hover": _mix(accent, "#ffffff", 0.22),
                    "press": _mix(accent, "#000000", 0.25)}[state]
            d.ellipse(box, fill=fill)
        else:
            outline = ring if state == "normal" else _mix(accent, "#ffffff", 0.22)
            fill = {"normal": None, "hover": _mix(accent, "#000000", 0.45) + (110,),
                    "press": _mix(accent, "#000000", 0.2) + (200,)}[state]
            d.ellipse(box, fill=fill, outline=outline, width=w)
        if on:                                             # галочка
            pts = [(S * 0.28, S * 0.52), (S * 0.44, S * 0.68), (S * 0.73, S * 0.36)]
            d.line(pts, fill=_rgb(mark), width=round(S * 0.12), joint="curve")
        _dots[key] = ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS), master=master)
    return _dots[key]


class Toggle:
    """строка панели слоёв: круглый флажок и подпись; color - цветная метка органа слева.
    Щелчок по любому месту строки переключает, а подсвечивается при наведении и нажатии только кружок"""

    def __init__(self, parent, text, on, command, color=None):
        self.command, self.on = command, on
        self.state = "normal"
        self.row = frame(parent)
        self.row.pack(fill="x", pady=(0, px(1)))
        if color:
            tk.Frame(self.row, bg=color, width=px(4)).pack(side="left", fill="y")
        self.dot = label(self.row, None, bd=0)
        self.dot.pack(side="left", padx=(px(8), px(7)), pady=px(3))
        self.text = label(self.row, "", font=(FONT, 9), anchor="w")
        self.text.pack(side="left", fill="x", expand=True)
        self.parts = (self.row, self.dot, self.text) + tuple(self.row.winfo_children())
        for w in self.parts:
            w.config(cursor="hand2")
            w.bind("<Enter>", lambda e: self.show("hover"))
            w.bind("<Leave>", self.leave)
            w.bind("<ButtonPress-1>", lambda e: self.show("press"))
            w.bind("<ButtonRelease-1>", self.release)
        self.set(text, on)

    def inside(self, e):
        """указатель над строкой (над ней или над её частями)"""
        return self.row.winfo_containing(e.x_root, e.y_root) in self.parts

    def leave(self, e):
        if not self.inside(e):
            self.show("normal")

    def release(self, e):
        if self.inside(e):
            self.show("hover")
            self.command()
        else:
            self.show("normal")

    def show(self, state):
        if not self.dot.winfo_exists():
            return
        self.state = state
        self.dot.config(image=dot_image(self.dot, px(16), self.on, state))

    def set(self, text, on):
        """обновить на месте (без пересоздания панели: так щелчок срабатывает сразу)"""
        self.on = on
        style(self.text, fg="text" if on else "muted")
        self.text.config(text=text)
        self.show(self.state)


SHOW_ALL = "_show_all"            # ключи кнопок в заголовках в словаре, который отдаёт fill_layers
ORGANS_ALL = "_organs_all"


def show_all_button(buttons, visible):
    """показать или спрятать кнопку «Показать всё», не пересоздавая панель"""
    b = buttons[SHOW_ALL]
    if visible and not b.winfo_manager():
        b.pack(side="right")
    elif not visible and b.winfo_manager():
        b.pack_forget()


def header(box, title, button, top):
    """заголовок раздела панели с маленькой кнопкой справа; button - (текст, функция)"""
    head = frame(box)
    head.pack(fill="x", pady=(top, px(4)))
    label(head, title.upper(), fg="muted", font=(FONT, 9, "bold"), anchor="w").pack(side="left")
    b = flat_button(head, button[0], button[1])
    b.config(font=(FONT, 8, "bold"), padx=px(6), pady=0)
    return b


def fill_layers(card, title, layers, organs_title, organs, on_layer, on_organ, show_all, organs_all):
    """панель слоёв слева от схемы (только в режиме «Изучать»).
    layers - [(ключ, текст, виден)] слоёв тела; organs - [(ключ, название, цвет, виден)];
    show_all - (текст, функция, видна ли) кнопки «Показать всё» (видна, когда что-то скрыто);
    organs_all - (текст, функция) кнопки «Скрыть все» / «Показать все» в заголовке органов.
    Кнопки - в строках заголовков: низ панели может не поместиться в невысокое окно.
    Возвращает {ключ слоя или органа: Toggle} и кнопки заголовков под SHOW_ALL и ORGANS_ALL."""
    for w in card.winfo_children():
        w.destroy()
    frame(card, "accent", height=3).pack(fill="x")
    box = frame(card)
    box.pack(fill="x", padx=px(12), pady=(0, px(10)))
    buttons = {SHOW_ALL: header(box, title, show_all, px(8))}
    show_all_button(buttons, show_all[2])
    for key, text, on in layers:
        buttons[key] = Toggle(box, text, on, lambda k=key: on_layer(k))
    buttons[ORGANS_ALL] = header(box, organs_title, organs_all, px(8))
    buttons[ORGANS_ALL].pack(side="right")
    for key, text, color, on in organs:
        buttons[key] = Toggle(box, text, on, lambda k=key: on_organ(k), color=color)
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
