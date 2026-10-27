"""Сборка программы для Windows без Python: папка dist/OrganismAtlas с OrganismAtlas.exe.

    pip install -r requirements-dev.txt
    python tools/build_exe.py                          # Nuitka: папка dist/OrganismAtlas, быстрый запуск
    python tools/build_exe.py --builder pyinstaller    # прежняя сборка PyInstaller (быстрее собирается)
    python tools/build_exe.py --onefile                # один dist/OrganismAtlas.exe: удобно передать, но каждый
                                                       # запуск распаковывается во временную папку
    python tools/build_exe.py --console                # с окном консоли: видно ошибки, если программа не запускается

После сборки программа запускается с --selftest (окно, 3D-кадр, выход): если в сборку что-то не попало,
сборка падает с отчётом. --no-check - не проверять.

По умолчанию собирает Nuitka: код программы и библиотек на Python переводится в C и компилируется,
поэтому exe - обычная программа, а не распаковщик байт-кода, как у PyInstaller. Что это даёт:
  * запуск быстрее (нет распаковки и импорта сотен .pyc), сборка меньше: Nuitka выкидывает тесты
    и неиспользуемые части numpy, Pillow и Qt (переводы Qt, лишние плагины, tkinter);
  * Защитник Windows реже принимает программу за подозрительную: загрузчик PyInstaller встречается
    во многих вредоносных программах, поэтому его exe часто проверяют дольше или помечают ложно.
Собирается Nuitka дольше (минут 10-20: компилятор C), на Windows нужен Visual Studio Build Tools
(в GitHub Actions он есть) или MinGW, который Nuitka скачает сам.

В сборку входят все данные пакета: тексты lang/*.json, вопросы, 3D-модели с подписями авторов и лицензиями
(models/mesh/ATTRIBUTION.md, LICENSE-3D-Slicer.txt - условие лицензий моделей), look.json. Ещё - хэш
исходников рисунка схемы (atlas_cache.STAMP): по нему считается версия кэша, как и при запуске из исходников.
Настройки, прогресс и кэш схемы собранная программа хранит там же, где обычная (%APPDATA%, %LOCALAPPDATA%).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from organism_atlas import __version__, atlas_cache  # noqa: E402

NAME = "OrganismAtlas"
PKG = ROOT / "organism_atlas"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
EXE = NAME + (".exe" if sys.platform == "win32" else "")
# не нужно программе, а попадает в сборку через импорты библиотек
SKIP = ("tkinter", "unittest", "pydoc", "PyInstaller", "nuitka", "IPython", "matplotlib", "pytest")


def make_icon(path):
    """иконка .exe - та же, что у окна программы (сердце из ui/titlebar.py), во всех размерах Windows"""
    from organism_atlas.ui.titlebar import icon_image
    sizes = (256, 128, 64, 48, 32, 24, 16)
    big = icon_image(256)
    big.save(path, format="ICO", sizes=[(n, n) for n in sizes])
    return path


def write_stamp(path):
    """хэш исходников рисунка схемы - в файл, который ляжет в сборку как organism_atlas/<STAMP>"""
    path.write_text(atlas_cache.sources_digest() + "\n", encoding="ascii")
    return path


def nuitka_command(icon, stamp, console=False, onefile=False):
    cmd = [sys.executable, "-m", "nuitka", str(ROOT / "run.py"),
           "--mode=" + ("onefile" if onefile else "standalone"),
           "--output-dir=" + str(BUILD / "nuitka"), "--output-folder-name=" + NAME, "--output-filename=" + EXE,
           "--enable-plugins=pyside6", "--noinclude-qt-translations",
           "--noinclude-qt-plugins=tls,printsupport,networkinformation",     # сеть и печать программе не нужны
           "--include-package=organism_atlas", "--include-package-data=organism_atlas",
           "--include-package=glcontext",                    # moderngl выбирает бэкенд OpenGL при запуске
           "--include-data-files=%s=organism_atlas/%s" % (stamp, atlas_cache.STAMP),
           "--windows-console-mode=" + ("force" if console else "disable"),
           "--windows-icon-from-ico=" + str(icon),
           "--product-name=Organism Atlas", "--company-name=Organism Atlas",
           "--file-description=Organism Atlas", "--product-version=" + __version__,
           "--file-version=" + __version__,
           "--assume-yes-for-downloads", "--report=" + str(BUILD / "nuitka-report.xml")]
    cmd += ["--nofollow-import-to=" + m for m in SKIP]
    return cmd


def pyinstaller_command(icon, stamp, console=False, onefile=False):
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [str(ROOT / "run.py"), "--name", NAME, "--console" if console else "--windowed", "--noconfirm", "--clean",
           "--icon", str(icon), "--distpath", str(DIST), "--workpath", str(BUILD),
           "--specpath", str(BUILD), "--collect-data", "organism_atlas",
           "--collect-submodules", "glcontext",           # moderngl выбирает бэкенд OpenGL при запуске
           "--add-data", "%s%sorganism_atlas" % (stamp, sep)]
    for m in SKIP:
        cmd += ["--exclude-module", m]
    if onefile:
        cmd.append("--onefile")
    return cmd


def selftest(exe):
    """запустить собранную программу с --selftest: окно открывается, 3D-кадр считается, данные на месте.
    Настройки, прогресс и кэш - во временной папке, чтобы проверка ничего не трогала. Возвращает отчёт"""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "selftest.txt"
        env = dict(os.environ, ORGANISM_ATLAS_SETTINGS=str(Path(tmp) / "settings.json"),
                   ORGANISM_ATLAS_PROGRESS=str(Path(tmp) / "progress.json"), ORGANISM_ATLAS_CACHE=tmp)
        if sys.platform != "win32" and not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
            env.setdefault("QT_QPA_PLATFORM", "offscreen")          # сборка без экрана (сервер, CI)
        r = subprocess.run([str(exe), "--selftest=" + str(report)], env=env, timeout=600)
        text = report.read_text(encoding="utf-8") if report.exists() else "(нет отчёта)"
    if r.returncode != 0:
        sys.exit("Собранная программа не прошла самопроверку (код %d):\n%s" % (r.returncode, text))
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--builder", choices=("nuitka", "pyinstaller"), default="nuitka", help="чем собирать")
    ap.add_argument("--onefile", action="store_true", help="один .exe вместо папки")
    ap.add_argument("--console", action="store_true", help="с окном консоли (для поиска ошибок)")
    ap.add_argument("--no-check", action="store_true", help="не запускать собранную программу для проверки")
    args = ap.parse_args()
    module = {"nuitka": "nuitka", "pyinstaller": "PyInstaller"}[args.builder]
    try:
        __import__(module)
    except ImportError:
        sys.exit("Нужен %s:  pip install -r requirements-dev.txt" % module)
    BUILD.mkdir(exist_ok=True)
    icon = make_icon(BUILD / (NAME + ".ico"))
    stamp = write_stamp(BUILD / atlas_cache.STAMP)
    out = DIST / (EXE if args.onefile else NAME)
    if out.is_dir():
        shutil.rmtree(out)
    elif out.exists():
        out.unlink()
    if args.builder == "pyinstaller":
        import PyInstaller.__main__
        PyInstaller.__main__.run(pyinstaller_command(icon, stamp, args.console, args.onefile))
    else:
        subprocess.run(nuitka_command(icon, stamp, args.console, args.onefile), check=True)
        DIST.mkdir(exist_ok=True)
        built = BUILD / "nuitka" / (EXE if args.onefile else NAME + ".dist")     # Nuitka дописывает .dist
        shutil.move(str(built), str(out))
    if not args.onefile:
        shutil.copy(ROOT / "README.md", out / "README.md")         # описание - рядом с программой
    if not args.no_check:
        print(selftest(out if args.onefile else out / EXE), end="")
    print("Готово:", out)


if __name__ == "__main__":
    main()
