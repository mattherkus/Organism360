"""Окно 3D-просмотра органа (рендер в фоновом потоке)."""

import queue
import threading
import time
import tkinter as tk
import traceback

from PIL import Image, ImageTk

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..organs import ORGANS
from ..render3d.scene import Scene3D
from ..theme import C, style
from . import titlebar
from .scaling import px
from .widgets import center_on, fill_card, label, rounded_card

_viewer = None                  # единственное окно просмотра: новый орган открывается в нём же

# качество рендера (окно настроек): суперсэмплинг чистого кадра для обычного и большого (HiDPI) окна
# и черновик при вращении в половинном разрешении (None - только на больших окнах)
QUALITY = {
    "low": {"ss": 1, "ss_big": 1, "half_draft": True},
    "medium": {"ss": 3, "ss_big": 2, "half_draft": None},
    "high": {"ss": 4, "ss_big": 3, "half_draft": None},
}
_quality = "medium"


class Viewer3D:
    """Окно с 3D-моделью органа. Рендер программный: сглаженный, с попиксельным освещением.
    При вращении показывается быстрый черновик, после отпускания мыши — чистый кадр."""

    def __init__(self, root, key):
        self.key = None
        self.w, self.h = px(600), px(450)
        self.gen, self.last, self.job = 0, 0.0, None
        self.lx = self.ly = 0
        self.q = queue.Queue()
        self.cv = threading.Condition()
        self.pending, self.alive = None, True
        self.photo = None
        self.error = None                # последняя ошибка рендера (показывается в подписи)
        win = self.win = style(tk.Toplevel(root), bg="bg")
        win.withdraw()                           # показать сразу по центру, а не в углу с прыжком
        titlebar.paint(win)
        win.bind("<Destroy>", self.close)
        threading.Thread(target=self.work, daemon=True).start()
        self.view = label(win, None, bg="bg", bd=0, highlightthickness=0, cursor="fleur")
        self.view.pack(padx=14, pady=(14, 0))
        box, self.card = rounded_card(win)
        box.pack(fill="x", padx=14, pady=(8, 4))
        self.hint = label(win, "", fg="muted", bg="bg", font=(FONT, 9))
        self.hint.pack(pady=(2, 10))
        v = self.view
        v.bind("<ButtonPress-1>", self.press)
        v.bind("<B1-Motion>", self.drag)
        v.bind("<ButtonRelease-1>", lambda e: self.refine())
        v.bind("<MouseWheel>", lambda e: self.zoom_by(1.12 if e.delta > 0 else 1 / 1.12))
        v.bind("<Button-4>", lambda e: self.zoom_by(1.12))
        v.bind("<Button-5>", lambda e: self.zoom_by(1 / 1.12))
        v.bind("<Double-Button-1>", self.reset)
        self.load(key)
        center_on(win, root)
        win.deiconify()
        self.poll()

    def load(self, key):
        """показать в окне другой орган: новая сцена, вид по умолчанию"""
        parts = ORGANS[key]["parts"]()
        self.key = key
        self.anatomical = any(p["k"] == "m" for p in parts)    # сетка BodyParts3D: нужна подпись авторов
        self.scene = Scene3D(parts)
        self.retranslate()
        self.reset()                                     # gen растёт: кадры прежнего органа отбросятся

    def raise_(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def retranslate(self):
        self.win.title(t("viewer_title", name=i18n.name(self.key)))
        fill_card(self.card, self.key, compact=True, wrap=self.w - px(40))
        credit = "\n" + t("viewer_credit") if self.anatomical else ""   # условие лицензии CC BY 4.0
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
        self.photo = ImageTk.PhotoImage(im)
        self.view.configure(image=self.photo)
        if self.error:
            self.error = None
            self.retranslate()

    def show_error(self, ex):
        """рендер упал: кадр остаётся прежним, причина - в подписи под карточкой"""
        self.error = ex
        self.retranslate()

    def draft(self):
        """быстрый кадр при вращении; на больших (HiDPI) окнах - в половинном разрешении:
        на ходу разницы не видно, а считается вчетверо меньше пикселей"""
        half = QUALITY[_quality]["half_draft"]
        k = 2 if (self.w * self.h > 400000 if half is None else half) else 1
        try:
            im = self.scene.render(self.w // k, self.h // k, self.az, self.el, self.zoom, ss=1, step=2,
                                   bg=self.colors())
        except Exception as ex:
            if self.error is None:                       # при вращении не печатаем одно и то же на каждый кадр
                traceback.print_exc()
            self.show_error(ex)
            return
        self.show(im.resize((self.w, self.h), Image.BILINEAR) if k > 1 else im)

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
                    self.q.put((gen, scene.render(w, h, az, el, zoom, ss=1, bg=bg)))
                    if gen != self.gen or self.pending is not None:
                        continue
                self.q.put((gen, scene.render(w, h, az, el, zoom, ss=ss, bg=bg)))
            except Exception as ex:                      # поток не должен умереть: покажем ошибку в окне
                traceback.print_exc()
                self.q.put((gen, ex))

    def close(self, e):
        if e.widget is not self.win:
            return
        global _viewer
        if _viewer is self:
            _viewer = None
        with self.cv:
            self.alive = False
            self.pending = None
            self.cv.notify()

    def poll(self):
        try:
            if not self.win.winfo_exists():
                return
            try:
                while True:
                    gen, im = self.q.get_nowait()
                    if gen != self.gen:
                        continue
                    if isinstance(im, Exception):
                        self.show_error(im)
                    else:
                        self.show(im)
            except queue.Empty:
                pass
            self.win.after(30, self.poll)
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
        now = time.monotonic()
        if now - self.last > 0.03:
            self.last = now
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
