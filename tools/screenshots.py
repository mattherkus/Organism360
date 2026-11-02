"""Скриншоты окна и GIF для страницы проекта (docs/, GitHub Pages) и README.

    python tools/screenshots.py               # docs/screenshots/*.png и docs/heart.gif, интерфейс на английском
    python tools/screenshots.py --lang ru     # на русском (файлы с суффиксом -ru)
    python tools/screenshots.py --show        # окно на экране, а не без него (offscreen)

Настройки, прогресс, заметки и кэш схемы - во временной папке: ваши файлы не меняются.
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIZE = (1440, 900)                  # размер окна на снимках (логические пиксели)
GIF_SIZE = (360, 300)               # кадр вращающейся 3D-модели
GIF_FRAMES = 36                     # кадров на оборот
GIF_MS = 70                         # длительность кадра
RU_SHOTS = ("heart", "muscles", "flashcards", "3d")    # на русском - только эти (для README.md)


def wait(cond, seconds=60):
    from PySide6.QtWidgets import QApplication
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def settle(seconds=0.6):
    """дать окну дорисоваться (плавное появление карточки, кадры 3D в фоне)"""
    wait(lambda: False, seconds)


def shot(win, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    win.grab().save(str(path))
    print(path)


def gif(key, path):
    """GIF: 3D-модель органа делает оборот (видеокарта, а без неё - программный рендер)"""
    from organism_atlas.organs import ORGANS
    from organism_atlas.render3d import gpu
    from organism_atlas import theme
    scene = gpu.make_scene(ORGANS[key]["parts"]())
    w, h = GIF_SIZE
    bg = (theme.C["view_bg"], theme.C["view_hi"])
    frames = [scene.render(w, h, -62 + i * 360 / GIF_FRAMES, 14, ss=2, bg=bg).convert("RGB")
              for i in range(GIF_FRAMES)]
    pal = [f.quantize(colors=128, method=2) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=GIF_MS, loop=0, optimize=True)
    print(path, "%d KB" % (path.stat().st_size // 1024))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en", choices=("en", "ru"))
    ap.add_argument("--show", action="store_true", help="окно на экране (иначе - без экрана)")
    ap.add_argument("--out", default=str(ROOT / "docs"))
    a = ap.parse_args()
    if not a.show:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        fonts = Path(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
        if fonts.is_dir():                                        # без экрана Qt сам системные шрифты не находит
            os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))
    tmp = tempfile.mkdtemp(prefix="atlas-shots-")
    os.environ.update({"ORGANISM_ATLAS_SETTINGS": os.path.join(tmp, "settings.json"),
                       "ORGANISM_ATLAS_PROGRESS": os.path.join(tmp, "progress.json"),
                       "ORGANISM_ATLAS_NOTES": os.path.join(tmp, "notes.json"),
                       "ORGANISM_ATLAS_CACHE": os.path.join(tmp, "cache"),
                       "ORGANISM_ATLAS_SPEECH": "off"})

    from PySide6.QtWidgets import QApplication
    from organism_atlas import i18n, notes, questions, settings, theme
    from organism_atlas.organs import ORGANS
    app = QApplication.instance() or QApplication(sys.argv)
    i18n.load_all()
    questions.load_all(known=list(ORGANS))
    i18n.set_base(a.lang)
    settings.save(lang=a.lang, body="female", updates="off", onboarding="done")
    theme.set_theme("paper")
    from organism_atlas.ui.app import App
    from organism_atlas.ui.diseases import show_diseases
    from organism_atlas.ui.overlay import close_top
    from organism_atlas.ui.viewer3d import show_3d
    from organism_atlas.ui.widgets import font
    app.setFont(font(10))
    win = App()
    win.set_body("female")
    win.resize(*SIZE)
    win.show()
    if not wait(win.ready, 180):
        sys.exit("схема не нарисовалась")
    out, suffix = Path(a.out), "" if a.lang == "en" else "-" + a.lang
    d = out / "screenshots"

    def name(n):
        return d / ("%s%s.png" % (n, suffix))

    def shoot(n):
        if a.lang == "en" or n in RU_SHOTS:
            shot(win, name(n))

    settle()
    shoot("start")                                     # стартовая карточка: экскурсии, флеш-карточки

    notes.set_note("heart", "Left ventricle wall ≈ 3× thicker than the right." if a.lang == "en"
                   else "Стенка левого желудочка примерно в 3 раза толще правой.")
    win.show_info("heart")
    win.set_spot("heart")
    settle()
    shoot("heart")                                     # карточка сердца с заметкой

    win.set_spot(None)
    win.layers = {"skin", "muscles", "skeleton"}                 # мышцы и кости в полный рост, органы скрыты
    win.hidden = set(win.organs())
    win.skin_clear = 40
    win.apply_view()
    win.apply_skin()
    win.show_info("tibialis_anterior")
    win.set_spot("tibialis_anterior")
    settle(1.0)
    shoot("muscles")
    win.show_all()
    win.layers = {"skin", "skeleton", "veins", "arteries"}
    win.skin_clear = 0
    win.apply_view()
    win.apply_skin()

    win.tours.start("bile")                                      # шаг экскурсии
    win.tours.go(2)
    settle()
    shoot("tour")
    win.tours.end()

    win.flash.start("latin")                                     # флеш-карточка с открытым ответом
    win.flash.reveal()
    settle()
    shoot("flashcards")
    win.flash.end()

    win.set_mode("name")                                         # вопрос викторины
    win.quiz.start()
    settle()
    shoot("quiz")
    win.set_mode("study")

    show_diseases(win, "gastritis")                              # справочник болезней
    settle()
    shoot("diseases")
    while close_top(win):
        pass

    show_3d(win, "heart")                                        # 3D-просмотр
    settle(4.0)
    shoot("3d")
    while close_top(win):
        pass

    win.set_theme("black")                                       # тёмная тема
    win.show_info("brain")
    win.set_spot("brain")
    settle(1.0)
    shoot("black")
    win.set_theme("paper")

    if a.lang == "en":
        gif("heart", out / "heart.gif")
    win.close()


if __name__ == "__main__":
    main()
