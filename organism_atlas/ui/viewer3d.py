"""Панель 3D-просмотра органа. Рендер - в фоновых потоках, окно никогда не ждёт кадра.

При вращении черновики считают два потока по очереди (numpy на больших операциях отпускает GIL,
поэтому кадры идут внахлёст), каждый берёт самый свежий вид. Разрешение черновика подстраивается так,
чтобы кадр считался за DRAFT_TIME; после отпускания мыши третий поток считает чистый кадр."""

import queue
import threading
import time
import tkinter as tk
import traceback

from PIL import Image, ImageTk

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..models import mesh_credit
from ..organs import ORGANS
from ..render3d.scene import Scene3D
from ..theme import C, style
from .overlay import Panel
from .scaling import px
from .widgets import fill_card, frame, label, rounded_card

_viewer = None                  # единственное окно просмотра: новый орган открывается в нём же

# качество рендера (окно настроек): суперсэмплинг чистого кадра для обычного и большого (HiDPI) окна
# и во сколько раз черновик при вращении может быть меньше кадра (наименьший делитель)
QUALITY = {
    "low": {"ss": 1, "ss_big": 1, "draft_min": 2},
    "medium": {"ss": 3, "ss_big": 2, "draft_min": 1},
    "high": {"ss": 4, "ss_big": 3, "draft_min": 1},
}
_quality = "medium"

DRAFT_TIME = 0.06               # секунд на черновик в одном потоке (двумя потоками - около 25 кадров в секунду)
DRAFT_MAX = 4.0                 # черновик не меньше четверти кадра по стороне, иначе слишком мутно
DRAFT_THREADS = 2


