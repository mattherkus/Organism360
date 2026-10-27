"""QApplication для тестов окна: без экрана (QT_QPA_PLATFORM=offscreen), одна на все тесты."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


def app():
    return QApplication.instance() or QApplication([])


def wait(cond, timeout=60):
    """крутить цикл событий, пока cond() не станет истинным (или не выйдет время); возвращает cond()"""
    a = app()
    t = time.time()
    while not cond() and time.time() - t < timeout:
        a.processEvents()
        time.sleep(0.005)
    return cond()


def pump(seconds=0.0):
    """обработать события (и таймеры, которые успеют сработать за seconds)"""
    a = app()
    t = time.time()
    while True:
        a.processEvents()
        if time.time() - t >= seconds:
            break
        time.sleep(0.005)
