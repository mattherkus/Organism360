"""Главное окно: схема тела, наведение, карточка органа, панель слоёв с поиском органа, режим «Изучать»
с экскурсиями по системам органов и четыре викторины: «Найди орган», «Угадай название», «Угадай по факту»
и «Вперемешку» (со сложностью, таймером, длиной игры, темой и повторением ошибок).
Схема подстраивается под размер окна: пока рисуется чёткая версия, показывается растянутая прежняя."""

import math
import queue
import threading
import tkinter as tk
import traceback

from PIL import Image, ImageTk

from .. import achievements, i18n, progress, settings, theme, tours
from ..atlas import Atlas
from ..body.base import BODY_LAYERS
from ..config import FONT
from ..geometry import H, W
from ..i18n import t
from ..organs import ORGANS, SYSTEMS, by_system, for_body, in_system, other_sex, search
from ..quiz import LENGTHS, LEVELS, MODES, TIMERS, QuizSession, format_time, game_length
from ..theme import C, style
from . import overlay, titlebar
from .achievements import button_text as achievements_text, show_achievements
from .results import show_results_dialog
from .scaling import fit_zoom, pick_zoom, px, set_scale
from .settings_window import refresh_settings, show_settings
from .viewer3d import rerender_all, retranslate_all, set_quality, show_3d
from .widgets import (ORGANS_ALL, ORGANS_LIST, SEARCH, by_color, fill_card, fill_layers, fill_question, fill_setup,
                      fill_start, fill_tour, filter_organs, flat_button, frame, label, rounded_card, set_button_bg,
                      show_all_button)


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
        titlebar.set_icon(root)
        titlebar.paint(root)
        self.mode = "study"                    # study или режим викторины из quiz.MODES
        self.session = None                    # QuizSession во время игры (None - на карточке настройки)
        saved = settings.load()
        # настройки викторины: сложность, таймер и длина переживают перезапуск, тема и набор вопросов - нет
        self.cfg = {"level": settings.get(saved, "quiz_level"), "timer": settings.get(saved, "quiz_timer"),
                    "length": settings.get(saved, "quiz_length"), "topic": None, "set": "all"}
        self.body = settings.get(saved, "body")   # схема тела: female или male (органы малого таза)
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
        self.query = ""                        # строка поиска органа в панели слоёв
        self.spot = None                       # орган, подсвеченный в «Изучать»: найденный поиском или шаг экскурсии
        self.tour = None                       # (экскурсия, шаг): 0 - вступление, 1..n - органы, n + 1 - конец
        self.paused = None                     # экскурсия, прерванная щелчком по органу: к ней можно вернуться
        self.new_achievements, self.streak = [], 0        # для итогов игры: новые достижения и серия дней

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
        self.ach_button = flat_button(top, "", lambda: show_achievements(root))
        self.ach_button.pack(side="right", anchor="n", padx=(12, 0))
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
        self.panel_box, self.panel = rounded_card(body)     # панель слоёв: рамка для grid и место для содержимого
        self.panel_box.grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=(10, 0))
        body.bind("<Configure>", lambda e: self.fit_panel())
        self.want_Z = pick_zoom(root)                       # масштаб схемы под текущий размер окна
        self.cw, self.ch = int(math.ceil(W * self.want_Z)), int(math.ceil(H * self.want_Z))
        # схема по центру «сцены», которая растягивается вместе с окном
        self.stage = frame(body, "bg", width=self.cw, height=self.ch)
        self.stage.grid(row=0, column=1, sticky="nsew", padx=10)
        self.c = style(tk.Canvas(self.stage, width=self.cw, height=self.ch, highlightthickness=0), bg="bg")
        self.c.place(relx=0.5, y=0, anchor="n")
        self.stage.bind("<Configure>", self.on_resize)
        self.card_box, self.card = rounded_card(body)
        self.card_box.grid(row=0, column=2, sticky="new", padx=(10, 0), pady=(10, 0))
        self.c.create_text(self.cw // 2, self.ch // 2, fill=C["muted"], font=(FONT, 12), tags="loading")
        self.set_status(lambda: t("hint"))
        self.set_card(self.empty_card)
        self.retranslate()
        self.fix_window_size()           # схема начнёт рисоваться, когда окно покажется (on_resize)

    def fix_window_size(self):
        """задать размер окна один раз: иначе Tk растягивает его под каждую новую карточку, а за окном
        менялся бы и масштаб схемы. Высота - с запасом под самую высокую карточку (настройка викторины)"""
        root, mode = self.root, self.mode
        # ширина карточки - один раз, по самой широкой (настройка викторины): иначе при смене режима
        # колонка раздвигалась бы, а схема сдвигалась и меняла масштаб
        wide = px(340)
        for self.mode in MODES:
            self.render_setup()
            root.update_idletasks()
            wide = max(wide, self.card.winfo_reqwidth() + 2 * self.card_box.pad)
        self.mode = mode
        self.card_box.fixed = wide
        self.card_box.fit()
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
        titlebar.set_icon(self.root)
        titlebar.paint_all(self.root)
        self.c.itemconfigure("loading", fill=C["muted"])
        if self.atlas:
            self.paint_base()
        rerender_all()
        self.retranslate()

    def set_quality(self, name):
        self.quality = name
        set_quality(name)
        settings.save(quality=name)

    def organs(self):
        """органы на схеме: без органов другого пола"""
        return for_body(self.body)

    def set_body(self, value):
        """женская или мужская схема тела; викторина начинается заново - вопросы могли быть о скрытых органах"""
        if value == self.body:
            return
        self.body = value
        settings.save(body=value)
        self.hidden -= other_sex(value)
        self.tour = self.paused = None                  # маршрут экскурсии зависит от схемы тела
        self.set_spot(None)
        self.render_layers()
        self.apply_view()
        if self.mode != "study":
            self.set_mode(self.mode)
        elif self.card_fn != self.empty_card:
            self.set_card(self.empty_card)

    def set_ui_scale(self, value):
        """масштаб меняет размеры всего окна и схемы, поэтому применяется со следующего запуска"""
        self.pending_scale = value
        settings.save(ui_scale=value)

    def retranslate(self):
        """переписать все тексты на текущем языке, не сбрасывая режим и вопрос викторины"""
        self.root.title(t("app_title"))
        self.title.config(text=t("app_title"))
        self.settings_button.config(text="⚙  " + t("settings_button"))
        self.ach_button.config(text=achievements_text())
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
        fill_start(self.card, t("pick_title"), t("pick_hint"), t("tours_title"),
                   [("➜  " + tours.title(name), lambda n=name: self.start_tour(n)) for name in tours.available(self.body)])

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
        if not first:
            self.drop_photos()                          # подсветка прежнего масштаба больше не подходит
        self.atlas = res
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
        """какие органы скрыты сейчас: в викторине видны все, иначе вопрос мог бы оказаться невидимым;
        органов другого пола нет на схеме всегда"""
        return (self.hidden if self.mode == "study" else set()) | other_sex(self.body)

    def something_hidden(self):
        return bool(self.hidden or len(self.layers) < len(BODY_LAYERS))

    def organs_all_text(self):
        """подпись кнопки в заголовке органов: всё скрыто - вернуть, иначе - скрыть все"""
        return t("layers_show_organs") if self.hidden == set(self.organs()) else t("layers_hide_organs")

    def render_layers(self):
        """построить панель слоёв заново (смена языка)"""
        self.toggles = fill_layers(
            self.panel, t("layers_title"),
            [(name, t("layer_" + name), name in self.layers) for name in BODY_LAYERS],
            t("layers_organs"),
            [(t("system_" + system), [(k, i18n.name(k), ORGANS[k]["color"], k not in self.hidden) for k in keys])
             for system, keys in by_system(by_color(self.organs()))],
            self.toggle_layer, self.toggle_organ,
            show_all=(t("layers_show_all"), self.show_all, self.something_hidden()),
            organs_all=(self.organs_all_text(), self.toggle_all_organs),
            search=(t("search_hint"), self.query, self.on_search, self.on_search_enter, t("search_nothing")))
        if self.query:
            filter_organs(self.toggles, set(search(self.organs(), self.query)))
        self.root.after_idle(self.fit_panel)

    # --- поиск органа
    def on_search(self, text):
        """строка поиска изменилась: в панели остаются подходящие органы; если подходит ровно один,
        он подсвечивается на схеме"""
        self.query = text
        found = search(self.organs(), text)
        filter_organs(self.toggles, set(found))
        self.root.after_idle(self.fit_panel)
        if self.tour is None:
            self.set_spot(found[0] if text.strip() and len(found) == 1 else None)

    def on_search_enter(self, text):
        """Enter в поиске: открыть карточку первого найденного органа и подсветить его (скрытый - показать)"""
        found = search(self.organs(), text)
        if not text.strip() or not found:
            return
        self.pause_tour()
        self.show_info(found[0])
        self.set_spot(found[0])

    def set_spot(self, key):
        """подсветить орган в режиме «Изучать» (None - снять подсветку); скрытый орган сначала показать"""
        self.spot = key
        if key is not None and key in self.hidden:
            self.hidden.discard(key)
            self.apply_view()
        self.show_target()

    def fit_panel(self):
        """список органов в панели - не выше, чем осталось места в окне (остальное листается)"""
        area = getattr(self, "toggles", {}).get(ORGANS_LIST)
        if area is None or not area.winfo_exists():
            return
        body = self.panel_box.master
        if not body.winfo_ismapped():            # окно ещё не показано: его высоты пока нет
            return
        self.root.update_idletasks()
        rest = self.panel_box.winfo_reqheight() - area.winfo_reqheight()       # панель без списка органов
        area.set_limit(body.winfo_height() - px(10) - rest)

    def update_layers(self):
        """после щелчка: обновить флажки и кнопки на месте (пересоздавать панель долго)"""
        show_all_button(self.toggles, self.something_hidden())
        self.toggles[ORGANS_ALL].config(text=self.organs_all_text())
        for name in BODY_LAYERS:
            self.toggles[name].set(t("layer_" + name), name in self.layers)
        for k in self.organs():
            self.toggles[k].set(i18n.name(k), k not in self.hidden)

    def show_panel(self):
        """панель слоёв - только в режиме «Изучать». В викторине её место остаётся пустым,
        чтобы схема не меняла масштаб (и не перерисовывалась) при каждой смене режима"""
        box = self.panel_box
        body = box.master
        if self.mode == "study":
            if not box.winfo_manager():
                box.grid()
                body.columnconfigure(0, minsize=0)
        elif box.winfo_manager():
            body.columnconfigure(0, minsize=body.grid_bbox(0, 0)[2])
            box.grid_remove()

    def toggle_all_organs(self):
        self.hidden = set() if self.hidden == set(self.organs()) else set(self.organs())
        self.apply_view()

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
                self.drop_photos()                      # подсветка зависит от того, кто кого закрывает
                self.on_leave(None)
            self.show_base()
            self.show_target()                          # подсветка органа поиска или экскурсии - заново

    # --- наведение и клики
    def drop_photos(self):
        """забыть картинки подсветки. Сначала отвязать их от элементов холста: иначе удалённая картинка
        остаётся в элементе, и любая следующая его настройка падает с «image ... does not exist»"""
        for item in (self.tg, self.hov, self.fl):
            self.c.itemconfigure(item, image="", state="hidden")
        self.photos.clear()

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

    def kind(self):
        """тип текущего вопроса (quiz.KINDS); без игры - режим: study, find, name, facts или mix"""
        s = self.session
        return s.kind if s is not None and not s.finished else self.mode

    def on_move(self, e):
        if not self.ready() or self.kind() not in ("study", "find"):   # отвечают кнопками; в «Угадай название» подсвечен вопрос
            return
        if self.kind() == "find" and self.session and self.session.level == "hard":
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
        if key is None or self.kind() not in ("study", "find"):
            return
        if self.mode != "study":
            self.answer(key)
            return
        self.pause_tour()                               # щелчок по органу прерывает экскурсию (к ней можно вернуться)
        self.set_spot(None)
        self.show_info(key)

    def show_info(self, key):
        """карточка органа; под ней - возврат к прерванной экскурсии или к списку экскурсий"""
        def back():
            if self.paused is not None:
                return t("tour_resume", title=tours.title(self.paused[0])), self.resume_tour
            return t("tours_back"), self.end_tour
        self.set_card(lambda: fill_card(self.card, key, on_3d=lambda: show_3d(self.root, key), back=back()))

    def update_buttons(self):
        for mode, b in self.mode_buttons.items():
            set_button_bg(b, "accent" if mode == self.mode else "card")
        for code, b in self.lang_buttons.items():
            set_button_bg(b, "accent" if code == i18n.current() else "card")

    def set_mode(self, mode):
        """study - изучение; режим викторины сначала показывает карточку настройки"""
        self.mode = mode
        self.tour = self.paused = None
        if SEARCH in getattr(self, "toggles", {}):
            self.toggles[SEARCH].clear()                # поиск сбрасывается вместе с подсветкой
        self.spot = None
        self.update_buttons()
        self.stop_quiz()
        self.show_panel()
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
        """органы набора вопросов qset (all, missed, due) в выбранной теме"""
        keys = in_system(self.organs(), self.cfg["topic"])
        if qset == "missed":
            return progress.last_missed(self.mode, keys, data)
        if qset == "due":
            return progress.due(self.mode, keys, data)
        return keys

    def topics(self):
        """темы викторины: [(система или None - все органы, сколько органов)]; системы из одного органа
        не предлагаются - по ним нечего спрашивать"""
        out = [(None, len(self.organs()))]
        for name in SYSTEMS:
            n = len(in_system(self.organs(), name))
            if n >= 2:
                out.append((name, n))
        return out

    def render_setup(self):
        data = progress.load()
        topics = self.topics()
        if self.cfg["topic"] not in dict(topics):
            self.cfg["topic"] = None
        counts = {q: len(self.question_keys(q, data)) for q in ("all", "missed", "due")}
        if not counts.get(self.cfg["set"]):
            self.cfg["set"] = "all"
        n = counts[self.cfg["set"]]
        length = self.cfg["length"] if 0 < self.cfg["length"] < n else 0     # длиннее набора - значит «все»
        rows = [
            (t("setup_level"), [(t("level_" + v), v, True) for v in LEVELS], self.cfg["level"],
             lambda v: self.set_cfg("level", v), t("level_hint_" + self.cfg["level"]), False),
            (t("setup_timer"), [(t("timer_sec", sec=v) if v else t("timer_off"), v, True) for v in TIMERS],
             self.cfg["timer"], lambda v: self.set_cfg("timer", v), None, False),
            (t("setup_length"), [(t("length_all", n=n) if not v else str(v), v, not v or v < n) for v in LENGTHS],
             length, lambda v: self.set_cfg("length", v), None, False),
            (t("setup_topic"), [(t("topic_all", n=k) if name is None else
                                 t("topic_system", system=t("system_" + name), n=k), name, True) for name, k in topics],
             self.cfg["topic"], lambda v: self.set_cfg("topic", v), None, 2),
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
        if key in ("level", "timer", "length"):
            settings.save(**{"quiz_" + key: value})
        self.set_card(self.render_setup)

    def start_quiz(self, qset=None):
        """начать игру по текущим настройкам; qset - другой набор вопросов (кнопка «Повторить ошибки»)"""
        qset = qset or self.cfg["set"]
        keys = self.question_keys(qset)
        if not keys:
            qset, keys = "all", self.question_keys("all")
        self.stop_quiz()
        self.qset = qset
        self.session = QuizSession(keys, pool=self.organs(), mode=self.mode, level=self.cfg["level"],
                                   timer=self.cfg["timer"], count=game_length(self.cfg["length"], len(keys)))
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
        if s.kind == "find":
            self.progress, self.choices = fill_question(
                self.card, self.progress_text(), t("find_title", name=i18n.name(s.current)),
                t("find_hint"), fb)
            self.show_target()                          # во «Вперемешку» прячет подсветку прошлого вопроса
            return
        opts = s.options()
        if s.kind == "facts" and s.custom():             # вопрос со своими вариантами ответа
            title, hint = s.prompt(), t("custom_hint", n=len(opts))
        elif s.kind == "facts":
            title, hint = "«%s»" % s.prompt(), t("facts_hint", n=len(opts))
        elif s.kind == "where":
            title, hint = "«%s»" % s.prompt(), t("where_hint", n=len(opts))
        elif s.kind == "system":
            title, hint = t("system_title", name=i18n.name(s.current)), t("custom_hint", n=len(opts))
        elif s.kind == "disease":
            title, hint = "«%s»" % s.prompt(), t("disease_hint", n=len(opts))
        elif s.kind == "latin":
            title, hint = s.prompt(), t("latin_hint", n=len(opts))
        elif s.kind == "truth":
            title, hint = "«%s»" % s.prompt(), t("truth_hint", name=i18n.name(s.current))
        else:
            title, hint = t("name_title"), t("name_hint", n=len(opts))
        self.progress, self.choices = fill_question(
            self.card, self.progress_text(), title, hint, fb, [(k, s.option_label(k)) for k in opts], self.pick)
        for k in self.wrong:
            self.mark_wrong(self.choices[k])
        self.show_target()

    def feedback_text(self, key, organ, _color, i=None):
        """текст отзыва на текущем языке; i - номер вопроса, ответ на который не орган: назвать верный ответ"""
        if i is not None:
            return t(key, answer=self.session.answer_text(i))
        return t(key, name=i18n.name(organ))

    def tick(self):
        """раз в четверть секунды: обновить остаток времени, а когда он вышел - показать ответ и идти дальше"""
        self.timer_job = None
        s = self.session
        if s is None or s.finished or s.remaining() is None:
            return
        if self.next_job is None:                       # во время зелёной паузы после ответа не считаем
            i = s.i if s.answer_text(s.i) is not None else None      # ответ - не орган: назовём его
            key = s.time_up()
            if key:
                self.flash(key, "ok")                   # показать, где был нужный орган
                if s.finished:
                    self.finish(key)
                    return
                self.ask(("time_up", key, "bad") if i is None else ("time_up_answer", key, "bad", i))
                return
            if self.progress is not None and self.progress.winfo_exists():
                self.progress.config(text=self.progress_text())
        self.timer_job = self.root.after(250, self.tick)

    @staticmethod
    def mark_wrong(btn):
        style(btn, bg="wrong_bg", disabledforeground="on_mark")
        btn.config(state="disabled", cursor="")

    def show_target(self):
        """подсветить орган текущего вопроса «Угадай название», а в «Изучать» - орган поиска или экскурсии;
        у вопроса другого типа подсветки нет"""
        if not self.ready():
            return
        s = self.session
        key = s.current if s is not None and s.kind == "name" else self.spot if self.mode == "study" else None
        if key is None or key in self.hidden_now():
            self.c.itemconfigure(self.tg, state="hidden")
            return
        ph, (x, y) = self.photo(key, "target")
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
        self.new_achievements, self.streak = [], 0
        try:
            before = progress.load()
            after = progress.record(s, self.qset)
            self.new_achievements = achievements.new_ones(before, after)
            self.streak = achievements.streak(after)
            self.ach_button.config(text=achievements_text(after))
        except Exception:                               # история - не повод сорвать конец игры
            traceback.print_exc()
        self.set_card(lambda: fill_card(self.card, last))
        self.ask()
        self.root.after(600, self.show_results)

    def on_key(self, e):
        """цифры выбирают вариант ответа, Enter на карточке настройки начинает игру, стрелки листают экскурсию
        (но не тогда, когда поверх открыта панель: настройки, итоги или 3D, и не при наборе в поиске)"""
        if overlay.top(self.root) is not None or isinstance(e.widget, tk.Entry):
            return
        if self.mode == "study":
            if self.tour is not None and e.keysym in ("Right", "Left", "Return", "KP_Enter"):
                self.tour_go(-1 if e.keysym == "Left" else 1)
            return
        if self.session is None:
            if e.keysym in ("Return", "KP_Enter"):
                self.start_quiz()
            return
        if self.kind() != "find" and e.char.isdigit():
            keys = list(self.choices)
            i = int(e.char) - 1
            if 0 <= i < len(keys):
                self.pick(keys[i])

    # --- экскурсии
    def start_tour(self, name):
        self.tour, self.paused = (name, 0), None
        self.set_spot(None)
        self.set_card(self.tour_card)

    def tour_go(self, step):
        """на step шагов вперёд или назад; после последнего органа - карточка «экскурсия пройдена»"""
        name, i = self.tour
        keys = tours.steps(name, self.body)
        i = max(0, min(len(keys) + 1, i + step))
        if i == self.tour[1]:
            return
        self.tour = (name, i)
        self.set_spot(keys[i - 1] if 1 <= i <= len(keys) else None)
        self.set_card(self.tour_card)

    def end_tour(self):
        """закончить экскурсию и показать список экскурсий"""
        self.tour = self.paused = None
        self.set_spot(None)
        self.set_card(self.empty_card)

    def pause_tour(self):
        """прервать экскурсию (щелчок по органу, поиск): запомнить шаг, чтобы к нему вернуться"""
        if self.tour is not None:
            self.paused, self.tour = self.tour, None

    def resume_tour(self):
        """вернуться к прерванной экскурсии на тот же шаг"""
        if self.paused is None:
            return
        name, i = self.tour = self.paused
        self.paused = None
        keys = tours.steps(name, self.body)
        self.set_spot(keys[i - 1] if 1 <= i <= len(keys) else None)
        self.set_card(self.tour_card)

    def tour_quiz(self, topic):
        """викторина «Вперемешку» по системе органов экскурсии: карточка настройки с выбранной темой"""
        self.set_mode("mix")
        self.set_cfg("topic", topic)

    def tour_card(self):
        if self.tour is None:                           # экскурсию закончили, пока карточка перерисовывалась
            self.empty_card()
            return
        name, i = self.tour
        keys = tours.steps(name, self.body)
        n = len(keys)
        back = (t("tour_back"), lambda: self.tour_go(-1), "card", i > 0)
        if i == 0:
            route = " → ".join(i18n.name(k) for k in keys)
            fill_tour(self.card, t("tour_label"), tours.title(name), None,
                      tours.intro(name) + "\n\n" + t("tour_route", route=route), "accent",
                      [(t("tour_start"), lambda: self.tour_go(1), "accent", True)],
                      [(t("tour_exit"), self.end_tour)], t("tour_keys"))
        elif i > n:
            topic = tours.TOPICS.get(name)
            extra = [(t("tour_quiz"), lambda: self.tour_quiz(topic))] if topic in dict(self.topics()) else []
            fill_tour(self.card, tours.title(name), t("tour_done"), None, t("tour_done_text", n=n), "accent",
                      [back, (t("tour_finish"), self.end_tour, "accent", True)], extra)
        else:
            key = keys[i - 1]
            fill_tour(self.card, t("tour_progress", title=tours.title(name), n=i, total=n), i18n.name(key),
                      i18n.subtitle(key), tours.story(name, key), ORGANS[key]["color"],
                      [back, (t("tour_next") if i < n else t("tour_last"), lambda: self.tour_go(1), "accent", True)],
                      [(t("card_3d"), lambda: show_3d(self.root, key)), (t("tour_exit"), self.end_tour)])

    def show_results(self):
        s, mode = self.session, self.mode
        if s is None or self.mode != s.mode:            # пока ждали, пользователь ушёл в другой режим
            return

        def again(qset=None):
            if self.mode == mode:
                self.start_quiz(qset)

        show_results_dialog(self.root, s, on_again=again, on_retry=lambda: again("missed"),
                            due=len(progress.due(mode, self.organs())), streak=self.streak,
                            new=self.new_achievements, on_achievements=lambda: show_achievements(self.root))