class Viewer3D:
    """Окно с 3D-моделью органа. Рендер программный: сглаженный, с попиксельным освещением.
    При вращении показывается быстрый черновик, после отпускания мыши — чистый кадр."""

    def __init__(self, root, key):
        self.key = None
        self.card_w = px(330)                    # ширина карточки органа справа от кадра
        self.w, self.h = self.view_size(root)
        self.gen, self.shown, self.job = 0, -1, None    # номер вида и номер показанного кадра
        self.lx = self.ly = 0
        self.q = queue.Queue()
        self.cv = threading.Condition()          # слоты запросов чистого кадра и черновика
        self.pending = self.draft_req = None
        self.alive = True
        self.k = max(1.0, (self.w * self.h / 100000) ** 0.5)     # во сколько раз черновик меньше кадра
        self.error = None                # последняя ошибка рендера (показывается в подписи)
        win = self.win = Panel(root)
        win.bind("<Destroy>", self.close)
        threading.Thread(target=self.work, daemon=True).start()
        for _ in range(DRAFT_THREADS):
            threading.Thread(target=self.draft_work, daemon=True).start()
        # кадр слева, карточка органа справа: так панель ниже и помещается в главное окно;
        # до первого кадра - пустая картинка нужного размера, чтобы панель не прыгала
        self.photo = ImageTk.PhotoImage(Image.new("RGB", (self.w, self.h), C["view_bg"]), master=root)
        self.view = label(win.body, None, bg="bg", bd=0, highlightthickness=0, cursor="fleur", image=self.photo)
        self.view.pack(side="left", anchor="n", padx=(px(16), px(12)), pady=(px(10), px(16)))
        side = frame(win.body, "bg")
        side.pack(side="left", anchor="n", fill="y", padx=(0, px(16)), pady=(px(10), px(16)))
        box, self.card = rounded_card(side, width=self.card_w)
        box.pack(fill="x")
        self.hint = label(side, "", fg="muted", bg="bg", font=(FONT, 9), justify="left", anchor="w",
                          wraplength=self.card_w)
        self.hint.pack(fill="x", pady=(px(8), 0))
        v = self.view
        v.bind("<ButtonPress-1>", self.press)
        v.bind("<B1-Motion>", self.drag)
        v.bind("<ButtonRelease-1>", lambda e: self.refine())
        v.bind("<MouseWheel>", lambda e: self.zoom_by(1.12 if e.delta > 0 else 1 / 1.12))
        v.bind("<Button-4>", lambda e: self.zoom_by(1.12))
        v.bind("<Button-5>", lambda e: self.zoom_by(1 / 1.12))
        v.bind("<Double-Button-1>", self.reset)
        self.load(key)
        self.poll()

    def view_size(self, root):
        """размер кадра: 600 x 450 (с учётом масштаба), а в небольшом окне - меньше, чтобы панель влезла"""
        root.update_idletasks()
        w = min(px(600), root.winfo_width() - self.card_w - px(110))
        h = min(px(450), root.winfo_height() - px(120), round(w * 3 / 4))
        h = max(px(180), h)
        return round(h * 4 / 3), h

    def load(self, key):
        """показать в окне другой орган: новая сцена, вид по умолчанию"""
        parts = ORGANS[key]["parts"]()
        self.key = key
        # анатомическая сетка: условие лицензии - подпись авторов её источника
        self.credit = mesh_credit(key) if any(p["k"] == "m" for p in parts) else None
        self.scene = Scene3D(parts)
        self.shown = self.gen                            # недосчитанные черновики прежнего органа не показывать
        self.retranslate()
        self.reset()                                     # gen растёт: кадры прежнего органа отбросятся

    def raise_(self):
        self.win.raise_()

    def retranslate(self):
        self.win.title(t("viewer_title", name=i18n.name(self.key)))
        fill_card(self.card, self.key, compact=True, wrap=self.card_w - px(40))
        credit = "\n" + t({"bp3d": "viewer_credit"}.get(self.credit, "viewer_credit_%s" % self.credit)) \
            if self.credit else ""
        if self.error is not None:
            style(self.hint, fg="bad").config(text=t("viewer_error", error=self.error) + credit)
        else:
            style(self.hint, fg="muted").config(text=t("viewer_hint") + credit)

    # --- отрисовка
    @staticmethod
    def colors():
        """фон кадра по текущей теме; читается в потоке окна и передаётся воркеру готовым"""
        return C["view_bg"], C["view_hi"]

    def show(self, im):
        if (self.photo.width(), self.photo.height()) == im.size:
            self.photo.paste(im)                     # в готовую картинку - втрое быстрее, чем новая
        else:
            self.photo = ImageTk.PhotoImage(im, master=self.view)
            self.view.configure(image=self.photo)
        if self.error:
            self.error = None
            self.retranslate()

    def show_error(self, ex):
        """рендер упал: кадр остаётся прежним, причина - в подписи под карточкой"""
        self.error = ex
        self.retranslate()

    def draft(self):
        """быстрый кадр текущего вида: запрос потокам черновиков (более старый неначатый запрос заменяется)"""
        with self.cv:
            self.draft_req = (self.gen, self.scene, self.w, self.h, self.az, self.el, self.zoom, self.colors(),
                              QUALITY[_quality]["draft_min"])
            self.cv.notify_all()

    def draft_work(self):
        """поток черновиков: кадр в уменьшенном разрешении (делитель self.k подстраивается под DRAFT_TIME),
        растянутый до размера кадра"""
        printed = False
        while True:
            with self.cv:
                while self.draft_req is None and self.alive:
                    self.cv.wait()
                if not self.alive:
                    return
                gen, scene, w, h, az, el, zoom, bg, k_min = self.draft_req
                self.draft_req = None
            k = min(max(self.k, k_min), DRAFT_MAX)
            dw, dh = max(1, round(w / k)), max(1, round(h / k))
            t0 = time.perf_counter()
            try:
                im = scene.render(dw, dh, az, el, zoom, ss=1, step=2, bg=bg)
                if (dw, dh) != (w, h):
                    im = im.resize((w, h), Image.BILINEAR)
            except Exception as ex:
                if not printed:                          # при вращении не печатаем одно и то же на каждый кадр
                    traceback.print_exc()
                    printed = True
                self.q.put((gen, ex, True))
                continue
            # время растёт с числом пикселей, то есть как квадрат стороны: поправка - корень, сглаженная
            dt = time.perf_counter() - t0
            self.k = min(max(0.7 * k + 0.3 * k * (dt / DRAFT_TIME) ** 0.5, 1.0), DRAFT_MAX)
            self.q.put((gen, im, True))

    def refine(self):
        """чистый кадр (суперсэмплинг) считаем в фоновом потоке, чтобы окно не подвисало.
        Запрос кладётся в единственный слот: если воркер занят, более старый
        необработанный запрос просто перезаписывается."""
        self.gen += 1
        w, h = self.w, self.h
        q = QUALITY[_quality]
        ss = q["ss_big"] if w * h > 450000 else q["ss"]
        with self.cv:
            self.pending = (self.gen, self.scene, w, h, self.az, self.el, self.zoom, ss, self.colors())
            self.cv.notify()

    def work(self):
        while True:
            with self.cv:
                while self.pending is None and self.alive:
                    self.cv.wait()
                if not self.alive:
                    return
                gen, scene, w, h, az, el, zoom, ss, bg = self.pending
                self.pending = None
            if gen != self.gen:                          # пока ждали, вид уже сменился
                continue
            try:
                if ss > 1:                               # сначала быстрый чёткий кадр, потом сглаженный
                    self.q.put((gen, scene.render(w, h, az, el, zoom, ss=1, bg=bg), False))
                    if gen != self.gen or self.pending is not None:
                        continue
                self.q.put((gen, scene.render(w, h, az, el, zoom, ss=ss, bg=bg), False))
            except Exception as ex:                      # поток не должен умереть: покажем ошибку в окне
                traceback.print_exc()
                self.q.put((gen, ex, False))

    def close(self, e):
        if e.widget is not self.win:
            return
        global _viewer
        if _viewer is self:
            _viewer = None
        with self.cv:
            self.alive = False
            self.pending = self.draft_req = None
            self.cv.notify_all()

    def poll(self):
        try:
            if not self.win.winfo_exists():
                return
            frame = None
            try:
                while True:
                    gen, im, draft = self.q.get_nowait()
                    # черновик - если он новее показанного (вид при вращении всё равно уже чуть ушёл),
                    # чистый кадр - только для текущего вида
                    if gen > self.shown if draft else gen == self.gen:
                        frame, self.shown = im, gen
            except queue.Empty:
                pass
            if isinstance(frame, Exception):
                self.show_error(frame)
            elif frame is not None:
                self.show(frame)                         # из нескольких готовых показываем только последний
            self.win.after(15, self.poll)
        except tk.TclError:
            pass

    # --- мышь
    def press(self, e):
        self.lx, self.ly = e.x, e.y

    def drag(self, e):
        self.az -= (e.x - self.lx) * 0.5
        self.el = max(-89.0, min(89.0, self.el + (e.y - self.ly) * 0.4))
        self.lx, self.ly = e.x, e.y
        self.gen += 1                                    # отложенный чистый кадр устарел
        self.draft()

    def zoom_by(self, f):
        self.zoom = max(0.5, min(3.0, self.zoom * f))
        self.gen += 1
        self.draft()
        if self.job:
            self.win.after_cancel(self.job)
        self.job = self.win.after(200, self.refine)

    def reset(self, _e=None):
        self.az, self.el, self.zoom = -62.0, 18.0, 1.0
        self.draft()
        self.refine()


def show_3d(root, key):
    """открыть орган в окне просмотра; если окно уже открыто - переиспользовать его"""
    global _viewer
    if _viewer is None:
        _viewer = Viewer3D(root, key)
        return
    if key != _viewer.key:
        _viewer.load(key)
    _viewer.raise_()


def retranslate_all():
    if _viewer is not None:
        _viewer.retranslate()


def set_quality(name):
    """сменить качество рендера; открытое окно сразу перерисовывает кадр"""
    global _quality
    _quality = name if name in QUALITY else "medium"
    rerender_all()


def rerender_all():
    """перерисовать кадр открытого окна (сменились качество или тема)"""
    if _viewer is not None:
        _viewer.draft()
        _viewer.refine()
