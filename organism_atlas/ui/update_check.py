"""Новая версия на GitHub (updates.py): раз в день спросить в фоновом потоке, и если выпуск новее есть,
показать в верхней панели кнопку «Новая версия» - щелчок открывает страницу выпуска."""

import queue
import threading

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from .. import updates
from ..i18n import t
from .widgets import flat_button

POLL_MS = 500


class UpdateCheck:
    def __init__(self, app):
        self.app = app
        self.info = None                       # {"version", "url"} выпуска новее или None
        self.queue = None                      # ответ фонового потока; None - ещё не спрашивали
        self.timer = QTimer(app)
        self.timer.timeout.connect(self.poll)
        self.button = flat_button("", self.open, bg="accent", padx=10)      # видна, только когда есть новее
        self.button.hide()

    def check(self):
        """раз в день спросить GitHub о новой версии - в фоновом потоке; ответ заберёт poll"""
        if not updates.due():
            return
        result = queue.Queue()
        threading.Thread(target=lambda: result.put(updates.check()), daemon=True).start()
        self.queue = result
        self.timer.start(POLL_MS)

    def poll(self):
        try:
            info = self.queue.get_nowait()
        except queue.Empty:
            return
        self.timer.stop()
        if info:
            self.info = info
            self.button.show()
            self.retranslate()

    def open(self):
        if self.info:
            QDesktopServices.openUrl(QUrl(self.info["url"]))

    def retranslate(self):
        if self.info:
            self.button.setText(t("update_button", version=self.info["version"]))
            self.button.setToolTip(t("update_hint"))
