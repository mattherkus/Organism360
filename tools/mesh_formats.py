"""Чтение 3D-моделей для импорта (только numpy): glTF-binary (.glb), устаревший VTK (.vtk, POLYDATA)
и двоичный FBX 7.x (.fbx).

Возвращают список частей (имя, V (n,3) float64, F (m,3) int64): треугольники, без нормалей и текстур.
"""

import json
import struct
import zlib

import numpy as np

# типы компонент glTF -> numpy
_GL = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _node_matrix(n):
    if "matrix" in n:
        return np.array(n["matrix"], np.float64).reshape(4, 4).T          # glTF хранит по столбцам
    M = np.eye(4)
    M[:3, :3] = _quat_matrix(n.get("rotation", [0, 0, 0, 1])) * np.array(n.get("scale", [1, 1, 1]))[None, :]
    M[:3, 3] = n.get("translation", [0, 0, 0])
    return M


def read_glb(path):
    """части - примитивы сеток glTF с учётом преобразований узлов; имя - имя узла (или сетки)"""
    data = open(path, "rb").read()
    magic, _, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("%s: не glTF-binary" % path)
    pos, doc, binary = 12, None, b""
    while pos < length:
        clen, ctype = struct.unpack_from("<II", data, pos)
        chunk = data[pos + 8:pos + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk)
        elif ctype == 0x004E4942:
            binary = chunk
        pos += 8 + clen

    def accessor(i):
        a = doc["accessors"][i]
        bv = doc["bufferViews"][a["bufferView"]]
        dt = np.dtype(_GL[a["componentType"]])
        n = _N[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0) or dt.itemsize * n
        raw = np.frombuffer(binary, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * n, offset=off)
        out = np.lib.stride_tricks.as_strided(raw, (a["count"], dt.itemsize * n), (stride, 1))
        return np.ascontiguousarray(out).view(dt).reshape(a["count"], n)

    parts = []

    def visit(ni, parent):
        node = doc["nodes"][ni]
        M = parent @ _node_matrix(node)
        if "mesh" in node:
            mesh = doc["meshes"][node["mesh"]]
            name = node.get("name") or mesh.get("name") or "mesh%d" % node["mesh"]
            for prim in mesh["primitives"]:
                if prim.get("mode", 4) != 4:                     # только треугольники
                    continue
                V = accessor(prim["attributes"]["POSITION"]).astype(np.float64)
                V = V @ M[:3, :3].T + M[:3, 3]
                F = (accessor(prim["indices"]).reshape(-1) if "indices" in prim else np.arange(len(V)))
                F = F.astype(np.int64).reshape(-1, 3)
                if np.linalg.det(M[:3, :3]) < 0:                 # зеркальное преобразование - порядок обхода
                    F = F[:, ::-1]
                parts.append((name, V, F))
        for c in node.get("children", []):
            visit(c, M)

    scene = doc["scenes"][doc.get("scene", 0)]
    for ni in scene["nodes"]:
        visit(ni, np.eye(4))
    return parts


def read_vtk(path, name=None):
    """устаревший VTK (ASCII или BINARY), DATASET POLYDATA: POLYGONS и TRIANGLE_STRIPS"""
    data = open(path, "rb").read()
    binary = b"\nBINARY" in data[:300]
    pos = 0

    def line():
        nonlocal pos
        end = data.index(b"\n", pos)
        s = data[pos:end].decode("latin-1").strip()
        pos = end + 1
        return s

    def numbers(count, dtype, big):
        nonlocal pos
        if binary:
            dt = np.dtype(dtype).newbyteorder(">")
            arr = np.frombuffer(data, dt, count, pos)
            pos += arr.nbytes
            if data[pos:pos + 1] == b"\n":
                pos += 1
            return arr.astype(big)
        out = []
        while len(out) < count:
            out += line().split()
        return np.array(out[:count], big)

    V, tris = None, []
    while pos < len(data):
        s = line()
        if not s:
            continue
        head = s.split()
        if head[0] == "POINTS":
            n, t = int(head[1]), head[2]
            V = numbers(3 * n, {"float": np.float32, "double": np.float64}[t], np.float64).reshape(n, 3)
        elif head[0] in ("POLYGONS", "TRIANGLE_STRIPS"):
            size = int(head[2])
            if s.endswith("") and binary and data[pos:pos + 7] == b"OFFSETS":        # формат VTK 5.1
                raise ValueError("%s: VTK 5.1 не поддерживается" % path)
            cells = numbers(size, np.int32, np.int64)
            i = 0
            while i < len(cells):
                k = cells[i]
                ids = cells[i + 1:i + 1 + k]
                i += 1 + k
                if head[0] == "POLYGONS":
                    for j in range(1, k - 1):
                        tris.append((ids[0], ids[j], ids[j + 1]))
                else:
                    for j in range(k - 2):
                        a, b, c = ids[j], ids[j + 1], ids[j + 2]
                        tris.append((a, b, c) if j % 2 == 0 else (b, a, c))
        elif head[0] in ("POINT_DATA", "CELL_DATA"):
            break
    if V is None:
        raise ValueError("%s: нет точек" % path)
    return [(name or str(path), V, np.array(tris, np.int64).reshape(-1, 3))]


# ----------------------------------------------------------------------------------- FBX
# двоичный FBX: дерево записей (имя, свойства, вложенные записи); массивы свойств могут быть сжаты zlib
_FBX_ARR = {"f": "<f4", "d": "<f8", "l": "<i8", "i": "<i4", "b": "<u1"}
_FBX_SCALAR = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}


class _FbxNode:
    __slots__ = ("name", "props", "kids")

    def __init__(self, name, props, kids):
        self.name, self.props, self.kids = name, props, kids

    def find(self, name):
        return next((k for k in self.kids if k.name == name), None)


