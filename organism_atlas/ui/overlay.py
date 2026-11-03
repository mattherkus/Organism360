"""Встроенные страницы и панели внутри главного окна (не отдельные окна).

Справочник болезней, статистика и настройки - страницы-вкладки (page=True): страница занимает окно под строкой
вкладок (host.page_rect) во всю ширину, без рамки и кнопки ✕, содержимое - столбиком посередине, над ним
заголовок. Открыта одна страница: новая заменяет прежнюю.
Достижения, горячие клавиши и 3D - скруглённые панели по центру окна поверх схемы (или поверх страницы - её они
не закрывают), с заголовком и кнопкой ✕; открыта одна такая панель.
Esc закрывает верхнюю (это делает главное окно: keyPressEvent). Содержимое кладётся в panel.body (столбик).
Страница и панель держат своё место и при изменении размера окна. Когда что-то открывается или закрывается,
окно узнаёт об этом (host.panels_changed): его вкладки показывают, какая страница открыта.
"""

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QPainter

from ..i18n import t
from .scaling import px
from .widgets import RoundCard, alive, clear, color, flat_button, hbox, label, vbox


def stack(host):
    """открытые панели окна host, последняя - сверху (список хранится на самом окне)"""
    if not hasattr(host, "panels"):
        host.panels = []
    return host.panels


def top(host):
    """верхняя открытая панель окна host или None"""
    panels = stack(host)
    return panels[-1] if panels else None


def changed(host):
    """сообщить окну, что набор открытых панелей поменялся"""
    notify = getattr(host, "panels_changed", None)
    if notify is not None and alive(host):
        notify()


def close_top(host):
    p = top(host)
    if p is not None:
        p.close_panel()
        return True
    return False


def close_all(host):
    """закрыть все страницы и панели окна"""
    while close_top(host):
        pass


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
    """панель по центру окна host или (page) страница-вкладка; title - текст заголовка (меняется через title());
    kind - какая это страница (diseases, stats, settings: у окна для неё есть вкладка) или None"""

    closed = Signal()
    kind = None
    title_key = None                             # ключ заголовка: такая панель пересобирается при смене языка

    def __init__(self, host, title="", kind=None, page=False):
        super().__init__(fill="bg", border="border", radius=16, parent=host)
        self.host = host
        self.page = page
        if kind:
            self.kind = kind
        if page:                                 # столбик посередине страницы: заголовок и содержимое
            self.lay.setContentsMargins(px(24), px(2), px(24), px(16))
            outer = hbox()
            outer.addStretch(1)
            column = vbox()
            outer.addLayout(column)
            outer.addStretch(1)
            self.head = label(title, size=18, bold=True, wrap=False, serif=True)
            column.addWidget(self.head)
            self.body = vbox()
            column.addLayout(self.body, 1)
            self.lay.addLayout(outer, 1)
        else:
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
        for other in list(stack(host)):          # страница заменяет всё, панель поверх страницу не закрывает
            if page or not other.page:
                other.close_panel()
        stack(host).append(self)
        host.installEventFilter(_Center(self))
        self.show()
        self.raise_()
        changed(host)

    @classmethod
    def open(cls, host):
        """открыть панель; если такая уже сверху - просто вернуть её (вторая не открывается)"""
        p = top(host)
        return p if isinstance(p, cls) else cls(host)

    def build(self):
        """содержимое панели в self.body (панели с title_key)"""

    def retranslate(self):
        """смена языка: заголовок и содержимое заново (панели со своим refresh обновляются им)"""
        if self.title_key is None or not self.is_open:
            return
        self.title(t(self.title_key))
        clear(self.body)
        self.build()

    def title(self, text=None):
        if text is None:
            return self.head.text()
        self.head.setText(text)

    def center(self):
        if not self.is_open:
            return
        if self.page:                            # страница - на своё место в окне
            place = getattr(self.host, "page_rect", None)
            self.setGeometry(place() if place else self.host.rect())
            return
        self.adjustSize()
        h = self.host
        size = self.sizeHint().boundedTo(h.size())
        self.resize(size)
        self.move((h.width() - size.width()) // 2, max(0, (h.height() - size.height()) // 2))

    def showEvent(self, e):
        super().showEvent(e)
        self.center()

    def paintEvent(self, e):
        if self.page:                            # страница - часть окна: его фон, без рамки
            QPainter(self).fillRect(self.rect(), color("bg"))
            return
        super().paintEvent(e)

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
        changed(self.host)

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
        changed(self.host)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            close_top(self.host)
            return
        super().keyPressEvent(e)
