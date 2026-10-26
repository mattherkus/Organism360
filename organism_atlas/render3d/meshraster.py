"""Растеризация треугольных сеток в z-буфер Scene3D (numpy, без циклов по треугольникам).

Для каждого треугольника перебираются пиксели его рамки, проверяется попадание центра пикселя
(барицентрические координаты), и в каждом пикселе побеждает самая близкая к камере точка.
Нормаль интерполируется по вершинам (гладкое затенение).

Треугольники группируются по размеру рамки (с округлением вверх до SIZES): у группы пиксели-кандидаты -
одна и та же сетка смещений, и всё считается широкими операциями над массивом (треугольник x пиксель)
без поэлементных выборок. Работа идёт порциями, чтобы большие кадры не съедали память.
При равной глубине побеждает треугольник с большим номером - как при обходе треугольников по порядку.
Черновик (exact=False) считает барицентрические координаты по готовым уравнениям рёбер: вдвое меньше
операций, но в последнем знаке результат другой, поэтому чистый кадр считается по-прежнему.
"""

import numpy as np

CHUNK = 3_000_000          # кандидатов-пикселей за порцию
SIZES = np.array([1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024,
                  1536, 2048, 3072, 4096, 6144, 8192])        # стороны рамок групп


def face_normals(V, F):
    """ненормированные нормали граней (для отсечения задних граней); у сетки их можно посчитать один раз"""
    return np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])


def raster_mesh(V, F, VN, mid, bufs, cam, right, up, scale, cx, cy, ctr, cull=True, FN=None, exact=True):
    """V - вершины (n,3), F - треугольники (m,3), VN - нормали вершин (n,3), mid - номер части,
    FN - готовые face_normals(V, F) (иначе считаются здесь); exact=False - быстрый черновик.
    bufs = (z, nrm, mat, sid) из Scene3D._raster, меняются на месте"""
    z, nrm, mat, sid = bufs
    H, W = z.shape
    rel = V - ctr[None, :]
    sx = cx + (rel @ right) * scale
    sy = cy - (rel @ up) * scale
    sd = rel @ cam
    if cull:                                        # задние грани закрытой сетки не видны
        fn = face_normals(V, F) if FN is None else FN
        F = F[fn @ cam > 0]
    if not len(F):
        return
    sx, sy, sd = sx.astype(np.float32), sy.astype(np.float32), sd.astype(np.float32)
    X, Y = sx[F], sy[F]                               # (m,3)
    x0 = np.clip(np.ceil(X.min(1) - 0.5), 0, W).astype(np.int64)
    x1 = np.clip(np.floor(X.max(1) - 0.5), -1, W - 1).astype(np.int64)
    y0 = np.clip(np.ceil(Y.min(1) - 0.5), 0, H).astype(np.int64)
    y1 = np.clip(np.floor(Y.max(1) - 0.5), -1, H - 1).astype(np.int64)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    keep = (bw > 0) & (bh > 0)
    area = (X[:, 1] - X[:, 0]) * (Y[:, 2] - Y[:, 0]) - (X[:, 2] - X[:, 0]) * (Y[:, 1] - Y[:, 0])
    keep &= np.abs(area) > 1e-12
    if not keep.any():
        return
    F, X, Y, x0, y0, bw, bh, area = F[keep], X[keep], Y[keep], x0[keep], y0[keep], bw[keep], bh[keep], area[keep]
    D = sd[F]
    inv = 1.0 / area
    if not exact:
        # w0 = A0*fx + B0*fy + C0 (и так же w1); в C - сразу значение в центре левого верхнего пикселя рамки
        fx0, fy0 = (x0 + 0.5).astype(np.float32), (y0 + 0.5).astype(np.float32)
        edges = []
        for i, j in ((1, 2), (2, 0)):
            A = (Y[:, i] - Y[:, j]) * inv
            B = (X[:, j] - X[:, i]) * inv
            C = (X[:, i] * Y[:, j] - X[:, j] * Y[:, i]) * inv
            edges += [A, B, A * fx0 + B * fy0 + C]
        E = np.stack(edges, 1)                       # (m, 6): A0, B0, C0, A1, B1, C1
    gw = SIZES[np.searchsorted(SIZES, bw)]            # рамка группы: сторона, округлённая вверх
    gh = SIZES[np.searchsorted(SIZES, bh)]
    ends = np.cumsum(gw * gh)
    zf, mf, sf = z.reshape(-1), mat.reshape(-1), sid.reshape(-1)
    nf = nrm.reshape(3, -1)
    start = 0
    while start < len(F):
        base = ends[start - 1] if start else 0
        stop = int(np.searchsorted(ends, base + CHUNK, side="right"))
        stop = max(stop, start + 1)
        key = gh[start:stop] * 16384 + gw[start:stop]
        order = np.argsort(key, kind="stable")         # внутри группы - по возрастанию номера
        cuts = np.flatnonzero(np.diff(key[order])) + 1
        order += start
        parts = []
        for ti in np.split(order, cuts):
            g = int(gw[ti[0]]), int(gh[ti[0]])
            parts.append(_hits(ti, *g, X, Y, x0, y0, bw, bh, inv) if exact else _hits_fast(ti, *g, E, x0, y0, bw, bh))
        t, px, py, w0, w1, w2 = (np.concatenate(c) for c in zip(*parts))
        if len(t):
            dep = w0 * D[t, 0] + w1 * D[t, 1] + w2 * D[t, 2]
            pid = py * W + px
            np.maximum.at(zf, pid, dep)                # в z-буфере - самая близкая точка пикселя
            o = np.nonzero(dep >= zf[pid])[0]          # кто её дал (при равенстве - последний по номеру)
            if len(o):
                if exact:
                    o = o[np.argsort(t[o], kind="stable")]
                p = pid[o]
                mf[p] = mid
                sf[p] = -1
                tri = F[t[o]]
                n = (w0[o, None] * VN[tri[:, 0]] + w1[o, None] * VN[tri[:, 1]] + w2[o, None] * VN[tri[:, 2]])
                n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
                nf[:, p] = n.T
        start = stop


