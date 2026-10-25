"""Главное окно: схема тела, наведение, карточка органа, панель слоёв, режим «Изучать» и три викторины:
«Найди орган», «Угадай название» и «Угадай по факту» (со сложностью, таймером и повторением ошибок).
Схема подстраивается под размер окна: пока рисуется чёткая версия, показывается растянутая прежняя."""

import math
import queue
import threading
import tkinter as tk
import traceback

from PIL import Image, ImageTk

from .. import i18n, progress, questions, settings, theme
from ..atlas import Atlas
from ..body.base import BODY_LAYERS
from ..config import FONT
from ..geometry import H, W
from ..i18n import t
from ..organs import ORGANS
from ..quiz import LEVELS, MODES, TIMERS, QuizSession, format_time
from ..theme import C, style
from .results import show_results_dialog
from .scaling import fit_zoom, pick_zoom, px, set_scale
from .settings_window import refresh_settings, show_settings
from .viewer3d import rerender_all, retranslate_all, set_quality, show_3d
from .widgets import (fill_card, fill_layers, fill_question, fill_setup, flat_button, frame, label, set_button_bg,
                      set_toggle, show_all_button)


class App:
    def __init__(self, root, ui_scale=1.0, quality="medium"):
        """ui_scale - множитель масштаба из настроек (действует с запуска), quality - качество 3D"""
        self.root = root
        dpi = root.winfo_fpixels("1i")
        self.ui_scale = self.pending_scale = ui_scale     # pending - выбрано в настройках до перезапуска
        if ui_scale != 1.0:
            root.tk.call("tk", "scaling", dpi / 72.0 * ui_scale)      # шрифты в пунктах тоже крупнее
        set_scale(max(1.0, dpi / 96.0) * ui_scale)
        self.quality = quality
        set_quality(quality)
        style(root, bg="bg")
        self.mode = "study"                    # study или режим викторины из quiz.MODES
        self.session = None                    # QuizSession во время игры (None - на карточке настройки)
        saved = settings.load()
        # настройки викторины: сложность и таймер переживают перезапуск, набор вопросов - нет
        self.cfg = {"level": settings.get(saved, "quiz_level"), "timer": settings.get(saved, "quiz_timer"),
                    "set": "all"}
        self.qset = "all"                      # набор вопросов текущей игры (для истории)
        self.timer_job = None
        self.atlas, self.cur = None, None
        self.photos, self.flash_job, self.next_job = {}, None, None
        self.choices = {}                      # {ключ органа: кнопка} в режиме «Угадай название»
        self.progress = None                   # метка «Вопрос N из M · Ошибок: K» в карточке
        self.feedback = None                   # (ключ текста, орган, цвет[, вопрос]) - отзыв о прошлом ответе
        self.wrong = set()                     # неверно выбранные варианты текущего вопроса
        # что сейчас в карточке и в строке статуса: функции, чтобы перерисовать их на другом языке
        self.card_fn = self.status_fn = None
        self.built = queue.Queue()
        self.building = False                  # в фоне рисуется схема (при запуске или под новый размер окна)
        self.resize_job = None
        self.layers = set(BODY_LAYERS)         # видимые слои тела
        self.hidden = set()                    # органы, скрытые в режиме «Изучать» (в викторине видны все)

        top = self.top = frame(root, "bg")
        top.pack(fill="x", padx=24, pady=(18, 0))
        left = frame(top, "bg")
        self.title = label(left, "", bg="bg", font=(FONT, 20, "bold"))
        self.title.pack(anchor="w")
        # статус - отдельной строкой: длинный текст не должен теснить кнопки режимов
        self.status = label(root, "", bg="bg", font=(FONT, 11, "bold"), anchor="w")
        self.status.pack(fill="x", padx=24, pady=(8, 0))
        self.settings_button = flat_button(top, "", lambda: show_settings(self))
        self.settings_button.pack(side="right", anchor="n", padx=(12, 0))
        langs = frame(top, "bg")                           # переключатель языка, справа от режимов
        langs.pack(side="right", anchor="n", padx=(20, 0))
        self.lang_buttons = {}
        for i, code in enumerate(i18n.available()):
            b = flat_button(langs, i18n.short_name(code), lambda c=code: self.set_lang(c))
            b.config(padx=px(8))
            b.pack(side="left", padx=(4 if i else 0, 0))
            self.lang_buttons[code] = b
        btns = frame(top, "bg")
        btns.pack(side="right", anchor="n")
        self.mode_buttons = {mode: flat_button(btns, "", lambda m=mode: self.set_mode(m))
                             for mode in ("study",) + MODES}
        for i, b in enumerate(self.mode_buttons.values()):
            b.pack(side="left", padx=(8 if i else 0, 0))
        left.pack(side="left")                              # последним: в узком окне теснится заголовок
        root.bind("<Key>", self.on_key)

        body = frame(root, "bg")
        body.pack(fill="both", expand=True, padx=24, pady=10)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)                   # лишнее место при растягивании окна - схеме
        body.columnconfigure(2, minsize=px(340))
        self.panel = style(frame(body, highlightthickness=1), highlightbackground="border")
        self.panel.grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=(10, 0))
        self.want_Z = pick_zoom(root)                       # масштаб схемы под текущий размер окна
        self.cw, self.ch = int(math.ceil(W * self.want_Z)), int(math.ceil(H * self.want_Z))
        # схема по центру «сцены», которая растягивается вместе с окном
        self.stage = frame(body, "bg", width=self.cw, height=self.ch)
        self.stage.grid(row=0, column=1, sticky="nsew", padx=10)
        self.c = style(tk.Canvas(self.stage, width=self.cw, height=self.ch, highlightthickness=0), bg="bg")
        self.c.place(relx=0.5, y=0, anchor="n")
        self.stage.bind("<Configure>", self.on_resize)
        self.card = style(frame(body, highlightthickness=1), highlightbackground="border")
        self.card.grid(row=0, column=2, sticky="new", padx=(10, 0), pady=(10, 0))
        self.c.create_text(self.cw // 2, self.ch // 2, fill=C["muted"], font=(FONT, 12), tags="loading")
        self.set_status(lambda: t("hint"))
        self.set_card(self.empty_card)
        self.retranslate()
        self.fix_window_size()           # схема начнёт рисоваться, когда окно покажется (on_resize)

    def fix_window_size(self):
        """задать размер окна один раз: иначе Tk растягивает его под каждую новую карточку, а за окном
        менялся бы и масштаб схемы. Высота - с запасом под самую высокую карточку (настройка викторины)"""
        root, mode = self.root, self.mode
        self.mode = "facts"
        self.render_setup()
        self.mode = mode
        root.update_idletasks()
        h = root.winfo_reqheight() + px(40)                 # запас на строки истории игр
        self.card_fn()
        root.update_idletasks()
        h = min(max(h, root.winfo_reqheight()), int(0.92 * root.winfo_screenheight()))
        root.geometry("%dx%d" % (root.winfo_reqwidth(), h))
        root.minsize(self.top.winfo_reqwidth() + px(48), px(520))      # уже верхней панели окно не сжать

    # --- язык и настройки
    def set_lang(self, code):
        i18n.set_lang(code)
        settings.save(lang=i18n.current(), previous_lang=i18n.previous())
        self.retranslate()

    def set_theme(self, name):
        """сменить тему на лету: перекрасить все окна, а карточки и тексты перерисовать"""
        theme.set_theme(name)
        settings.save(theme=theme.current())
        theme.repaint(self.root)
        self.c.itemconfigure("loading", fill=C["muted"])
        if self.atlas:
            self.paint_base()
        rerender_all()
        self.retranslate()

    def set_quality(self, name):
        self.quality = name
        set_quality(name)
        settings.save(quality=name)

    def set_ui_scale(self, value):
        """масштаб меняет размеры всего окна и схемы, поэтому применяется со следующего запуска"""
        self.pending_scale = value
        settings.save(ui_scale=value)

    def retranslate(self):
        """переписать все тексты на текущем языке, не сбрасывая режим и вопрос викторины"""
        self.root.title(t("app_title"))
        self.title.config(text=t("app_title"))
        self.settings_button.config(text="⚙  " + t("settings_button"))
        for mode, b in self.mode_buttons.items():
            b.config(text=t("mode_" + mode))
        self.update_buttons()
        self.c.itemconfigure("loading", text=t("loading"))
        self.c.itemconfigure("rescale", text=t("rescaling"))
        self.c.delete("tip")
        self.render_layers()
        self.status.config(text=self.status_fn())
        self.card_fn()
        retranslate_all()
        refresh_settings()

    def set_status(self, fn):
        self.status_fn = fn
        self.status.config(text=fn())

    def set_card(self, fn):
        self.card_fn = fn
        fn()

    def empty_card(self):
        fill_card(self.card, None, empty=(t("pick_title"), t("pick_hint")))

    # --- построение схемы (в отдельном потоке: окно не замирает)
    def ready(self):
        """схема нарисована в масштабе окна: можно наводить, кликать и подсвечивать"""
        return self.atlas is not None and self.atlas.Z == self.want_Z

    def start_build(self):
        """нарисовать схему в масштабе want_Z (из кэша, если есть); одновременно строится одна"""
        self.resize_job = None
        if self.building or self.ready():
            return
        self.building = True
        Z = self.want_Z

        def work():
            try:
                self.built.put((Z, Atlas.cached(Z)))
            except Exception as ex:                     # покажем ошибку в основном потоке
                self.built.put((Z, ex))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(50, self.poll_build)

    def poll_build(self):
        try:
            _Z, res = self.built.get_nowait()
        except queue.Empty:
            self.root.after(50, self.poll_build)
            return
        self.building = False
        if isinstance(res, Exception):
            traceback.print_exception(type(res), res, res.__traceback__)
            if self.atlas is None:
                self.c.itemconfigure("loading", text=t("build_error", error=res))
                self.c.dtag("loading", "loading")         # чтобы смена языка не затёрла ошибку
            return                                      # под новый размер не вышло: остаётся растянутая
        first = self.atlas is None
        self.atlas = res
        self.photos.clear()                             # подсветка прежнего масштаба больше не подходит
        self.atlas.set_layers(self.layers)
        self.atlas.set_hidden(self.hidden_now())
        if first:
            self.c.delete("loading")
            self.base_img = self.c.create_image(0, 0, anchor="nw")
            self.tg = self.c.create_image(0, 0, anchor="nw", state="hidden")      # орган-вопрос
            self.hov = self.c.create_image(0, 0, anchor="nw", state="hidden")
            self.fl = self.c.create_image(0, 0, anchor="nw", state="hidden")
            self.c.bind("<Motion>", self.on_move)
            self.c.bind("<Leave>", self.on_leave)
            self.c.bind("<Button-1>", self.on_click)
        self.paint_base()
        self.c.tag_raise("rescale")
        if not self.ready():                            # пока рисовали, окно снова поменяло размер
            self.start_build()
            return
        self.c.delete("rescale")
        self.show_target()                              # если режим включили, пока схема строилась

    def paint_base(self):
        """схема тела на фоне текущей темы"""
        self.atlas.set_background(C["scene_bg"], C["scene_hi"])
        self.show_base()

    def show_base(self):
        """показать готовую схему; пока чёткая под новый размер не готова - растянуть имеющуюся"""
        im = self.atlas.base
        if not self.ready():
            im = im.resize((self.cw, self.ch), Image.BILINEAR)
        self.base_photo = ImageTk.PhotoImage(im)
        self.c.itemconfigure(self.base_img, image=self.base_photo)

    # --- размер окна
    def set_zoom(self, Z):
        """новый масштаб схемы: холст под него сразу, сама схема - когда дорисуется"""
        self.want_Z = Z
        self.cw, self.ch = int(math.ceil(W * Z)), int(math.ceil(H * Z))
        self.c.config(width=self.cw, height=self.ch)
        self.c.coords("loading", self.cw // 2, self.ch // 2)

    def on_resize(self, e):
        """окно поменяло размер: схема сразу растягивается, а чёткая рисуется, когда размер устоится"""
        Z = fit_zoom(e.width, e.height)
        if self.atlas is None and not self.building:    # окно показалось: рисуем первую схему сразу
            self.set_zoom(Z)
            self.start_build()
            return
        if Z == self.want_Z:
            return
        self.set_zoom(Z)
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(400, self.start_build)
        if self.atlas is None:                          # первая схема ещё рисуется
            return
        self.on_leave(None)
        for item in (self.tg, self.fl):
            self.c.itemconfigure(item, state="hidden")
        self.c.delete("rescale")
        if self.ready():                                # вернули прежний размер, пока рисовалась другая
            self.show_target()
        else:
            self.c.create_text(self.cw // 2, self.ch - px(14), text=t("rescaling"), fill=C["muted"],
                               font=(FONT, 9), tags="rescale")
        self.show_base()

    # --- слои
    def hidden_now(self):
        """какие органы скрыты сейчас: в викторине видны все, иначе вопрос мог бы оказаться невидимым"""
        return self.hidden if self.mode == "study" else ()

    def something_hidden(self):
        return bool(self.hidden or len(self.layers) < len(BODY_LAYERS))

    def render_layers(self):
        """построить панель слоёв заново (смена языка или режима)"""
        self.layers_study = study = self.mode == "study"
        self.toggles = fill_layers(
            self.panel, t("layers_title"),
            [(name, t("layer_" + name), name in self.layers) for name in BODY_LAYERS],
            t("layers_organs"), [(k, i18n.name(k), ORGANS[k]["color"], k not in self.hidden) for k in ORGANS],
            self.toggle_layer, self.toggle_organ, organs_enabled=study,
            note=None if study else t("layers_quiz_note"),
            show_all=(t("layers_show_all"), self.show_all, self.something_hidden()))

    def update_layers(self):
        """после щелчка: обновить флажки на месте (пересоздавать панель долго), а при смене режима - построить"""
        if (self.mode == "study") != self.layers_study:
            self.render_layers()
            return
        show_all_button(self.toggles, self.something_hidden())
        for name in BODY_LAYERS:
            set_toggle(self.toggles[name], t("layer_" + name), name in self.layers)
        for k in ORGANS:
            set_toggle(self.toggles[k], i18n.name(k), k not in self.hidden)

    def toggle_layer(self, name):
        self.layers ^= {name}
        self.apply_view()

    def toggle_organ(self, key):
        self.hidden ^= {key}
        self.apply_view()

    def show_all(self):
        self.layers, self.hidden = set(BODY_LAYERS), set()
        self.apply_view()

    def apply_view(self):
        """применить слои и скрытые органы к схеме и обновить панель"""
        self.update_layers()
        if self.atlas is not None:
            self.root.update_idletasks()                # флажок виден сразу, ещё до перерисовки схемы
            self.atlas.set_layers(self.layers)
            hidden = frozenset(self.hidden_now())
            if hidden != self.atlas.hidden:
                self.atlas.set_hidden(hidden)
                self.photos.clear()                     # подсветка зависит от того, кто кого закрывает
                self.on_leave(None)
            self.show_base()

    # --- наведение и клики
    def photo(self, key, kind):
        if (key, kind) not in self.photos:
            im, pos = self.atlas.overlay(key, kind)
            self.photos[(key, kind)] = (ImageTk.PhotoImage(im), pos)
        return self.photos[(key, kind)]

    def set_hover(self, key):
        if key is None:
            self.c.itemconfigure(self.hov, state="hidden")
            self.c.config(cursor="")
            return
        ph, (x, y) = self.photo(key, "hover")
        self.c.itemconfigure(self.hov, image=ph, state="normal")
        self.c.coords(self.hov, x, y)
        self.c.config(cursor="hand2")

    def on_move(self, e):
        if not self.ready() or self.mode in ("name", "facts"):              # отвечают кнопками; в «Угадай название» подсвечен вопрос
            return
        if self.mode == "find" and self.session and self.session.level == "hard":
            return                                      # на сложном уровне орган под курсором не подсвечивается
        key = self.atlas.organ_at(e.x, e.y)
        if key != self.cur:
            self.cur = key
            self.set_hover(key)
        self.c.delete("tip")
        if key and self.mode == "study":                # в викторине название не показываем
            self.tooltip(e.x, e.y, i18n.name(key))

    def on_leave(self, _e):
        if self.atlas is None:
            return
        self.cur = None
        self.set_hover(None)
        self.c.delete("tip")

    def tooltip(self, x, y, text):
        t = self.c.create_text(x + 14, y + 14, text=text, anchor="nw", fill=C["tip_fg"],
                               font=(FONT, 10, "bold"), tags="tip")
        x1, y1, x2, y2 = self.c.bbox(t)
        shift = max(0, x2 + 6 - self.cw)                # не даём подсказке вылезти за край холста
        if shift:
            self.c.move(t, -shift, 0)
            x1, x2 = x1 - shift, x2 - shift
        r = self.c.create_rectangle(x1 - 5, y1 - 2, x2 + 5, y2 + 2, fill=C["tip_bg"], outline=C["border"], tags="tip")
        self.c.tag_lower(r, t)

    def on_click(self, e):
        if not self.ready():
            return
        key = self.atlas.organ_at(e.x, e.y)
        if key is None or self.mode in ("name", "facts"):
            return
        if self.mode == "find":
            self.answer(key)
            return
        self.show_info(key)

    def show_info(self, key):
        self.set_card(lambda: fill_card(self.card, key, on_3d=lambda: show_3d(self.root, key)))

    def update_buttons(self):
        for mode, b in self.mode_buttons.items():
            set_button_bg(b, "accent" if mode == self.mode else "card")
        for code, b in self.lang_buttons.items():
            set_button_bg(b, "accent" if code == i18n.current() else "card")

    def set_mode(self, mode):
        """study - изучение; режим викторины сначала показывает карточку настройки"""
        self.mode = mode
        self.update_buttons()
        self.stop_quiz()
        self.apply_view()                               # в викторине скрытые органы снова видны
        if mode == "study":
            self.set_status(lambda: t("hint"))
            self.set_card(self.empty_card)
            return
        self.set_status(lambda: t("setup_status"))
        self.set_card(self.render_setup)

    def stop_quiz(self):
        """прервать текущую игру: таймеры, подсветка, кнопки-варианты"""
        for job in ("next_job", "timer_job"):
            if getattr(self, job):
                self.root.after_cancel(getattr(self, job))
                setattr(self, job, None)
        self.session = None
        self.choices = {}
        if self.atlas:
            self.on_leave(None)
            self.c.itemconfigure(self.tg, state="hidden")

    # --- настройка викторины
    def question_keys(self, qset, data=None):
        keys = list(ORGANS)
        if qset == "missed":
            return progress.last_missed(self.mode, keys, data)
        if qset == "due":
            return progress.due(self.mode, keys, data)
        return keys

    def render_setup(self):
        data = progress.load()
        counts = {q: len(self.question_keys(q, data)) for q in ("all", "missed", "due")}
        if not counts.get(self.cfg["set"]):
            self.cfg["set"] = "all"
        rows = [
            (t("setup_level"), [(t("level_" + v), v, True) for v in LEVELS], self.cfg["level"],
             lambda v: self.set_cfg("level", v), t("level_hint_" + self.cfg["level"]), False),
            (t("setup_timer"), [(t("timer_sec", sec=v) if v else t("timer_off"), v, True) for v in TIMERS],
             self.cfg["timer"], lambda v: self.set_cfg("timer", v), None, False),
            (t("setup_set"), [(t("set_" + q, n=counts[q]), q, counts[q] > 0) for q in ("all", "missed", "due")],
             self.cfg["set"], lambda v: self.set_cfg("set", v), t("setup_set_hint"), True),
        ]
        history = [t("history_line", date=self.short_date(r.get("date")), level=t("level_" + r.get("level", "medium")),
                     right=r.get("first_try", 0), total=r.get("total", 0), time=format_time(r.get("seconds", 0)))
                   for r in progress.recent(self.mode, 3, data)
                   if r.get("level") in LEVELS] or [t("history_empty")]
        fill_setup(self.card, t("mode_" + self.mode), t("setup_desc_" + self.mode), rows, t("setup_start"),
                   self.start_quiz, t("setup_history"), history)

    @staticmethod
    def short_date(iso):
        """'2026-10-25T14:03' -> '25.10 14:03'"""
        try:
            d, hm = (iso or "").split("T")
            return "%s.%s %s" % (d[8:10], d[5:7], hm[:5])
        except ValueError:
            return iso or ""

    def set_cfg(self, key, value):
        self.cfg[key] = value
        if key in ("level", "timer"):
            settings.save(**{"quiz_" + key: value})
        self.set_card(self.render_setup)

    def start_quiz(self, qset=None):
        """начать игру по текущим настройкам; qset - другой набор вопросов (кнопка «Повторить ошибки»)"""
        qset = qset or self.cfg["set"]
        keys = self.question_keys(qset)
        if not keys:
            qset, keys = "all", list(ORGANS)
        self.stop_quiz()
        self.qset = qset
        self.session = QuizSession(keys, pool=list(ORGANS), mode=self.mode, level=self.cfg["level"],
                                   timer=self.cfg["timer"])
        self.ask()

    # --- вопросы
    def progress_text(self):
        s = self.session
        text = t("progress", n=s.i + 1, total=s.total, errors=s.errors)
        rem = s.remaining()
        return text + "  ·  " + t("progress_timer", sec=math.ceil(rem)) if rem is not None else text

    def ask(self, feedback=None):
        """показать текущий вопрос в карточке справа;
        feedback - (ключ текста, орган, цвет[, номер вопроса со своими вариантами]): отзыв о прошлом ответе"""
        s = self.session
        if s.finished:
            self.set_status(lambda: t("quiz_done", errors=s.errors, mode=t("mode_" + self.mode)))
            return
        if s.deadline is None:                          # новый вопрос на экране - запускаем его время
            s.start_timer()
            if self.timer_job:
                self.root.after_cancel(self.timer_job)
            self.tick()
        self.feedback, self.wrong = feedback, set()
        self.set_status(lambda: t("quiz_status", mode=t("mode_" + self.mode)))
        self.set_card(self.render_question)

    def render_question(self):
        s = self.session
        fb = self.feedback and (self.feedback_text(*self.feedback), self.feedback[2])
        if self.mode == "find":
            self.progress, self.choices = fill_question(
                self.card, self.progress_text(), t("find_title", name=i18n.name(s.current)),
                t("find_hint"), fb)
            return
        opts = s.options()
        if self.mode == "facts" and s.custom():          # вопрос со своими вариантами ответа
            title, hint = s.prompt(), t("custom_hint", n=len(opts))
        elif self.mode == "facts":
            title, hint = "«%s»" % s.prompt(), t("facts_hint", n=len(opts))
        else:
            title, hint = t("name_title"), t("name_hint", n=len(opts))
        self.progress, self.choices = fill_question(
            self.card, self.progress_text(), title, hint, fb, [(k, s.option_label(k)) for k in opts], self.pick)
        for k in self.wrong:
            self.mark_wrong(self.choices[k])
        self.show_target()

    @staticmethod
    def feedback_text(key, organ, _color, idx=None):
        """текст отзыва на текущем языке; idx - вопрос со своими вариантами: назвать верный ответ"""
        if idx is not None:
            return t(key, answer=questions.answer_text(organ, idx, 0))
        return t(key, name=i18n.name(organ))

    def tick(self):
        """раз в четверть секунды: обновить остаток времени, а когда он вышел - показать ответ и идти дальше"""
        self.timer_job = None
        s = self.session
        if s is None or s.finished or s.remaining() is None:
            return
        if self.next_job is None:                       # во время зелёной паузы после ответа не считаем
            idx = s.prompts.get(s.current) if s.custom() else None
            key = s.time_up()
            if key:
                self.flash(key, "ok")                   # показать, где был нужный орган
                if s.finished:
                    self.finish(key)
                    return
                self.ask(("time_up", key, "bad") if idx is None else ("time_up_answer", key, "bad", idx))
                return
            if self.progress is not None and self.progress.winfo_exists():
                self.progress.config(text=self.progress_text())
        self.timer_job = self.root.after(250, self.tick)

    @staticmethod
    def mark_wrong(btn):
        style(btn, bg="wrong_bg", disabledforeground="on_mark")
        btn.config(state="disabled", cursor="")

    def show_target(self):
        """подсветить орган текущего вопроса (режим «Угадай название»)"""
        if not self.ready() or self.mode != "name" or self.session is None or self.session.finished:
            return
        ph, (x, y) = self.photo(self.session.current, "target")
        self.c.itemconfigure(self.tg, image=ph, state="normal")
        self.c.coords(self.tg, x, y)

    def flash(self, key, kind):
        """на полсекунды закрасить орган зелёным (верно) или красным (ошибка)"""
        if not self.ready():
            return
        ph, (x, y) = self.photo(key, kind)
        self.c.itemconfigure(self.fl, image=ph, state="normal")
        self.c.coords(self.fl, x, y)
        if self.flash_job:
            self.root.after_cancel(self.flash_job)
        self.flash_job = self.root.after(500, self.unflash)

    def unflash(self):
        self.flash_job = None
        self.c.itemconfigure(self.fl, state="hidden")

    def answer(self, key):
        """клик по органу в режиме «Найди орган»"""
        s = self.session
        if s is None or s.finished:
            return
        right = s.answer(key)
        self.flash(key, "ok" if right else "bad")
        if not right:
            self.ask(("answer_wrong", key, "bad"))
            return
        if s.finished:
            self.finish(key)
            return
        self.ask(("answer_right", key, "ok"))

    def pick(self, key):
        """выбран вариант ответа в режимах «Угадай название» и «Угадай по факту»"""
        s = self.session
        if s is None or s.finished or self.next_job or key not in self.choices:
            return
        asked = s.current
        right = s.answer(key)
        btn = self.choices[key]
        if not right:
            self.wrong.add(key)
            self.mark_wrong(btn)
            self.progress.config(text=self.progress_text())
            return
        style(btn, bg="right_bg", fg="on_mark", activebackground="right_bg", activeforeground="on_mark")
        self.flash(asked, "ok")
        self.next_job = self.root.after(700, self.next_question)

    def next_question(self):
        self.next_job = None
        s = self.session
        if s.finished:
            self.finish(s.q[-1])
            return
        self.ask()

    def finish(self, last):
        """игра закончена: сохранить результат, показать карточку последнего органа и итоги"""
        s = self.session
        self.choices = {}
        self.c.itemconfigure(self.tg, state="hidden")
        try:
            progress.record(s, self.qset)
        except Exception:                               # история - не повод сорвать конец игры
            traceback.print_exc()
        self.set_card(lambda: fill_card(self.card, last))
        self.ask()
        self.root.after(600, self.show_results)

    def on_key(self, e):
        """цифры выбирают вариант ответа, Enter на карточке настройки начинает игру"""
        if self.mode == "study":
            return
        if self.session is None:
            if e.keysym in ("Return", "KP_Enter"):
                self.start_quiz()
            return
        if self.mode in ("name", "facts") and e.char.isdigit():
            keys = list(self.choices)
            i = int(e.char) - 1
            if 0 <= i < len(keys):
                self.pick(keys[i])

    def show_results(self):
        s, mode = self.session, self.mode
        if s is None or self.mode != s.mode:            # пока ждали, пользователь ушёл в другой режим
            return

        def again(qset=None):
            if self.mode == mode:
                self.start_quiz(qset)

        show_results_dialog(self.root, s, on_again=again, on_retry=lambda: again("missed"),
                            due=len(progress.due(mode, list(ORGANS))))
