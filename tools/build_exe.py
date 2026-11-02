"""Сборка программы без Python (PyInstaller): на Windows - папка dist/OrganismAtlas с OrganismAtlas.exe,
на macOS - dist/OrganismAtlas.app, на Linux - папка dist/OrganismAtlas с исполняемым файлом OrganismAtlas.

    pip install -r requirements-dev.txt
    python tools/build_exe.py              # папка dist/OrganismAtlas: быстрый запуск, отдавать архивом
    python tools/build_exe.py --onefile    # один dist/OrganismAtlas.exe: удобно передать, но каждый
                                           # запуск распаковывается во временную папку (на секунды дольше)
    python tools/build_exe.py --console    # с окном консоли: видно ошибки, если программа не запускается
    python tools/build_exe.py --archive    # и упаковать в dist/OrganismAtlas-<версия>-<система>.zip / .tar.gz

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

from organism_atlas import __version__, atlas_cache  # noqa: E402

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


def platform_tag(platform=sys.platform):
    """имя системы в названии архива"""
    return "windows" if platform == "win32" else "macos" if platform == "darwin" else "linux"


def icon_for(build, platform=sys.platform):
    """иконка для PyInstaller: .ico на Windows, .png на macOS (PyInstaller сам сделает .icns через Pillow);
    на Linux у исполняемого файла иконки нет - None"""
    if platform == "win32":
        return make_icon(build / (NAME + ".ico"))
    if platform == "darwin":
        from organism_atlas.ui.titlebar import icon_image
        path = build / (NAME + ".png")
        icon_image(512).save(path)
        return path
    return None


def archive(out, platform=sys.platform):
    """упаковать сборку для передачи: zip на Windows и macOS (приложение .app - целиком, со ссылками внутри),
    tar.gz на Linux (сохраняет права на запуск). Возвращает путь архива"""
    base = ROOT / "dist" / ("%s-%s-%s" % (NAME, __version__, platform_tag(platform)))
    if platform == "darwin":
        path = base.with_suffix(".zip")
        import subprocess
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(out), str(path)], check=True)
        return path
    fmt = "zip" if platform == "win32" else "gztar"
    return Path(shutil.make_archive(str(base), fmt, root_dir=out.parent, base_dir=out.name))


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
    ap.add_argument("--archive", action="store_true", help="упаковать сборку в zip / tar.gz для передачи")
    args = ap.parse_args()
    try:
        import PyInstaller.__main__
    except ImportError:
        sys.exit("Нужен PyInstaller:  pip install -r requirements-dev.txt")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    icon = icon_for(build)
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [str(ROOT / "run.py"), "--name", NAME, "--console" if args.console else "--windowed", "--noconfirm", "--clean",
           "--distpath", str(ROOT / "dist"), "--workpath", str(build),
           "--specpath", str(build), "--collect-data", "organism_atlas",
           "--collect-submodules", "glcontext",           # moderngl выбирает бэкенд OpenGL при запуске
           "--exclude-module", "tkinter"]
    for src, dest in source_datas():
        cmd += ["--add-data", "%s%s%s" % (src, sep, dest.as_posix())]
    prebuilt = make_prebuilt(build / "prebuilt")
    cmd += ["--add-data", "%s%sorganism_atlas/prebuilt" % (prebuilt, sep)]
    if icon is not None:
        cmd += ["--icon", str(icon)]
    if sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", "io.github.mattherkus.organismatlas"]
    if args.onefile:
        cmd.append("--onefile")
    PyInstaller.__main__.run(cmd)
    if sys.platform == "darwin" and not args.console:
        out = ROOT / "dist" / (NAME + ".app")             # приложение macOS; рядом - папка, она для .app не нужна
    else:
        out = ROOT / "dist" / (NAME + ".exe" if args.onefile and sys.platform == "win32" else NAME)
        if out.is_dir():
            shutil.copy(ROOT / "README.md", out / "README.md")      # описание - рядом с программой
    print("Готово:", out)
    if args.archive:
        print("Архив:", archive(out))


if __name__ == "__main__":
    main()
