"""Встроенные окна: настройки, итоги викторины, достижения и 3D открываются не отдельным окном,
а скруглённой панелью по центру главного окна - поверх схемы и карточек.

У панели заголовок и кнопка ✕, Esc закрывает верхнюю из открытых (это делает главное окно: keyPressEvent).
Содержимое кладётся в panel.body (столбик). Панель держится по центру и при изменении размера окна.
"""

from PySide6.QtCore import QEvent, QObject, Qt, Signal

from .scaling import px
from .widgets import RoundCard, flat_button, hbox, label, vbox


def stack(host):
    """открытые панели окна host, последняя - сверху (список хранится на самом окне)"""
    if not hasattr(host, "panels"):
        host.panels = []
    return host.panels


def top(host):
    """верхняя открытая панель окна host или None"""
    panels = stack(host)
    return panels[-1] if panels else None


def close_top(host):
    p = top(host)
    if p is not None:
        p.close_panel()
        return True
    return False


class _Center(QObject):
    """держит панель по центру окна, когда то меняет размер"""

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize:
            self.panel.center()
        return False


class Panel(RoundCard):
    """панель по центру окна host; title - текст заголовка (меняется через title())"""

    closed = Signal()

    def __init__(self, host, title=""):
        super().__init__(fill="bg", border="border", radius=16, parent=host)
        self.host = host
        head = hbox()
        self.head = label(title, size=13, bold=True, wrap=False)
        head.addWidget(self.head, 1)
        close = flat_button("✕", self.close_panel, bg="bg", size=11, padx=9, pady=3)
        head.addWidget(close)
        self.lay.addSpacing(px(10))
        row = hbox()
        row.setContentsMargins(px(16), 0, px(16), 0)
        row.addLayout(head)
        self.lay.addLayout(row)
        self.body = vbox()
        self.lay.addLayout(self.body, 1)
        self.is_open = True
        stack(host).append(self)
        host.installEventFilter(_Center(self))
        self.show()
        self.raise_()

    def title(self, text=None):
        if text is None:
            return self.head.text()
        self.head.setText(text)

    def center(self):
        if not self.is_open:
            return
        self.adjustSize()
        h = self.host
        size = self.sizeHint().boundedTo(h.size())
        self.resize(size)
        self.move((h.width() - size.width()) // 2, max(0, (h.height() - size.height()) // 2))

    def showEvent(self, e):
        super().showEvent(e)
        self.center()

    def event(self, e):
        if e.type() == QEvent.LayoutRequest:          # содержимое поменялось: размер и место заново
            r = super().event(e)
            self.center()
            return r
        return super().event(e)

    def raise_panel(self):
        """поднять над остальными панелями"""
        self.raise_()
        panels = stack(self.host)
        if self in panels:
            panels.remove(self)
        panels.append(self)

    def close_panel(self):
        if not self.is_open:
            return
        self.is_open = False
        panels = stack(self.host)
        if self in panels:
            panels.remove(self)
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            close_top(self.host)
            return
        super().keyPressEvent(e)
