"""3D-модели органов из файлов models/<орган>.json.

Модель - список примитивов:
  {"type": "ellipsoid", "center": [x, y, z], "radii": [rx, ry, rz], ...}
  {"type": "tube", "path": [[x, y, z], ...], "radius": r или [r1, r2, ...], ...}
и у обоих: "color": "#rrggbb", "texture" (smooth, lung, gyri, folia, liver, muscle, gland, bowel),
"gloss" (блеск), необязательные "rings" (кольца, как у трахеи) и "hause" (перетяжки толстой кишки).
Список радиусов трубки - профиль вдоль её длины, число значений не обязано совпадать с числом точек.
Оси: x - вправо, y - вглубь (камера по умолчанию смотрит с -y), z - вверх.

load_procedural() отдаёт эти примитивы в том виде, который понимает render3d.scene.Scene3D.

Для органов есть и анатомические модели - треугольные сетки (models/mesh/<орган>.json + .npz) из BodyParts3D
(импорт: tools/bp3d_import.py), Human Reference Atlas и атласа головы и шеи Open Anatomy
(tools/atlas_import.py); источник - в поле "attribution", см. mesh_credit(). load_parts() берёт сетку, если
в render3d/look.json "models": "anatomical" (по умолчанию), а если сетки нет или она не читается -
процедурную модель.
"""

import copy
import io
import json
import sys
from importlib import resources

import numpy as np

from .render3d import look
from .render3d.primitives import E, T

_cache = {}
_mesh_cache = {}


def _primitive(d):
    rings, hause = d.get("rings", 0.0), d.get("hause", 0.0)
    if d["type"] == "ellipsoid":
        p = E(d["center"], d["radii"], d["color"], d["texture"], d["gloss"])
        if rings or hause:                         # Scene3D читает их у любого примитива
            p.update(rings=rings, hause=hause)
        return p
    if d["type"] == "tube":
        return T(d["path"], d["radius"], d["color"], d["texture"], d["gloss"], rings, hause)
    raise ValueError("неизвестный тип примитива: %r" % d["type"])


def read_model(key):
    """содержимое models/<key>.json как есть (для проверок и редакторов)"""
    path = resources.files(__package__) / "models" / (key + ".json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError("Ошибка в файле models/%s.json, строка %d, столбец %d: %s"
                         % (key, e.lineno, e.colno, e.msg)) from None


def load_procedural(key):
    """процедурная модель органа; файл читается один раз, каждый вызов получает свою копию"""
    if key not in _cache:
        _cache[key] = [_primitive(d) for d in read_model(key)["parts"]]
    return copy.deepcopy(_cache[key])


def _mesh_dir():
    return resources.files(__package__) / "models" / "mesh"


def has_mesh(key):
    return (_mesh_dir() / (key + ".json")).is_file()


def read_mesh_model(key):
    """описание анатомической модели: группы с цветом, текстурой, блеском и источником"""
    return json.loads((_mesh_dir() / (key + ".json")).read_text(encoding="utf-8"))


def mesh_credit(key):
    """источник анатомической модели для подписи авторов: bp3d, hra или spl (по полю attribution)"""
    attribution = read_mesh_model(key).get("attribution", "")
    if "Human Reference Atlas" in attribution:
        return "hra"
    if "Head and Neck" in attribution:
        return "spl"
    return "bp3d"


def load_mesh(key):
    """анатомическая модель: по сетке на группу материала (имя группы - в "group", по нему берётся
    название части в 3D-просмотре: раздел parts в lang/*.json). Массивы общие для всех вызовов
    и защищены от записи, поэтому список собирается заново, а геометрия не копируется"""
    if key not in _mesh_cache:
        meta = read_mesh_model(key)
        data = np.load(io.BytesIO((_mesh_dir() / meta["mesh"]).read_bytes()))
        groups = []
        for i, g in enumerate(meta["groups"]):
            arr = [np.asarray(data[k + str(i)], dt) for k, dt in (("v", np.float64), ("f", np.int64), ("n", np.float64))]
            for a in arr:
                a.flags.writeable = False
            if arr[1].max() >= len(arr[0]):
                raise ValueError("models/mesh/%s: номер вершины за пределами сетки" % key)
            groups.append((g, arr))
        _mesh_cache[key] = groups
    return [{"k": "m", "v": V, "f": F, "vn": N, "color": g["color"], "tex": g["texture"], "gloss": g["gloss"],
             "group": g["group"]} for g, (V, F, N) in _mesh_cache[key]]


def load_parts(key):
    """модель органа для 3D-просмотра: анатомическая, если она есть и включена, иначе процедурная"""
    if look.get().get("models", "anatomical") == "anatomical" and has_mesh(key):
        try:
            return load_mesh(key)
        except Exception as e:                       # битый файл не должен ломать просмотр
            print("models/mesh/%s: %s; показываю процедурную модель" % (key, e), file=sys.stderr)
    return load_procedural(key)
