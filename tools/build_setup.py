"""Сборка установщика для Windows: dist/OrganismAtlas-Setup-<версия>.exe (Inno Setup, скрипт tools/setup.iss).

    pip install -r requirements-dev.txt
    python tools/build_setup.py               # собрать программу (build_exe.py) и установщик
    python tools/build_setup.py --skip-exe    # только установщик из уже собранной dist/OrganismAtlas

Нужен Inno Setup 6.3+ (https://jrsoftware.org/isdl.php или  winget install JRSoftware.InnoSetup):
ISCC.exe ищется в PATH и в обычных папках установки, либо задаётся переменной окружения ISCC.
Версия установщика - organism_atlas.__version__.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from organism_atlas import __version__  # noqa: E402

NAME = "OrganismAtlas"
SCRIPT = ROOT / "tools" / "setup.iss"


def find_iscc():
    """путь к ISCC.exe или None"""
    custom = os.environ.get("ISCC")
    if custom:
        return custom
    found = shutil.which("iscc")
    if found:
        return found
    roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(str(Path(local) / "Programs"))                 # winget ставит сюда без прав администратора
    for r in filter(None, roots):
        p = Path(r) / "Inno Setup 6" / "ISCC.exe"
        if p.is_file():
            return str(p)
    return None


def iscc_command(iscc):
    dist = ROOT / "dist"
    return [iscc, "/DAppVersion=" + __version__, "/DDist=" + str(dist / NAME),
            "/DIcon=" + str(ROOT / "build" / (NAME + ".ico")), "/DOutDir=" + str(dist), str(SCRIPT)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-exe", action="store_true", help="не пересобирать dist/OrganismAtlas")
    args = ap.parse_args()
    iscc = find_iscc()
    if not iscc:
        sys.exit("Нужен Inno Setup 6:  winget install JRSoftware.InnoSetup  (или задайте путь к ISCC.exe в ISCC)")
    if not args.skip_exe:
        # установщику нужна папка, а не --onefile: так программа открывается за секунду
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_exe.py")], check=True)
    if not (ROOT / "dist" / NAME / (NAME + ".exe")).is_file():
        sys.exit("Нет dist/%s/%s.exe: сначала  python tools/build_exe.py" % (NAME, NAME))
    if not (ROOT / "build" / (NAME + ".ico")).is_file():          # иконку делает build_exe.py
        sys.exit("Нет build/%s.ico: запустите без --skip-exe" % NAME)
    subprocess.run(iscc_command(iscc), check=True)
    print("Готово:", ROOT / "dist" / ("%s-Setup-%s.exe" % (NAME, __version__)))


if __name__ == "__main__":
    main()
