"""Общие виджеты: скруглённые кнопка и карточка, круглый флажок, карточка органа.
Цвета - роли текущей темы (theme.py). Скругления в Tk нет, поэтому подложки кнопок, карточек и флажков -
сглаженные картинки Pillow на холсте (Canvas), а текст поверх рисует сам Tk."""

import colorsys
import math
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..organs import ORGANS, fact_of_day
from ..theme import C, style
from .scaling import px

# --- картинки-подложки

_images = {}                    # {ключ: PhotoImage}; виджет держит свою картинку сам, поэтому кэш можно чистить
_images_tk = None               # интерпретатор Tk, которому принадлежат картинки из _images


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, w):
    """смешать цвета #rrggbb: w = 0 - a, 1 - b; результат - (r, g, b) 0..255"""
    return tuple(round(x + (y - x) * w) for x, y in zip(_rgb(a), _rgb(b)))


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def cached_image(master, key, draw):
    """PhotoImage из кэша; draw() рисует картинку Pillow, если её ещё нет"""
    global _images_tk
    if _images_tk is not master.tk or len(_images) > 600:     # новое окно Tk или кэш разросся
        _images.clear()
        _images_tk = master.tk
    if key not in _images:
        _images[key] = ImageTk.PhotoImage(draw(), master=master)
    return _images[key]


def rounded_rect(w, h, r, fill, outline=None, width=1, ss=3):
    """сглаженный скруглённый прямоугольник w x h (картинка Pillow с прозрачными углами)"""
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=fill,
                                         outline=outline, width=width * ss if outline else 0)
    return im.resize((w, h), Image.LANCZOS)


