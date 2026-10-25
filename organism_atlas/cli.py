"""Точка входа: python -m organism_atlas."""

import sys
import tkinter as tk


def main():
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("Нужна библиотека Pillow:  pip install pillow")
    from . import i18n, questions, settings, theme
    from .ui.app import App
    from .ui.scaling import enable_dpi_awareness

    enable_dpi_awareness()
    root = tk.Tk()
    try:
        i18n.load_all()                 # файлы lang/*.json и questions/*.json правят руками:
        from .organs import ORGANS      # сообщим, в каком файле ошибка
        questions.load_all(known=list(ORGANS))
    except ValueError as e:
        root.withdraw()
        from tkinter import messagebox
        messagebox.showerror("Атлас организма", str(e))
        sys.exit(str(e))
    saved = settings.load()
    i18n.restore(saved.get("lang"), saved.get("previous_lang"))
    theme.set_theme(settings.get(saved, "theme"))
    App(root, ui_scale=settings.get(saved, "ui_scale"), quality=settings.get(saved, "quality"))
    root.mainloop()
