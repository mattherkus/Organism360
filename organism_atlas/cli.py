"""Точка входа: python -m organism_atlas.

    --selftest[=файл]   самопроверка собранной программы: открыть окно, посчитать 3D-кадр и выйти.
                        Код выхода 0 - всё работает; отчёт (время, рендер 3D, ошибка) - в файл или в stdout.
                        Так tools/build_exe.py и GitHub Actions проверяют, что в сборку попало всё нужное.
"""

import sys
import time
import traceback

T0 = time.perf_counter()


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
    app.setApplicationName("Organism Atlas")
    try:
        i18n.load_all()                 # файлы lang/*.json и questions/*.json правят руками:
        from .organs import ORGANS      # сообщим, в каком файле ошибка
        questions.load_all(known=list(ORGANS))
    except ValueError as e:
        QMessageBox.critical(None, "Атлас организма", str(e))
        sys.exit(str(e))
    saved = settings.load()
    i18n.restore(saved.get("lang"), saved.get("previous_lang"))
    theme.set_theme(settings.get(saved, "theme"))
    from .ui.scaling import set_scale
    set_scale(settings.get(saved, "ui_scale"))
    app.setFont(font(10))
    win = App(ui_scale=settings.get(saved, "ui_scale"), quality=settings.get(saved, "quality"))
    win.show()
    test = [a for a in sys.argv[1:] if a.split("=")[0] == "--selftest"]
    if test:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: selftest(app, win, test[0].partition("=")[2] or None))
    sys.exit(app.exec())


def selftest(app, win, path):
    """окно уже на экране: посчитать маленький 3D-кадр (сетка из данных пакета, OpenGL или numpy),
    записать отчёт и выйти с кодом 0, а при ошибке - с кодом 1"""
    lines, code = ["window %.2f s" % (time.perf_counter() - T0)], 0
    try:
        from .organs import ORGANS
        from .render3d import gpu
        app.processEvents()
        t = time.perf_counter()
        im = gpu.make_scene(ORGANS["heart"]["parts"]()).render(160, 120, -62, 18, ss=2)
        lines.append("3d %.2f s, %s, %dx%d" % (time.perf_counter() - t, gpu.info() or "numpy: %s" % gpu._failed, *im.size))
        lines.append("total %.2f s" % (time.perf_counter() - T0))
    except Exception:
        lines.append(traceback.format_exc())
        code = 1
    text = "\n".join(lines) + "\n"
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif sys.stdout is not None:
        sys.stdout.write(text)
    win.close()
    app.exit(code)