def _hits(ti, gw, gh, X, Y, x0, y0, bw, bh, inv):
    """пиксели, центры которых внутри треугольников ti (у всех рамка не больше gw x gh):
    (номер треугольника, x, y, w0, w1, w2) по попаданиям"""
    ox = np.tile(np.arange(gw), gh)[None, :]
    oy = np.repeat(np.arange(gh), gw)[None, :]
    px = x0[ti][:, None] + ox
    py = y0[ti][:, None] + oy
    fx, fy = (px + 0.5).astype(np.float32), (py + 0.5).astype(np.float32)
    Xt, Yt = X[ti], Y[ti]
    X0, X1, X2 = Xt[:, 0:1], Xt[:, 1:2], Xt[:, 2:3]
    Y0, Y1, Y2 = Yt[:, 0:1], Yt[:, 1:2], Yt[:, 2:3]
    iv = inv[ti][:, None]
    w0 = ((X1 - fx) * (Y2 - fy) - (X2 - fx) * (Y1 - fy)) * iv
    w1 = ((X2 - fx) * (Y0 - fy) - (X0 - fx) * (Y2 - fy)) * iv
    w2 = 1.0 - w0 - w1
    ok = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if gw > 1 or gh > 1:                               # рамка группы шире рамки треугольника
        ok &= (ox < bw[ti][:, None]) & (oy < bh[ti][:, None])
    r = np.nonzero(ok)[0]
    return ti[r], px[ok], py[ok], w0[ok], w1[ok], w2[ok]


def _hits_fast(ti, gw, gh, E, x0, y0, bw, bh):
    """то же, что _hits, по уравнениям рёбер E (черновик)"""
    oxi, oyi = np.tile(np.arange(gw), gh), np.repeat(np.arange(gh), gw)
    ox, oy = oxi.astype(np.float32)[None, :], oyi.astype(np.float32)[None, :]
    e = E[ti]
    w0 = e[:, 2:3] + e[:, 0:1] * ox + e[:, 1:2] * oy
    w1 = e[:, 5:6] + e[:, 3:4] * ox + e[:, 4:5] * oy
    ok = (w0 >= 0) & (w1 >= 0) & (w0 + w1 <= 1)
    if gw > 1 or gh > 1:
        ok &= (oxi[None, :] < bw[ti][:, None]) & (oyi[None, :] < bh[ti][:, None])
    r, c = np.nonzero(ok)
    t = ti[r]
    w0, w1 = w0[ok], w1[ok]
    return t, x0[t] + oxi[c], y0[t] + oyi[c], w0, w1, 1.0 - w0 - w1


def vertex_normals(V, F):
    """нормали вершин: сумма нормалей соседних граней, взвешенная по площади"""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)
