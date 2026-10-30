"""Кэш готовой схемы тела на диске: второй запуск не рисует тело и органы заново.

Схема детерминирована (сиды фиксированы), поэтому её можно сохранить и потом просто прочитать.
Файл: atlas-<версия>-z<масштаб>.npz в папке кэша пользователя (см. _cache_dir); в нём слои тела, слои и маски органов
(фон в кэш не входит: его цвет зависит от темы и подставляется при показе).
Один файл, а не PNG + маски отдельно: он пишется атомарно, и половинчатый кэш не получится.

Версия - хэш исходников, от которых зависит рисунок, плюс версии numpy и Pillow. Поправили рисунок
органа - версия сменилась, схема перерисуется сама, а старые файлы удалятся.
Любая проблема с кэшем (нет прав, файл испорчен) - просто рисуем заново, как без кэша.
Сборка (tools/build_exe.py) кладёт в пакет папку prebuilt с готовыми схемами нескольких масштабов: при первом
запуске схема берётся оттуда (или ближайшая из них показывается растянутой, пока рисуется точная).
"""

import hashlib
import os
from pathlib import Path

import numpy as np
import PIL

PKG = Path(__file__).parent


def _cache_dir():
    """%LOCALAPPDATA%/organism_atlas/cache (на других системах ~/.cache/organism_atlas): туда можно писать,
    даже если программа установлена в папку только для чтения. ORGANISM_ATLAS_CACHE задаёт другой путь"""
    custom = os.environ.get("ORGANISM_ATLAS_CACHE")
    if custom:
        return Path(custom)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "organism_atlas" / "cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "organism_atlas"


CACHE_DIR = _cache_dir()
PREBUILT = PKG / "prebuilt"                       # готовые схемы из сборки (tools/build_exe.py), только чтение
FORMAT = 4                                        # поднять, если поменяется устройство файла
KEEP = 6                                          # сколько масштабов хранить (окно меняет размер)

# что влияет на картинку и маски; ui, викторина, тексты и 3D сюда не входят
_SOURCES = ["atlas.py", "geometry.py", "colors.py", "config.py", "body", "organs", "render2d"]


def version():
    """хэш исходников рисунка. В собранной программе (tools/build_exe.py) эти исходники лежат рядом
    как данные - версия та же, что при запуске из исходников. Если файла нет, хэшируется только его имя:
    кэш работает, просто не следит за правками этого файла"""
    h = hashlib.sha256(("%d|%s|%s" % (FORMAT, np.__version__, PIL.__version__)).encode())
    for name in _SOURCES:
        p = PKG / name
        for f in sorted(p.rglob("*.py")) if p.is_dir() else [p]:
            h.update(f.relative_to(PKG).as_posix().encode())
            if f.is_file():
                h.update(f.read_bytes())
    return h.hexdigest()[:16]


def zoom_key(Z):
    """масштаб с фиксированной точностью: им же и рисуем, чтобы кэш точно совпадал с рендером"""
    return round(float(Z), 4)


def _path(Z, cache_dir, ver):
    return Path(cache_dir) / ("atlas-%s-z%.4f.npz" % (ver, zoom_key(Z)))


BODY = ("glow", "skin", "skin_hi", "muscles", "skeleton", "veins", "arteries", "fade")    # слои тела (uint8)


def _read(p, ORDER):
    """({слой тела: uint8}, {орган: {rgba, hit, origin}}) из файла p или None, если его нет или он не годится"""
    try:
        with np.load(p) as z:
            body = {k: z["body_" + k] for k in BODY}
            org = {k: {"rgba": z["rgba_" + k], "hit": z["hit_" + k],
                       "origin": tuple(int(v) for v in z["origin_" + k])} for k in ORDER}
    except (OSError, KeyError, ValueError, EOFError):   # нет файла, другой набор органов, мусор
        return None
    shape = body["skin"].shape
    if any(a.dtype != np.uint8 for a in body.values()) or len(shape) != 3 or shape[2] != 4:
        return None
    if any(d["rgba"].dtype != np.uint8 or d["rgba"].shape[:2] != d["hit"].shape for d in org.values()):
        return None
    return body, org


def load(Z, ORDER, cache_dir=CACHE_DIR, prebuilt=PREBUILT):
    """({слой тела: uint8}, {орган: {rgba, hit, origin}}) или None, если в кэше нет.
    Сначала кэш пользователя, потом готовые схемы, которые положила сборка (prebuilt)"""
    ver = version()
    p = _path(Z, cache_dir, ver)
    data = _read(p, ORDER)
    if data is None:
        return _read(_path(Z, prebuilt, ver), ORDER)
    try:
        os.utime(p)                                     # свежий по времени: его save() удалит последним
    except OSError:
        pass
    return data


def nearest(Z, ORDER, prebuilt=PREBUILT):
    """(масштаб, данные) готовой схемы из сборки, ближайшей по масштабу к Z, или None. Её показывают
    растянутой при первом запуске, пока рисуется схема точно под окно"""
    ver = version()
    zooms = []
    for f in Path(prebuilt).glob("atlas-%s-z*.npz" % ver):
        try:
            zooms.append(float(f.stem.rsplit("-z", 1)[1]))
        except ValueError:
            continue
    for z in sorted(zooms, key=lambda z: abs(z - Z)):
        data = _read(_path(z, prebuilt, ver), ORDER)
        if data is not None:
            return zoom_key(z), data
    return None


def save(Z, body, org, cache_dir=CACHE_DIR):
    """сохранить схему; заодно убрать файлы прошлых версий и самые давние масштабы сверх KEEP"""
    ver = version()
    p = _path(Z, cache_dir, ver)
    arrays = {"body_" + k: body[k] for k in BODY}
    for k, d in org.items():
        arrays["rgba_" + k] = d["rgba"]
        arrays["hit_" + k] = d["hit"]
        arrays["origin_" + k] = np.array(d["origin"], np.int64)
    tmp = p.with_name(p.name + ".%d.tmp" % os.getpid())
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            np.savez_compressed(f, **arrays)
        os.replace(tmp, p)
        for old in p.parent.glob("atlas-*.npz*"):        # и недописанные .tmp прошлых версий
            if not old.name.startswith("atlas-%s-" % ver):
                old.unlink()
        mine = sorted(p.parent.glob("atlas-%s-*.npz" % ver), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in mine[KEEP:]:
            if old != p:
                old.unlink()
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
