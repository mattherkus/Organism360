"""Чтение 3D-моделей для импорта (только numpy): glTF-binary (.glb) и устаревший VTK (.vtk, POLYDATA).

Возвращают список частей (имя, V (n,3) float64, F (m,3) int64): треугольники, без нормалей и текстур.
"""

import json
import struct

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
