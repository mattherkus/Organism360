"""Главное окно: схема тела, наведение, карточка органа, режим «Изучать» и три викторины:
«Найди орган», «Угадай название» и «Угадай по факту» (со сложностью, таймером и повторением ошибок)."""

import math
import queue
import threading
import tkinter as tk
import traceback

from PIL import ImageTk

from .. import atlas_cache, i18n, progress, questions, settings, theme
from ..atlas import Atlas
from ..config import FONT
from ..geometry import H, W
from ..i18n import t
from ..organs import ORGANS
from ..quiz import LEVELS, MODES, TIMERS, QuizSession, format_time
from ..theme import C, style
from .results import show_results_dialog
from .scaling import pick_zoom, px, set_scale
from .settings_window import refresh_settings, show_settings
from .viewer3d import rerender_all, retranslate_all, set_quality, show_3d
from .widgets import fill_card, fill_question, fill_setup, flat_button, frame, label, set_button_bg


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

        top = frame(root, "bg")
        top.pack(fill="x", padx=24, pady=(18, 0))
        left = frame(top, "bg")
        left.pack(side="left")
        self.title = label(left, "", bg="bg", font=(FONT, 20, "bold"))
        self.title.pack(anchor="w")
        self.status = label(left, "", bg="bg", font=(FONT, 11, "bold"))
        self.status.pack(anchor="w", pady=(8, 0))
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
        root.bind("<Key>", self.on_key)

        body = frame(root, "bg")
        body.pack(fill="both", expand=True, padx=24, pady=10)
        body.columnconfigure(0, weight=1, uniform="s")
        body.columnconfigure(2, weight=1, uniform="s", minsize=px(340))
        self.Z = atlas_cache.zoom_key(pick_zoom(root))      # с той же точностью, что ключ кэша
        self.cw, self.ch = int(math.ceil(W * self.Z)), int(math.ceil(H * self.Z))
        self.c = style(tk.Canvas(body, width=self.cw, height=self.ch, highlightthickness=0), bg="bg")
        self.c.grid(row=0, column=1, padx=10)
        self.card = style(frame(body, highlightthickness=1), highlightbackground="border")
        self.card.grid(row=0, column=2, sticky="new", padx=(10, 0), pady=(10, 0))
        self.c.create_text(self.cw // 2, self.ch // 2, fill=C["muted"], font=(FONT, 12), tags="loading")
        self.set_status(lambda: t("hint"))
        self.set_card(self.empty_card)
        self.retranslate()
        self.start_build()

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
        self.c.delete("tip")
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
    def start_build(self):
        def work():
            try:
                self.built.put(Atlas.cached(self.Z))
            except Exception as ex:                     # покажем ошибку в основном потоке
                self.built.put(ex)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(50, self.poll_build)

    def poll_build(self):
        try:
            res = self.built.get_nowait()
        except queue.Empty:
            self.root.after(50, self.poll_build)
            return
        if isinstance(res, Exception):
            traceback.print_exception(type(res), res, res.__traceback__)
            self.c.itemconfigure("loading", text=t("build_error", error=res))
            self.c.dtag("loading", "loading")             # чтобы смена языка не затёрла ошибку
            return
        self.atlas = res
        self.c.delete("loading")
        self.base_img = self.c.create_image(0, 0, anchor="nw")
        self.paint_base()
        self.tg = self.c.create_image(0, 0, anchor="nw", state="hidden")      # орган-вопрос
        self.hov = self.c.create_image(0, 0, anchor="nw", state="hidden")
        self.fl = self.c.create_image(0, 0, anchor="nw", state="hidden")
        self.c.bind("<Motion>", self.on_move)
        self.c.bind("<Leave>", self.on_leave)
        self.c.bind("<Button-1>", self.on_click)
        self.show_target()                              # если режим включили, пока схема строилась

    def paint_base(self):
        """схема тела на фоне текущей темы"""
        self.base_photo = ImageTk.PhotoImage(self.atlas.set_background(C["scene_bg"], C["scene_hi"]))
        self.c.itemconfigure(self.base_img, image=self.base_photo)

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
        if self.mode in ("name", "facts"):              # отвечают кнопками; в «Угадай название» подсвечен вопрос
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
        if self.atlas is None or self.mode != "name" or self.session is None or self.session.finished:
            return
        ph, (x, y) = self.photo(self.session.current, "target")
        self.c.itemconfigure(self.tg, image=ph, state="normal")
        self.c.coords(self.tg, x, y)

    def flash(self, key, kind):
        """на полсекунды закрасить орган зелёным (верно) или красным (ошибка)"""
        if self.atlas is None:
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
