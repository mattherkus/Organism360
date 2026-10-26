"""Встроенные окна: настройки, итоги викторины и 3D открываются не отдельным окном Windows,
а скруглённой панелью по центру главного окна - поверх схемы и карточек.

У панели заголовок и кнопка ✕, Esc закрывает верхнюю из открытых. Содержимое кладётся в panel.body.
"""

from ..config import FONT
from .scaling import px
from .widgets import RoundCard, flat_button, frame, label


def stack(root):
    """открытые панели окна root, последняя - сверху (список хранится на самом окне)"""
    if not hasattr(root, "panels"):
        root.panels = []
    root.panels[:] = [p for p in root.panels if p.winfo_exists()]
    return root.panels


def top(root):
    """верхняя открытая панель окна root или None"""
    panels = stack(root)
    return panels[-1] if panels else None


def close_top(root):
    p = top(root)
    if p is not None:
        p.destroy()
        return "break"


class Panel(RoundCard):
    """панель по центру окна root; title - текст заголовка (меняется через title())"""

    def __init__(self, root, title=""):
        super().__init__(root, fill="bg", border="border", radius=16)
        head = frame(self.inner, "bg")
        head.pack(fill="x", padx=px(16), pady=(px(10), 0))
        self.head = label(head, title, bg="bg", font=(FONT, 13, "bold"), anchor="w")
        self.head.pack(side="left", fill="x", expand=True)
        close = flat_button(head, "✕", self.destroy, bg="bg", font=(FONT, 11, "bold"))
        close.config(padx=px(9), pady=px(3))
        close.pack(side="right")
        self.body = frame(self.inner, "bg")
        self.body.pack(fill="both", expand=True)
        self.place(relx=0.5, rely=0.5, anchor="center")
        root.bind("<Escape>", lambda e: close_top(root))
        stack(root).append(self)

    def title(self, text=None):
        if text is None:
            return self.head.cget("text")
        self.head.config(text=text)

    def raise_(self):
        """поднять над остальными панелями"""
        self.tk.call("raise", self._w)          # у Canvas lift() поднимает элементы холста, а не сам виджет
        panels = stack(self.master)
        if self in panels:
            panels.remove(self)
        panels.append(self)