class RoundButton(tk.Canvas):
    """плоская кнопка со скруглёнными углами. Понимает те же настройки, что tk.Button, которыми пользуется
    интерфейс: text, command, font, padx, pady, anchor, state, bg/fg, activebackground/activeforeground
    (при нажатии), disabledforeground, highlightbackground (цвет рамки у кнопок цвета карточки) и invoke().
    Под курсором кнопка чуть подсвечивается, при нажатии - цвет activebackground"""

    OWN = ("text", "command", "font", "padx", "pady", "anchor", "state", "bg", "fg", "activebackground",
           "activeforeground", "disabledforeground", "highlightbackground")
    ALIASES = {"background": "bg", "foreground": "fg"}
    IGNORED = ("bd", "borderwidth", "relief", "highlightthickness")

    def __init__(self, parent, text="", command=None, **kw):
        self.o = {"text": text, "command": command, "font": (FONT, 10, "bold"), "padx": px(14), "pady": px(6),
                  "anchor": "center", "state": "normal", "bg": C["card"], "fg": C["text"],
                  "activebackground": C["accent"], "activeforeground": C["on_accent"],
                  "disabledforeground": C["muted"], "highlightbackground": C["border"]}
        self.hover = self.pressed = False
        self.photo = None
        super().__init__(parent, highlightthickness=0, bd=0, cursor="hand2")
        self.img = self.create_image(0, 0, anchor="nw")
        self.txt = self.create_text(0, 0)
        self.bind("<Configure>", lambda e: self.render(e.width, e.height))
        self.bind("<Enter>", lambda e: self.set_mouse(hover=True))
        self.bind("<Leave>", lambda e: self.set_mouse(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self.set_mouse(pressed=True))
        self.bind("<ButtonRelease-1>", self.release)
        self.configure(**kw)

    def configure(self, cnf=None, **kw):
        kw = {self.ALIASES.get(k, k): v for k, v in {**(cnf or {}), **kw}.items() if k not in self.IGNORED}
        own = {k: kw.pop(k) for k in list(kw) if k in self.OWN}
        if kw:
            super().configure(**kw)
        if own:
            self.o.update(own)
            self.measure()
            self.render()

    config = configure

    def cget(self, key):
        key = self.ALIASES.get(key, key)
        return self.o[key] if key in self.o else super().cget(key)

    def invoke(self):
        if self.o["state"] != "disabled" and self.o["command"]:
            self.o["command"]()

    def measure(self):
        """размер по тексту и отступам (как у tk.Button); растянутая pack/grid кнопка станет шире"""
        f = tkfont.Font(root=self, font=self.o["font"])
        super().configure(width=f.measure(self.o["text"]) + 2 * self.o["padx"],
                          height=f.metrics("linespace") + 2 * self.o["pady"])

    def set_mouse(self, hover=None, pressed=None):
        if self.o["state"] == "disabled":
            return
        self.hover = self.hover if hover is None else hover
        self.pressed = self.pressed if pressed is None else pressed
        self.render()

    def release(self, e):
        inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        was = self.pressed
        self.set_mouse(pressed=False)
        if was and inside:
            self.invoke()

    def colors(self):
        """(заливка, рамка или None, цвет текста) по состоянию кнопки"""
        o = self.o
        bg, active = o["bg"], o["activebackground"]
        plain = getattr(self, "_theme_roles", {}).get("bg") in ("card", "bg")    # кнопка цвета фона
        outline = o["highlightbackground"] if plain else None
        if o["state"] == "disabled":
            return bg, outline, o["disabledforeground"]
        if self.pressed:
            return active, None, o["activeforeground"]
        if self.hover:
            return _hex(_mix(bg, active, 0.22) if bg != active else _mix(bg, "#ffffff", 0.16)), outline, o["fg"]
        return bg, outline, o["fg"]

    def render(self, w=None, h=None):
        """нарисовать в размере w x h (по умолчанию - текущем; до первой раскладки - запрошенном)"""
        w = w or (self.winfo_width() if self.winfo_width() > 1 else self.winfo_reqwidth())
        h = h or (self.winfo_height() if self.winfo_height() > 1 else self.winfo_reqheight())
        fill, outline, fg = self.colors()
        r = min(px(8), h // 2)
        bw = max(1, px(1))
        self.photo = cached_image(self, ("btn", w, h, r, fill, outline, bw),
                                  lambda: rounded_rect(w, h, r, fill, outline, bw))
        super().configure(bg=self.master.cget("bg"))                # в углах виден фон родителя
        self.itemconfigure(self.img, image=self.photo)
        left = self.o["anchor"] == "w"
        self.coords(self.txt, self.o["padx"] if left else w / 2, h / 2)
        self.itemconfigure(self.txt, text=self.o["text"], font=self.o["font"], fill=fg,
                           anchor="w" if left else "center")


class RoundCard(tk.Canvas):
    """карточка со скруглёнными углами. Содержимое кладётся в self.inner (обычный Frame цвета fill),
    а холст рисует под ним подложку с рамкой border (роль темы или #rrggbb). inner отодвинут от края ровно
    настолько, чтобы его прямые углы не вылезали за скругление; размер карточки следует за содержимым,
    ширина - ещё и за местом, которое даёт pack/grid. width - постоянная ширина (по содержимому - только высота)"""

    def __init__(self, parent, fill="card", border="border", radius=12, width=None):
        super().__init__(parent, highlightthickness=0, bd=0, width=1, height=1)    # размер задаёт fit()
        self.fill, self.border, self.fixed = fill, border, width
        self.r, self.bw = px(radius), max(1, px(1))
        self.pad = math.ceil(self.r - (self.r - self.bw - 1) / math.sqrt(2))
        self.photos = []
        style(self, bg=getattr(parent, "_theme_roles", {}).get("bg", "bg"))
        self.inner = frame(self, fill)
        # обычное дочернее окно, а не элемент холста: тот не показывается, пока холст мал, и не растёт
        self.inner.place(x=self.pad, y=self.pad, relwidth=1, width=-2 * self.pad)
        self.inner.shell = self
        self.inner.bind("<Configure>", lambda e: self.fit())
        self.bind("<Configure>", lambda e: self.draw(e.width, e.height))

    def configure(self, cnf=None, **kw):
        super().configure(cnf, **kw)
        if "bg" in kw or "background" in kw:                        # смена темы: перерисовать подложку
            self.draw()

    config = configure

    def fit(self):
        """подогнать размер под содержимое (сама вызывается, когда меняется высота содержимого)"""
        w = self.fixed or self.inner.winfo_reqwidth() + 2 * self.pad
        h = self.inner.winfo_reqheight() + 2 * self.pad
        if (w, h) != (self.winfo_reqwidth(), self.winfo_reqheight()):
            super().configure(width=w, height=h)

    def draw(self, w=None, h=None):
        w, h = w or self.winfo_width(), h or self.winfo_height()
        if w < 2 * self.r or h < 2 * self.r:
            return
        fill, border = (C.get(c, c) for c in (self.fill, self.border))
        r, bw = self.r, self.bw

        def corner(i):
            def draw():
                im = rounded_rect(2 * r + 2, 2 * r + 2, r, fill, border, bw)
                x, y = (0 if i in (0, 2) else r + 2), (0 if i in (0, 1) else r + 2)
                return im.crop((x, y, x + r, y + r))
            return cached_image(self, ("corner", r, bw, fill, border, i), draw)

        self.delete("bg")
        self.photos = [corner(i) for i in range(4)]
        for i, (x, y) in enumerate(((0, 0), (w - r, 0), (0, h - r), (w - r, h - r))):
            self.create_image(x, y, image=self.photos[i], anchor="nw", tags="bg")
        for box, color in (((r, 0, w - r, h), fill), ((0, r, w, h - r), fill),
                           ((r, 0, w - r, bw), border), ((r, h - bw, w - r, h), border),
                           ((0, r, bw, h - r), border), ((w - bw, r, w, h - r), border)):
            self.create_rectangle(*box, fill=color, width=0, tags="bg")


class Bar(tk.Canvas):
    """цветная полоска со скруглёнными концами вверху карточки; color - роль темы или #rrggbb"""

    def __init__(self, parent, color):
        super().__init__(parent, highlightthickness=0, bd=0, width=1, height=px(3))      # ширину даёт pack
        self.color = color
        self.photo = None
        style(self, bg=getattr(parent, "_theme_roles", {}).get("bg", "card"))
        self.bind("<Configure>", lambda e: self.draw(e.width))

    def configure(self, cnf=None, **kw):
        super().configure(cnf, **kw)
        if "bg" in kw or "background" in kw:                        # смена темы
            self.draw()

    config = configure

    def draw(self, w=None):
        w, h = w or self.winfo_width(), self.winfo_reqheight()
        if w < 2 * h:
            return
        color = C.get(self.color, self.color)
        self.photo = cached_image(self, ("bar", w, h, color), lambda: rounded_rect(w, h, h // 2, color))
        self.delete("all")
        self.create_image(0, 0, image=self.photo, anchor="nw")


def bar(card, color):
    Bar(card, color).pack(fill="x", padx=px(8), pady=(px(1), 0))


def refit(card):
    """после смены содержимого карточки: подогнать RoundCard, когда Tk пересчитает размеры
    (смена ширины содержимого сама по себе карточке не сообщается)"""
    shell = getattr(card, "shell", None)
    if shell is not None:
        card.after_idle(lambda: shell.winfo_exists() and shell.fit())


def rounded_card(parent, **kw):
    """(карточка RoundCard для pack/grid, её внутренняя рамка для содержимого)"""
    card = RoundCard(parent, **kw)
    return card, card.inner


def flat_button(parent, text, command, bg="card", **kw):
    """bg - роль фона: card для обычной кнопки, accent для главной"""
    b = RoundButton(parent, text, command, **kw)
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
    refit(card)
    wrap = wrap or px(300)
    if empty:
        label(card, empty[0], font=(FONT, 15, "bold"),
              anchor="w").pack(fill="x", padx=px(16), pady=(px(14), px(4)))
        label(card, empty[1], fg="muted", font=(FONT, 11), justify="left",
              anchor="w", wraplength=wrap).pack(fill="x", padx=px(16), pady=(0, px(14)))
        return
    color = ORGANS[key]["color"]
    bar(card, color)                                                 # цветная полоска органа
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
        box, day = rounded_card(card, fill="day_bg", border=color, radius=10)
        box.pack(fill="x", padx=px(16), pady=(px(12), 0))
        label(day, "★  " + t("card_fact_of_day"), fg="day_title", bg="day_bg", font=(FONT, 10, "bold"),
              anchor="w").pack(fill="x", padx=px(10), pady=(px(8), px(2)))
        label(day, fact_of_day(key), bg="day_bg", font=(FONT, 11), justify="left",
              anchor="w", wraplength=wrap - px(22) - 2 * box.pad).pack(fill="x", padx=px(10), pady=(0, px(8)))
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
    refit(card)
    wrap = px(270)
    bar(card, "accent")
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


def dot_image(master, size, on, state):
    """круглый флажок (сглаженный, с прозрачным фоном). state: normal, hover, press.
    Включён - залитый кружок цвета акцента с галочкой, выключен - кольцо. Наведение и нажатие
    меняют только кружок: при наведении он светлее (у кольца появляется заливка), при нажатии темнее.
    master - виджет, в котором картинка будет показана (картинки Tk принадлежат своему окну Tk)"""
    accent, ring, mark = C["accent"], C["muted"], C["on_accent"]

    def draw():
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
            pts = [(S * 0.28, S * 0.52), (S * 0.44, S * 0.68), (S * 0.73, S * 0.36)]      # галочка
            d.line(pts, fill=_rgb(mark), width=round(S * 0.12), joint="curve")
        else:
            outline = ring if state == "normal" else _mix(accent, "#ffffff", 0.22)
            fill = {"normal": None, "hover": _mix(accent, "#000000", 0.45) + (110,),
                    "press": _mix(accent, "#000000", 0.2) + (200,)}[state]
            d.ellipse(box, fill=fill, outline=outline, width=w)
        return im.resize((size, size), Image.LANCZOS)

    return cached_image(master, ("dot", size, on, state, accent, ring, mark), draw)


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
        self.photo = dot_image(self.dot, px(16), self.on, state)        # своя ссылка: кэш могут очистить
        self.dot.config(image=self.photo)

    def set(self, text, on):
        """обновить на месте (без пересоздания панели: так щелчок срабатывает сразу)"""
        self.on = on
        style(self.text, fg="text" if on else "muted")
        self.text.config(text=text)
        self.show(self.state)


def color_family(c):
    """семейство цвета #rrggbb для группировки органов в панели: 0 - розовые, 1 - красные, 2 - тёмно-красные,
    3 - тёплые (персиковые, песочные), 4 - зелёные, 5 - прочие. Возвращает (семейство, светлота)"""
    h, light, _ = colorsys.rgb_to_hls(*(v / 255 for v in _rgb(c)))
    h *= 360
    if h >= 300 or h < 15:                                   # красные тона делятся по светлоте
        fam = 0 if light >= 0.65 else 2 if light < 0.4 else 1
    elif h < 60:
        fam = 3
    elif h < 180:
        fam = 4
    else:
        fam = 5
    return fam, light


def by_color(keys):
    """органы по семействам цвета, внутри семейства - от светлых к тёмным"""
    def order(k):
        fam, light = color_family(ORGANS[k]["color"])
        return fam, -light
    return sorted(keys, key=order)


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
    layers - [(ключ, текст, виден)] слоёв тела; organs - [(ключ, название, цвет, виден)] в порядке by_color:
    между семействами цветов - небольшой промежуток;
    show_all - (текст, функция, видна ли) кнопки «Показать всё» (видна, когда что-то скрыто);
    organs_all - (текст, функция) кнопки «Скрыть все» / «Показать все» в заголовке органов.
    Кнопки - в строках заголовков: низ панели может не поместиться в невысокое окно.
    Возвращает {ключ слоя или органа: Toggle} и кнопки заголовков под SHOW_ALL и ORGANS_ALL."""
    for w in card.winfo_children():
        w.destroy()
    refit(card)
    bar(card, "accent")
    box = frame(card)
    box.pack(fill="x", padx=px(12), pady=(0, px(10)))
    buttons = {SHOW_ALL: header(box, title, show_all, px(8))}
    show_all_button(buttons, show_all[2])
    for key, text, on in layers:
        buttons[key] = Toggle(box, text, on, lambda k=key: on_layer(k))
    buttons[ORGANS_ALL] = header(box, organs_title, organs_all, px(8))
    buttons[ORGANS_ALL].pack(side="right")
    family = None
    for key, text, color, on in organs:
        fam = color_family(color)[0]
        if family is not None and fam != family:                  # промежуток между группами цветов
            frame(box, height=px(7)).pack(fill="x")
        family = fam
        buttons[key] = Toggle(box, text, on, lambda k=key: on_organ(k), color=color)
    return buttons


def fill_setup(card, title, desc, rows, start_text, on_start, history_title, history):
    """карточка настройки викторины перед стартом.
    rows - [(заголовок, [(текст, значение, доступен)], выбранное, on_pick(значение), подсказка, столбиком)];
    history - строки списка «последние игры» (если игр не было - одна строка-заглушка)."""
    for w in card.winfo_children():
        w.destroy()
    refit(card)
    wrap = px(300)
    bar(card, "accent")
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
