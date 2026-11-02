"""«Вертушка» для вопроса «Угадай по 3D»: модель органа медленно поворачивается, названия нет.

Кадры считает программный рендер (render3d.scene.Scene3D) в фоновом потоке - окно не ждёт; первый кадр готов
за доли секунды, остальные появляются следом, и модель начинает вращаться, когда готов полный оборот.
Кадры хранит Frames (по одному набору на вопрос): если карточку перерисовали (смена языка), новая вертушка
продолжает с теми же кадрами."""

import threading

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ..render3d.scene import Scene3D
from ..theme import C
from .scaling import px
from .widgets import color, font, qimage

FRAMES = 16                     # кадров на оборот
FRAME_MS = 90                   # смена кадра
ELEVATION = 16                  # наклон камеры, градусов


class Frames:
    """кадры оборота модели: list картинок Pillow, дополняется потоком"""

    def __init__(self, parts, w, h, start_az=-62.0):
        self.images = []
        self.alive = True
        self.done = False
        bg = (C["view_bg"], C["view_hi"])
        threading.Thread(target=self.work, args=(parts, w, h, start_az, bg), daemon=True).start()

    def work(self, parts, w, h, start_az, bg):
        try:
            scene = Scene3D(parts)
            for i in range(FRAMES):
                if not self.alive:
                    return
                im = scene.render(w, h, start_az + 360.0 * i / FRAMES, ELEVATION, 1.0, ss=1, bg=bg)
                self.images.append(im[0] if isinstance(im, tuple) else im)
        except Exception:                            # вопрос можно решить и без картинки
            import traceback
            traceback.print_exc()
        finally:
            self.done = True

    def stop(self):
        self.alive = False


class Turntable(QWidget):
    """показывает кадры Frames по кругу; пока кадров нет - надпись «модель загружается»"""

    def __init__(self, frames, w, h, loading_text):
        super().__init__()
        self.frames, self.loading = frames, loading_text
        self.setFixedSize(w, h)
        self.i = 0
        self.cache = {}                              # {номер кадра: QImage}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(FRAME_MS)

    def tick(self):
        n = len(self.frames.images)
        if n:
            # крутим, когда готов весь оборот; до тех пор - первый кадр (а не рывки по недосчитанным)
            self.i = (self.i + 1) % n if self.frames.done else 0
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        n = len(self.frames.images)
        if not n:
            p.fillRect(self.rect(), color("view_bg"))
            p.setPen(color("muted"))
            p.setFont(font(9))
            p.drawText(self.rect(), Qt.AlignCenter, self.loading)
            return
        i = self.i % n
        if i not in self.cache:
            self.cache[i] = qimage(self.frames.images[i])
        p.drawImage(r, self.cache[i])


def frame_size(card_width):
    """размер кадра в пикселях экрана для карточки шириной card_width (логических)"""
    w = max(px(200), card_width - px(32))
    return w, round(w * 0.72)
