"""Сборка программы для Windows без Python: папка dist/OrganismAtlas с OrganismAtlas.exe (PyInstaller).

    pip install -r requirements-dev.txt
    python tools/build_exe.py              # папка dist/OrganismAtlas: быстрый запуск, отдавать архивом
    python tools/build_exe.py --onefile    # один dist/OrganismAtlas.exe: удобно передать, но каждый
                                           # запуск распаковывается во временную папку (на секунды дольше)
    python tools/build_exe.py --console    # с окном консоли: видно ошибки, если программа не запускается

В сборку входят все данные пакета: тексты lang/*.json, вопросы, 3D-модели с подписями авторов и лицензиями
(models/mesh/ATTRIBUTION.md, LICENSE-3D-Slicer.txt - условие лицензий моделей), look.json. Ещё - исходники
рисунка схемы как данные: по ним atlas_cache.version() считает версию кэша, как и при запуске из исходников.
Ещё - готовые схемы нескольких масштабов (папка prebuilt, см. PREBUILT_ZOOMS): первый запуск не ждёт, пока
схема нарисуется. Настройки, прогресс и кэш схемы собранная программа хранит там же, где обычная
(%APPDATA%, %LOCALAPPDATA%).
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from organism_atlas import atlas_cache  # noqa: E402

NAME = "OrganismAtlas"
# готовые схемы в сборке (~1-1.5 МБ каждая): 1.0 - ноутбуки 1366-1600 px, 1.5 - экраны 1920x1080 и 1920x1200.
# Масштаб под окно обычно совпадает с одной из них, а нет - ближайшая показывается растянутой, пока рисуется точная
PREBUILT_ZOOMS = (1.0, 1.5)
PKG = ROOT / "organism_atlas"


def make_icon(path):
    """иконка .exe - та же, что у окна программы (сердце из ui/titlebar.py), во всех размерах Windows"""
    from organism_atlas.ui.titlebar import icon_image
    sizes = (256, 128, 64, 48, 32, 24, 16)
    big = icon_image(256)
    big.save(path, format="ICO", sizes=[(n, n) for n in sizes])
    return path


def source_datas():
    """исходники, по которым считается версия кэша схемы, - как данные (на их местах в пакете)"""
    out = []
    for name in atlas_cache._SOURCES:
        p = PKG / name
        for f in sorted(p.rglob("*.py")) if p.is_dir() else [p]:
            out.append((f, Path("organism_atlas") / f.parent.relative_to(PKG)))
    return out


def make_prebuilt(folder):
    """готовые схемы PREBUILT_ZOOMS в folder - в том же виде, что кэш пользователя (atlas_cache.save)"""
    from organism_atlas.atlas import Atlas
    shutil.rmtree(folder, ignore_errors=True)
    for Z in PREBUILT_ZOOMS:
        print("Схема для сборки, масштаб", Z)
        Atlas.cached(Z, cache_dir=folder)
    return folder


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--onefile", action="store_true", help="один .exe вместо папки")
    ap.add_argument("--console", action="store_true", help="с окном консоли (для поиска ошибок)")
    args = ap.parse_args()
    try:
        import PyInstaller.__main__
    except ImportError:
        sys.exit("Нужен PyInstaller:  pip install -r requirements-dev.txt")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    icon = make_icon(build / (NAME + ".ico"))
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [str(ROOT / "run.py"), "--name", NAME, "--console" if args.console else "--windowed", "--noconfirm", "--clean",
           "--icon", str(icon), "--distpath", str(ROOT / "dist"), "--workpath", str(build),
           "--specpath", str(build), "--collect-data", "organism_atlas",
           "--collect-submodules", "glcontext",           # moderngl выбирает бэкенд OpenGL при запуске
           "--exclude-module", "tkinter"]
    for src, dest in source_datas():
        cmd += ["--add-data", "%s%s%s" % (src, sep, dest.as_posix())]
    prebuilt = make_prebuilt(build / "prebuilt")
    cmd += ["--add-data", "%s%sorganism_atlas/prebuilt" % (prebuilt, sep)]
    if args.onefile:
        cmd.append("--onefile")
    PyInstaller.__main__.run(cmd)
    out = ROOT / "dist" / (NAME + ".exe" if args.onefile else NAME)
    for doc in ("README.md",):                 # описание - рядом с программой
        if not args.onefile:
            shutil.copy(ROOT / doc, out / doc)
    print("Готово:", out)


if __name__ == "__main__":
    main()
