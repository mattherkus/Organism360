"""Панель 3D-просмотра органа.

Кадр считает видеокарта (render3d/gpu.py): при вращении сразу показывается полный кадр с тенями и деталями,
а после отпускания мыши - он же со сглаживанием (суперсэмплинг из настроек качества). Если кадр
считается дольше DRAFT_TIME (нет видеокарты, программный OpenGL), при вращении разрешение кадра
подстраивается так же, как у программного рендера.

Без OpenGL кадр считает Scene3D в фоновых потоках, окно никогда не ждёт кадра: черновики при вращении
считают два потока по очереди (numpy на больших операциях отпускает GIL, поэтому кадры идут внахлёст),
каждый берёт самый свежий вид; после отпускания мыши третий поток считает чистый кадр.

У анатомической модели из нескольких частей (групп сетки) под кадром - список частей: их можно скрывать,
под курсором показывается название части, а «Найди часть» - маленькая викторина: назвали часть - щёлкни по ней.
Названия частей - раздел parts в lang/*.json; часть без названия в список не попадает."""

import math
import queue
import random
import threading
import time
import traceback

from PIL import Image
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QWidget

from .. import i18n
from ..i18n import t
from ..models import mesh_credit
from ..organs import ORGANS
from ..render3d import gpu
from ..theme import C
from .diseases import show_diseases
from .overlay import Panel
from .scaling import px
from .cards import fill_card
from .layers_panel import Toggle
from .widgets import (clear, color, flat_button, font, hbox, label, put, qimage, rounded_card, set_button_bg, set_fg,
                      vbox)

_viewer = None                  # единственная панель просмотра: новый орган открывается в ней же

# качество рендера (окно настроек): суперсэмплинг чистого кадра для обычного и большого (HiDPI) окна
# и во сколько раз черновик при вращении может быть меньше кадра (наименьший делитель)
QUALITY = {
    "low": {"ss": 1, "ss_big": 1, "draft_min": 2},
    "medium": {"ss": 3, "ss_big": 2, "draft_min": 1},
    "high": {"ss": 4, "ss_big": 3, "draft_min": 1},
}
_quality = "medium"

DRAFT_TIME = 0.06               # секунд на черновик (программно - в одном потоке из двух)
DRAFT_MAX = 4.0                 # черновик не меньше четверти кадра по стороне, иначе слишком мутно
DRAFT_THREADS = 2
CLICK_MOVE = 4                  # сдвиг мыши (в пикселях), после которого нажатие - уже вращение, а не щелчок