def _fbx_props(data, pos, n):
    out = []
    for _ in range(n):
        t = chr(data[pos])
        pos += 1
        if t in _FBX_SCALAR:
            fmt = _FBX_SCALAR[t]
            out.append(struct.unpack_from(fmt, data, pos)[0])
            pos += struct.calcsize(fmt)
        elif t in _FBX_ARR:
            count, enc, size = struct.unpack_from("<III", data, pos)
            raw = data[pos + 12:pos + 12 + size]
            pos += 12 + size
            out.append(np.frombuffer(zlib.decompress(raw) if enc == 1 else raw, _FBX_ARR[t], count))
        elif t in "SR":
            size = struct.unpack_from("<I", data, pos)[0]
            raw = data[pos + 4:pos + 4 + size]
            pos += 4 + size
            out.append(raw.decode("utf-8", "replace") if t == "S" else raw)
        else:
            raise ValueError("FBX: неизвестный тип свойства %r" % t)
    return out


def _fbx_node(data, pos, wide):
    """запись с позиции pos -> (запись или None для пустой записи-терминатора, позиция за ней)"""
    head = "<QQQ" if wide else "<III"                  # с версии 7500 смещения 64-битные
    end, nprop, plen = struct.unpack_from(head, data, pos)
    pos += struct.calcsize(head)
    nlen = data[pos]
    if end == 0:
        return None, pos + 1
    name = data[pos + 1:pos + 1 + nlen].decode("ascii", "replace")
    pos += 1 + nlen
    props = _fbx_props(data, pos, nprop)
    pos += plen
    kids = []
    while pos < end:
        kid, pos = _fbx_node(data, pos, wide)
        if kid is None:
            break
        kids.append(kid)
    return _FbxNode(name, props, kids), end


def _euler(deg):
    """углы Эйлера FBX (порядок XYZ: сначала поворот вокруг x) в градусах -> матрица 3x3"""
    x, y, z = np.radians(np.asarray(deg, np.float64))
    rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    return rz @ ry @ rx


def _fbx_matrix(p, prefix=""):
    """локальное преобразование модели (Lcl ...) или смещение её сетки (Geometric...) из Properties70"""
    M = np.eye(4)
    if prefix:
        T, R, S = (p.get(prefix + k, d) for k, d in (("Translation", (0, 0, 0)), ("Rotation", (0, 0, 0)),
                                                     ("Scaling", (1, 1, 1))))
        M[:3, :3] = _euler(R) @ np.diag(np.asarray(S, np.float64))
    else:
        T = p.get("Lcl Translation", (0, 0, 0))
        M[:3, :3] = (_euler(p.get("PreRotation", (0, 0, 0))) @ _euler(p.get("Lcl Rotation", (0, 0, 0)))
                     @ np.diag(np.asarray(p.get("Lcl Scaling", (1, 1, 1)), np.float64)))
    M[:3, 3] = T
    return M


def read_fbx(path, want=None):
    """части - сетки моделей (Model) с учётом иерархии и их преобразований; имя - имя модели.
    want(имя) -> bool отбирает модели заранее: в больших файлах сотни сеток, а нужны единицы.
    Координаты - как в файле, без учёта осей и единиц из GlobalSettings"""
    data = open(path, "rb").read()
    if not data.startswith(b"Kaydara FBX Binary"):
        raise ValueError("%s: не двоичный FBX" % path)
    wide = struct.unpack_from("<I", data, 23)[0] >= 7500
    pos, top = 27, {}
    while pos < len(data) - 13:
        node, pos = _fbx_node(data, pos, wide)
        if node is None:
            break
        top[node.name] = node
    models, geoms = {}, {}
    for n in top["Objects"].kids:
        if n.name == "Model":
            p70 = n.find("Properties70")
            models[n.props[0]] = (n.props[1].split("\x00")[0], {r.props[0]: r.props[4:] for r in (p70.kids if p70 else [])})
        elif n.name == "Geometry" and n.props[2] == "Mesh":
            geoms[n.props[0]] = n
    parent, geom_of = {}, {}
    for c in top["Connections"].kids:
        if c.props[0] == "OO" and c.props[2] in models:
            if c.props[1] in models:
                parent[c.props[1]] = c.props[2]
            elif c.props[1] in geoms:
                geom_of[c.props[2]] = c.props[1]

    def world(mid):
        M = _fbx_matrix(models[mid][1])
        return world(parent[mid]) @ M if mid in parent else M

    parts = []
    for mid, gid in geom_of.items():
        name, p70 = models[mid]
        if want is not None and not want(name):
            continue
        g = geoms[gid]
        V = g.find("Vertices").props[0].reshape(-1, 3).astype(np.float64)
        idx = g.find("PolygonVertexIndex").props[0].astype(np.int64)
        ends = np.flatnonzero(idx < 0)                     # последняя вершина многоугольника записана как ~i
        idx = np.where(idx < 0, ~idx, idx)
        starts = np.concatenate([[0], ends[:-1] + 1])
        ntri = ends - starts - 1                           # многоугольники -> веером треугольников
        poly = np.repeat(np.arange(len(starts)), ntri)
        k = np.arange(ntri.sum()) - np.repeat(np.cumsum(ntri) - ntri, ntri) + 1
        F = np.stack([idx[starts[poly]], idx[starts[poly] + k], idx[starts[poly] + k + 1]], 1)
        M = world(mid) @ _fbx_matrix(p70, "Geometric")
        V = V @ M[:3, :3].T + M[:3, 3]
        if np.linalg.det(M[:3, :3]) < 0:                   # зеркальное преобразование - порядок обхода
            F = F[:, ::-1]
        parts.append((name, V, F))
    return parts
