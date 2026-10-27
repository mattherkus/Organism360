"""Сборка программы для Windows без Python: папка dist/OrganismAtlas с OrganismAtlas.exe (PyInstaller).

    pip install -r requirements-dev.txt
    python tools/build_exe.py              # папка dist/OrganismAtlas: быстрый запуск, отдавать архивом
    python tools/build_exe.py --onefile    # один dist/OrganismAtlas.exe: удобно передать, но каждый
                                           # запуск распаковывается во временную папку (на секунды дольше)
    python tools/build_exe.py --console    # с окном консоли: видно ошибки, если программа не запускается

После сборки программа запускается с --selftest (окно, 3D-кадр, выход): если в сборку что-то не попало,
сборка падает с отчётом. --no-check - не проверять.

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

from organism_atlas import atlas_cache  # noqa: E402

NAME = "OrganismAtlas"
PKG = ROOT / "organism_atlas"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
EXE = NAME + (".exe" if sys.platform == "win32" else "")
# не нужно программе, а попадает в сборку через импорты библиотек
SKIP = ("tkinter", "unittest", "pydoc", "PyInstaller", "IPython", "matplotlib", "pytest")


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
    ap.add_argument("--onefile", action="store_true", help="один .exe вместо папки")
    ap.add_argument("--console", action="store_true", help="с окном консоли (для поиска ошибок)")
    ap.add_argument("--no-check", action="store_true", help="не запускать собранную программу для проверки")
    args = ap.parse_args()
    try:
        import PyInstaller.__main__
    except ImportError:
        sys.exit("Нужен PyInstaller:  pip install -r requirements-dev.txt")
    BUILD.mkdir(exist_ok=True)
    icon = make_icon(BUILD / (NAME + ".ico"))
    stamp = write_stamp(BUILD / atlas_cache.STAMP)
    out = DIST / (EXE if args.onefile else NAME)
    if out.is_dir():
        shutil.rmtree(out)
    elif out.exists():
        out.unlink()
    PyInstaller.__main__.run(pyinstaller_command(icon, stamp, args.console, args.onefile))
    if not args.onefile:
        shutil.copy(ROOT / "README.md", out / "README.md")         # описание - рядом с программой
    if not args.no_check:
        print(selftest(out if args.onefile else out / EXE), end="")
    print("Готово:", out)


if __name__ == "__main__":
    main()