class Frame(QWidget):
    """кадр модели: картинка в пикселях экрана и подсказка с названием части под курсором"""

    def __init__(self, viewer, w, h):
        super().__init__()
        self.viewer = viewer
        self.setFixedSize(w, h)
        self.image = None
        self.tip = None                     # (x, y, текст)
        self.setMouseTracking(True)
        self.setCursor(Qt.SizeAllCursor)

    def set_image(self, im):
        q = qimage(im)
        q.setDevicePixelRatio(im.width / self.width())
        self.image = q
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.image is None:
            p.fillRect(self.rect(), color("view_bg"))
        else:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRectF(self.rect()), self.image)
        if self.tip:
            x, y, text = self.tip
            p.setFont(font(10, bold=True))
            fm = p.fontMetrics()
            w, h = fm.horizontalAdvance(text) + 2 * px(5), fm.height() + 2 * px(1)
            x = min(x + px(14), max(0, self.width() - w))
            y = y + px(14)
            p.fillRect(x, y, w, h, color("tip_bg"))
            p.setPen(color("tip_fg"))
            p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, text)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.viewer.press(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.viewer.drag(e.position())
        else:
            self.viewer.hover(e.position())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.viewer.release(e.position())

    def mouseDoubleClickEvent(self, e):
        self.viewer.reset()

    def leaveEvent(self, e):
        self.show_tip(None)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.viewer.zoom_by(1.12 if d > 0 else 1 / 1.12)

    def show_tip(self, tip):
        if tip != self.tip:
            self.tip = tip
            self.update()


class Viewer3D:
    """Панель с 3D-моделью органа: кадр слева, карточка органа справа, части модели под кадром."""

    def __init__(self, host, key):
        self.host = host
        self.key = None
        self.card_w = px(330)                    # ширина карточки органа справа от кадра
        self.w, self.h = self.view_size(host)
        self.dpr = host.devicePixelRatioF()
        self.gen, self.shown = 0, -1             # номер вида и номер показанного кадра
        self.lx = self.ly = 0
        self.az, self.el, self.zoom = -62.0, 18.0, 1.0
        self.k = max(1.0, (self.w * self.h * self.dpr ** 2 / 100000) ** 0.5)  # во сколько раз черновик меньше
        self.k_gpu = 1.0                         # то же для видеокарты: обычно 1 - черновик в полном размере
        self.error = None                        # последняя ошибка рендера (показывается в подписи)
        self.ids = None                          # карта частей показанного кадра (номер части в пикселе, -1 - фон)
        self.hidden = frozenset()                # скрытые части модели
        self.names = []                          # [(номер части, название, цвет)] - части со своим названием
        self.part_toggles = {}                   # {номер части: Toggle} в списке под кадром
        self.quiz = None                         # викторина «Найди часть»: {order, i, right, slipped, note}
        self.press_at, self.moved = None, False
        # программный рендер: очереди и потоки (запускаются, только если видеокарты нет)
        self.q = queue.Queue()
        self.cv = threading.Condition()
        self.pending = self.draft_req = None
        self.alive = True
        self.threads = False
        # видеокарта: кадр считается в потоке окна, вид при вращении - в слоте (кадры не копятся)
        self.gpu_draft = self.gpu_full = False
        self.gpu_timer = QTimer()
        self.gpu_timer.setSingleShot(True)
        self.gpu_timer.timeout.connect(self.gpu_frame)
        self.zoom_timer = QTimer()
        self.zoom_timer.setSingleShot(True)
        self.zoom_timer.timeout.connect(self.refine)
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll)

        win = self.win = Panel(host)
        win.closed.connect(self.close)
        row = hbox(spacing=12)
        left = vbox()
        self.view = Frame(self, self.w, self.h)
        left.addWidget(self.view)
        self.parts_card = rounded_card(width=self.w)        # части модели под кадром
        left.addSpacing(px(10))
        left.addWidget(self.parts_card)
        left.addStretch(1)
        row.addLayout(left)
        side = vbox()
        self.card = rounded_card(width=self.card_w)
        side.addWidget(self.card)
        self.hint = label("", "muted", 9)
        self.hint.setFixedWidth(self.card_w)
        side.addSpacing(px(8))
        side.addWidget(self.hint)
        side.addStretch(1)
        row.addLayout(side)
        put(win.body, row, top=10, bottom=16)
        self.load(key)

    def view_size(self, host):
        """размер кадра: 600 x 450 (с учётом масштаба), а в небольшом окне - меньше, чтобы панель влезла
        (под кадром место для списка частей модели)"""
        w = min(px(600), host.width() - self.card_w - px(110))
        h = min(px(450), host.height() - px(230), round(w * 3 / 4))
        h = max(px(180), h)
        return round(h * 4 / 3), h

    def load(self, key):
        """показать в панели другой орган: новая сцена, вид по умолчанию"""
        parts = ORGANS[key]["parts"]()
        self.key = key
        # анатомическая сетка: условие лицензии - подпись авторов её источника
        self.credit = mesh_credit(key) if any(p["k"] == "m" for p in parts) else None
        self.scene = gpu.make_scene(parts)
        self.gpu = isinstance(self.scene, gpu.GpuScene)
        if not self.gpu:
            self.start_threads()
        self.groups = [(p.get("group"), p["color"]) for p in parts]
        self.hidden, self.quiz, self.ids = frozenset(), None, None
        self.shown = self.gen                            # недосчитанные черновики прежнего органа не показывать
        self.retranslate()
        self.reset()                                     # gen растёт: кадры прежнего органа отбросятся

    def raise_(self):
        self.win.raise_panel()

    def open_link(self, key):
        """ссылка в карточке: орган - его модель здесь же, болезнь - статья справочника поверх"""
        if key in ORGANS:
            self.load(key)
        else:
            show_diseases(self.host, key)

    def retranslate(self):
        self.win.title(t("viewer_title", name=i18n.name(self.key)))
        fill_card(self.card, self.key, compact=True, on_link=self.open_link)
        credit = "\n" + t({"bp3d": "viewer_credit"}.get(self.credit, "viewer_credit_%s" % self.credit)) \
            if self.credit else ""
        if self.error is not None:
            set_fg(self.hint, "bad").setText(t("viewer_error", error=self.error) + credit)
        else:
            set_fg(self.hint, "muted").setText(t("viewer_hint") + credit)
        self.fill_parts()

    # --- части модели
    def fill_parts(self):
        """построить список частей под кадром (новый орган, другой язык); у модели меньше чем из двух
        названных частей его нет. Дальше щелчки только обновляют его на месте (refresh_parts)"""
        names = [(i, i18n.part(self.key, g), c) for i, (g, c) in enumerate(self.groups) if g]
        self.names = [(i, n, c) for i, n, c in names if n]
        lay = self.parts_card.lay
        clear(lay)
        self.part_toggles = {}
        if len(self.names) < 2:
            self.parts_card.hide()
            return
        self.parts_card.show()
        head = hbox()
        head.addWidget(label(t("parts_title").upper(), "muted", 9, bold=True, wrap=False))
        head.addStretch(1)
        self.quiz_button = flat_button("", self.toggle_quiz, size=9, padx=10, pady=3)
        head.addWidget(self.quiz_button)
        put(lay, head, top=6, x=(16, 12))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(px(6))
        grid.setVerticalSpacing(px(1))
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for n, (i, name, c) in enumerate(self.names):
            self.part_toggles[i] = Toggle(name, i not in self.hidden, lambda i=i: self.toggle_part(i), c=c)
            grid.addWidget(self.part_toggles[i], n // 2, n % 2)
        put(lay, grid, top=2, x=12)
        # высота - всегда две строки: подпись меняется после каждого ответа, а панель не должна прыгать
        self.note = label("", "muted", 10, bold=True)
        self.note.setFixedHeight(2 * self.note.fontMetrics().lineSpacing() + px(2))
        put(lay, self.note, top=6, bottom=10)
        self.refresh_parts()

    def refresh_parts(self):
        """обновить флажки частей, кнопку викторины и подпись на месте"""
        if not self.part_toggles:
            return
        for i, toggle in self.part_toggles.items():
            toggle.set(self.name_of(i), i not in self.hidden)
        playing = self.quiz is not None and not self.quiz_done()
        text = t("parts_quiz") if self.quiz is None else t("parts_quiz_stop") if playing else t("parts_quiz_again")
        self.quiz_button.setText(text)
        set_button_bg(self.quiz_button, "card" if playing else "accent")
        set_fg(self.note, "accent_fg" if self.quiz else "muted").setText(self.quiz_text())

    def name_of(self, i):
        return dict((j, n) for j, n, _ in self.names).get(i)

    def part_at(self, x, y):
        """номер части под точкой (x, y) кадра по карте частей показанного кадра; None - фон или не знаем"""
        ids = self.ids
        if ids is None or not (0 <= x < self.w and 0 <= y < self.h):
            return None
        ih, iw = ids.shape
        i = int(ids[min(ih - 1, int(y * ih / self.h)), min(iw - 1, int(x * iw / self.w))])
        return i if i >= 0 else None

    def hover(self, pos):
        """название части под курсором - подсказкой рядом с ним (во время викторины - нет: это подсказка ответа)"""
        x, y = pos.x(), pos.y()
        name = self.name_of(self.part_at(x, y)) if len(self.names) >= 2 and self.quiz is None else None
        self.view.show_tip(None if name is None else (int(x), int(y), name))

    def toggle_part(self, i):
        self.hidden = self.hidden ^ {i}
        self.refresh_parts()
        self.draft()
        self.refine()

    # --- викторина «Найди часть»
    def quiz_done(self):
        return self.quiz is not None and self.quiz["i"] >= len(self.quiz["order"])

    def quiz_text(self):
        q = self.quiz
        if q is None:
            return t("parts_hint")
        if q["i"] >= len(q["order"]):
            return t("parts_done", right=q["right"], total=len(q["order"]))
        ask = t("parts_find", name=self.name_of(q["order"][q["i"]]), n=q["i"] + 1, total=len(q["order"]))
        return (q["note"] + "\n" if q["note"] else "") + ask

    def toggle_quiz(self):
        """начать викторину (все части снова видны, порядок случайный), закончить её или, если она
        пройдена, начать заново"""
        if self.quiz is not None and not self.quiz_done():
            self.quiz = None
        else:
            order = [i for i, _, _ in self.names]
            random.shuffle(order)
            self.quiz = {"order": order, "i": 0, "right": 0, "slipped": False, "note": ""}
            if self.hidden:
                self.hidden = frozenset()
                self.draft()
                self.refine()
        self.view.show_tip(None)
        self.refresh_parts()

    def quiz_click(self, x, y):
        q = self.quiz
        if q is None or q["i"] >= len(q["order"]):
            return
        part = self.part_at(x, y)
        if part is None or self.name_of(part) is None:
            return
        if part == q["order"][q["i"]]:
            q["right"] += not q["slipped"]
            q["i"] += 1
            q["slipped"] = False
            q["note"] = t("parts_right")
        else:
            q["slipped"] = True
            q["note"] = t("parts_wrong", name=self.name_of(part))
        self.refresh_parts()

    # --- отрисовка
    @staticmethod
    def colors():
        """фон кадра по текущей теме; читается в потоке окна и передаётся воркеру готовым"""
        return C["view_bg"], C["view_hi"]

    def pixels(self):
        """размер кадра в пикселях экрана (на экране с масштабом 150 % - в полтора раза больше логического)"""
        return max(1, round(self.w * self.dpr)), max(1, round(self.h * self.dpr))

    def show(self, im):
        self.view.set_image(im)
        if self.error:
            self.error = None
            self.retranslate()

    def show_error(self, ex):
        """рендер упал: кадр остаётся прежним, причина - в подписи под карточкой"""
        self.error = ex
        self.retranslate()

    def draft(self):
        """быстрый кадр текущего вида"""
        if self.gpu:
            self.gpu_draft = True
            if not self.gpu_timer.isActive():
                self.gpu_timer.start(0)              # события мыши копятся, кадр - один на все
            return
        w, h = self.pixels()
        with self.cv:
            self.draft_req = (self.gen, self.scene, w, h, self.az, self.el, self.zoom, self.colors(),
                              QUALITY[_quality]["draft_min"], self.hidden)
            self.cv.notify_all()

    def refine(self):
        """чистый кадр (суперсэмплинг)"""
        self.gen += 1
        w, h = self.pixels()
        q = QUALITY[_quality]
        ss = q["ss_big"] if w * h > 450000 else q["ss"]
        if self.gpu:
            self.gpu_full = True
            if not self.gpu_timer.isActive():
                self.gpu_timer.start(0)
            return
        with self.cv:
            self.pending = (self.gen, self.scene, w, h, self.az, self.el, self.zoom, ss, self.colors(), self.hidden)
            self.cv.notify()

    def gpu_frame(self):
        """кадр на видеокарте (в потоке окна). Черновик - полный кадр, только без суперсэмплинга; если он
        считается дольше DRAFT_TIME (программный OpenGL), разрешение уменьшается, а при вращении убираются
        тени и мелкие детали, как у программного черновика"""
        if not self.alive:
            return
        full, self.gpu_full = self.gpu_full, False
        self.gpu_draft = False
        w, h = self.pixels()
        try:
            if full:
                q = QUALITY[_quality]
                ss = q["ss_big"] if w * h > 450000 else q["ss"]
                im, ids = self.scene.render(w, h, self.az, self.el, self.zoom, ss=ss, bg=self.colors(),
                                            hidden=self.hidden, ids=True)
            else:
                k = min(max(self.k_gpu, QUALITY[_quality]["draft_min"] if self.k_gpu > 1 else 1), DRAFT_MAX)
                k = math.ceil(k * 4) / 4                 # ступеньками: у видеокарты меньше разных размеров кадра
                dw, dh = max(1, round(w / k)), max(1, round(h / k))
                t0 = time.perf_counter()
                im, ids = self.scene.render(dw, dh, self.az, self.el, self.zoom, ss=1, bg=self.colors(),
                                            hidden=self.hidden, ids=True, step=1 if k <= 1 else 2)
                dt = time.perf_counter() - t0
                self.k_gpu = min(max(0.7 * k + 0.3 * k * (dt / DRAFT_TIME) ** 0.5, 1.0), DRAFT_MAX)
                if (dw, dh) != (w, h):
                    im = im.resize((w, h), Image.BILINEAR)
        except Exception as ex:
            traceback.print_exc()
            self.show_error(ex)
            return
        self.ids = ids
        self.show(im)
        if self.scene.gpu_error and self.scene.gpu_error != "другой поток":   # видеокарта отказала: дальше в потоках
            self.gpu = False
            self.start_threads()

    # --- программный рендер в потоках
    def start_threads(self):
        if self.threads:
            return
        self.threads = True
        threading.Thread(target=self.work, daemon=True).start()
        for _ in range(DRAFT_THREADS):
            threading.Thread(target=self.draft_work, daemon=True).start()
        self.poll_timer.start(15)

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
                gen, scene, w, h, az, el, zoom, bg, k_min, hidden = self.draft_req
                self.draft_req = None
            k = min(max(self.k, k_min), DRAFT_MAX)
            dw, dh = max(1, round(w / k)), max(1, round(h / k))
            t0 = time.perf_counter()
            try:
                im, ids = scene.render(dw, dh, az, el, zoom, ss=1, step=2, bg=bg, hidden=hidden, ids=True)
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
            self.q.put((gen, (im, ids), True))

    def work(self):
        while True:
            with self.cv:
                while self.pending is None and self.alive:
                    self.cv.wait()
                if not self.alive:
                    return
                gen, scene, w, h, az, el, zoom, ss, bg, hidden = self.pending
                self.pending = None
            if gen != self.gen:                          # пока ждали, вид уже сменился
                continue
            try:
                if ss > 1:                               # сначала быстрый чёткий кадр, потом сглаженный
                    self.q.put((gen, scene.render(w, h, az, el, zoom, ss=1, bg=bg, hidden=hidden, ids=True), False))
                    if gen != self.gen or self.pending is not None:
                        continue
                self.q.put((gen, scene.render(w, h, az, el, zoom, ss=ss, bg=bg, hidden=hidden, ids=True), False))
            except Exception as ex:                      # поток не должен умереть: покажем ошибку в окне
                traceback.print_exc()
                self.q.put((gen, ex, False))

    def poll(self):
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
            im, self.ids = frame
            self.show(im)                                # из нескольких готовых показываем только последний

    def close(self):
        global _viewer
        if _viewer is self:
            _viewer = None
        self.gpu_timer.stop()
        self.zoom_timer.stop()
        self.poll_timer.stop()
        with self.cv:
            self.alive = False
            self.pending = self.draft_req = None
            self.cv.notify_all()

    # --- мышь
    def press(self, pos):
        self.lx, self.ly = pos.x(), pos.y()
        self.press_at, self.moved = (pos.x(), pos.y()), False
        self.view.show_tip(None)

    def release(self, pos):
        """отпустили кнопку: после вращения - чистый кадр, а щелчок на месте - ответ викторины «Найди часть»"""
        if self.moved:
            self.refine()
        elif self.quiz is not None:
            self.quiz_click(pos.x(), pos.y())

    def drag(self, pos):
        x, y = pos.x(), pos.y()
        if not self.moved:
            x0, y0 = self.press_at or (x, y)
            if abs(x - x0) + abs(y - y0) < CLICK_MOVE:   # дрожание руки при щелчке - не вращение
                return
            self.moved = True
        self.az -= (x - self.lx) * 0.5
        self.el = max(-89.0, min(89.0, self.el + (y - self.ly) * 0.4))
        self.lx, self.ly = x, y
        self.gen += 1                                    # отложенный чистый кадр устарел
        self.gpu_full = False
        self.draft()

    def zoom_by(self, f):
        self.zoom = max(0.5, min(3.0, self.zoom * f))
        self.gen += 1
        self.gpu_full = False
        self.draft()
        self.zoom_timer.start(200)

    def reset(self):
        self.az, self.el, self.zoom = -62.0, 18.0, 1.0
        self.draft()
        self.refine()


def show_3d(host, key):
    """открыть орган в панели просмотра; если она уже открыта - переиспользовать её"""
    global _viewer
    if _viewer is None:
        _viewer = Viewer3D(host, key)
        return _viewer
    if key != _viewer.key:
        _viewer.load(key)
    _viewer.raise_()
    return _viewer


def retranslate_all():
    if _viewer is not None:
        _viewer.retranslate()


def set_quality(name):
    """сменить качество рендера; открытая панель сразу перерисовывает кадр"""
    global _quality
    _quality = name if name in QUALITY else "medium"
    rerender_all()


def rerender_all():
    """перерисовать кадр открытой панели (сменились качество или тема)"""
    if _viewer is not None:
        _viewer.draft()
        _viewer.refine()
