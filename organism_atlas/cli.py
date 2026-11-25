"""Точка входа: python -m organism_atlas."""

import sys


def main():
    try:
        import PIL  # noqa: F401
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as e:
        sys.exit("Нужны библиотеки из requirements.txt (%s):  pip install -r requirements.txt" % e.name)
    from . import i18n, questions, settings, theme
    from .ui.app import App
    from .ui.widgets import font

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Organism 360")
    try:
        i18n.load_all()                 # файлы lang/*.json и questions/*.json правят руками:
        from .organs import ORGANS      # сообщим, в каком файле ошибка
        questions.load_all(known=list(ORGANS))
    except ValueError as e:
        QMessageBox.critical(None, "Организм 360", str(e))
        sys.exit(str(e))
    saved = settings.load()
    i18n.restore(saved.get("lang"), saved.get("previous_lang"))
    theme.set_theme(settings.get(saved, "theme"))
    from .ui.scaling import set_scale
    set_scale(settings.get(saved, "ui_scale"))
    app.setFont(font(10))
    win = App(ui_scale=settings.get(saved, "ui_scale"), quality=settings.get(saved, "quality"))
    win.show()
    # тема «как в системе»: в Windows переключили светлую/тёмную - перекрашиваемся сразу
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: App.main and App.main.follow_system_theme())
    from .ui import onboarding
    onboarding.maybe_start(win)                 # подсказки при первом запуске - когда схема нарисована
    sys.exit(app.exec())
