"""Растеризация треугольных сеток в z-буфер Scene3D (numpy, без циклов по треугольникам).

Для каждого треугольника перебираются пиксели его рамки, проверяется попадание центра пикселя
(барицентрические координаты), и в каждом пикселе побеждает самая близкая к камере точка.
Нормаль интерполируется по вершинам (гладкое затенение). Работа идёт порциями, чтобы большие
кадры не съедали память.
"""

import numpy as np

CHUNK = 3_000_000          # кандидатов-пикселей за порцию


def raster_mesh(V, F, VN, mid, bufs, cam, right, up, scale, cx, cy, ctr, cull=True):
    """V - вершины (n,3), F - треугольники (m,3), VN - нормали вершин (n,3), mid - номер части.
    bufs = (z, nrm, mat, sid) из Scene3D._raster, меняются на месте"""
    z, nrm, mat, sid = bufs
    H, W = z.shape
    rel = V - ctr[None, :]
    sx = cx + (rel @ right) * scale
    sy = cy - (rel @ up) * scale
    sd = rel @ cam
    if cull:                                        # задние грани закрытой сетки не видны
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
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
    cnt = bw * bh
    ends = np.cumsum(cnt)
    zf, mf, sf = z.reshape(-1), mat.reshape(-1), sid.reshape(-1)
    nf = nrm.reshape(3, -1)
    start = 0
    while start < len(F):
        base = ends[start - 1] if start else 0
        stop = int(np.searchsorted(ends, base + CHUNK, side="right"))
        stop = max(stop, start + 1)
        sl = slice(start, stop)
        c = cnt[sl]
        t = np.repeat(np.arange(start, stop), c)
        off = np.arange(int(c.sum())) - np.repeat(np.cumsum(c) - c, c)
        px = x0[t] + off % bw[t]
        py = y0[t] + off // bw[t]
        fx, fy = (px + 0.5).astype(np.float32), (py + 0.5).astype(np.float32)
        Xt, Yt = X[t], Y[t]
        inv = 1.0 / area[t]
        w0 = ((Xt[:, 1] - fx) * (Yt[:, 2] - fy) - (Xt[:, 2] - fx) * (Yt[:, 1] - fy)) * inv
        w1 = ((Xt[:, 2] - fx) * (Yt[:, 0] - fy) - (Xt[:, 0] - fx) * (Yt[:, 2] - fy)) * inv
        w2 = 1.0 - w0 - w1
        ok = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if ok.any():
            t, px, py, w0, w1, w2 = t[ok], px[ok], py[ok], w0[ok], w1[ok], w2[ok]
            dep = w0 * D[t, 0] + w1 * D[t, 1] + w2 * D[t, 2]
            pid = py * W + px
            np.maximum.at(zf, pid, dep)                # в z-буфере - самая близкая точка пикселя
            o = np.nonzero(dep >= zf[pid])[0]          # кто её дал (при равенстве - любой из них)
            if len(o):
                p = pid[o]
                mf[p] = mid
                sf[p] = -1
                tri = F[t[o]]
                n = (w0[o, None] * VN[tri[:, 0]] + w1[o, None] * VN[tri[:, 1]] + w2[o, None] * VN[tri[:, 2]])
                n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
                nf[:, p] = n.T
        start = stop


def vertex_normals(V, F):
    """нормали вершин: сумма нормалей соседних граней, взвешенная по площади"""
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)
