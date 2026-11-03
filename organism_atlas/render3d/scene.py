"""Scene3D: сборка частей органа и программный рендер с освещением и AO."""

import math

import numpy as np
from PIL import Image

from ..colors import hex2rgb
from ..render2d.noise import gblur
from . import look, shading
from .mathutils import cr_nd, unit
from .meshraster import face_normals, raster_mesh, vertex_normals
from .surface import surface


BG = ("#0e1a22", "#1b3a50")       # фон кадра по умолчанию (тёмная тема)


class Scene3D:
    def __init__(self, parts):
        """parts - примитивы и сетки (models.load_parts); номер части в списке - её номер в render(hidden=...)
        и в карте частей render(ids=True)"""
        self.mats, self.ell, self.meshes = [], [], []
        C, R, S, M, TG, SL, CW = [], [], [], [], [], [], []
        for p in parts:
            mid = len(self.mats)
            self.mats.append({"color": hex2rgb(p["color"]), "tex": p["tex"], "gloss": p["gloss"],
                              "rings": p.get("rings", 0.0), "hause": p.get("hause", 0.0)})
            if p["k"] == "e":
                self.ell.append((np.asarray(p["c"], np.float64), np.asarray(p["r"], np.float64), mid))
            elif p["k"] == "m":                              # треугольная сетка (модели BodyParts3D)
                V = np.asarray(p["v"], np.float64)
                F = np.asarray(p["f"], np.int64)
                VN = np.asarray(p["vn"], np.float64) if p.get("vn") is not None else vertex_normals(V, F)
                cull = p.get("cull", True)
                FN = face_normals(V, F) if cull else None        # для отсечения задних граней: один раз
                self.meshes.append((V, F, VN, mid, cull, FN))
            else:
                pts = cr_nd(p["path"], 16)
                seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
                s = np.concatenate([[0], np.cumsum(seg)])
                L = s[-1]
                rad = p["rad"]
                if np.isscalar(rad):
                    r_at = lambda ss, rad=rad: np.full_like(ss, float(rad))
                else:
                    prof = cr_nd([[v] for v in rad], 24)[:, 0]          # гладкий профиль радиуса
                    r_at = lambda ss, prof=prof, L=L: np.interp(ss / L, np.linspace(0, 1, len(prof)), prof)
                vals, pos = [0.0], 0.0
                while pos < L and len(vals) < 2000:          # шаг пропорционален радиусу: гладкая трубка
                    pos += 0.12 * float(r_at(np.array([pos]))[0])
                    vals.append(min(pos, L))
                ss = np.array(vals)
                n = len(ss)
                cc = np.stack([np.interp(ss, s, pts[:, k]) for k in range(3)], 1)
                rs = r_at(ss)
                tg = np.gradient(cc, axis=0)
                tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
                C.append(cc)
                R.append(rs)
                S.append(ss)
                M.append(np.full(n, mid))
                TG.append(tg)
                SL.append(np.gradient(rs, ss))
                CW.append(np.clip(np.minimum(ss, L - ss) / (1.2 * rs), 0, 1))
        if C:
            self.C, self.R = np.concatenate(C).astype(np.float64), np.concatenate(R)
            self.S, self.M = np.concatenate(S), np.concatenate(M)
            self.TG, self.SL, self.CW = np.concatenate(TG), np.concatenate(SL), np.concatenate(CW)
        else:
            self.C = np.zeros((0, 3)); self.R = self.S = np.zeros(0); self.M = np.zeros(0, int)
            self.TG = np.zeros((0, 3)); self.SL = self.CW = np.zeros(0)
        lo = np.array([1e9] * 3); hi = np.array([-1e9] * 3)
        for c, r, _ in self.ell:
            lo, hi = np.minimum(lo, c - r), np.maximum(hi, c + r)
        for V, *_ in self.meshes:
            lo, hi = np.minimum(lo, V.min(0)), np.maximum(hi, V.max(0))
        if len(self.C):
            lo = np.minimum(lo, (self.C - self.R[:, None]).min(0))
            hi = np.maximum(hi, (self.C + self.R[:, None]).max(0))
        self.center = (lo + hi) / 2
        self.radius = float(np.linalg.norm(hi - lo) / 2) * 0.93
        self._bg = {}

    # --- фон
    def background(self, w, h, colors=BG):
        """фон кадра: colors - (цвет фона, цвет пятна в центре), #rrggbb; задаёт тема оформления"""
        key = (w, h, colors)
        if key not in self._bg:
            self._bg.clear()                    # только последний: размер черновика меняется почти каждый кадр
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            r = np.hypot((xx / w - 0.5) / 0.5, (yy / h - 0.52) / 0.56)     # на краях кадра свечение = 0
            t = np.clip(1 - r, 0, 1) ** 1.6
            bg, hi = hex2rgb(colors[0]), hex2rgb(colors[1])
            self._bg[key] = bg[None, None, :] * (1 - t[..., None]) + hi[None, None, :] * t[..., None]
        return self._bg[key]

    # --- рендер
    def _raster(self, W_, H_, cam, right, up, scale, cx, cy, step, hidden=()):
        """z-буфер в ортографической проекции по осям cam/right/up: для каждого пикселя глубина
        (больше - ближе к камере), нормаль, номер части и номер узла трубки (-1 у эллипсоидов и сеток).
        hidden - номера частей, которых не рисуем"""
        ctr = self.center
        z = np.full((H_, W_), -1e9, np.float32)
        nrm = np.zeros((3, H_, W_), np.float32)
        mat = np.full((H_, W_), -1, np.int16)
        sid = np.full((H_, W_), -1, np.int32)
        Ug = ((np.arange(W_) + 0.5 - cx) / scale).astype(np.float32)
        Vg = ((cy - (np.arange(H_) + 0.5)) / scale).astype(np.float32)

        def box(uc, vc, rb):
            x0 = max(int(cx + uc * scale - rb * scale) - 1, 0)
            x1 = min(int(cx + uc * scale + rb * scale) + 2, W_)
            y0 = max(int(cy - vc * scale - rb * scale) - 1, 0)
            y1 = min(int(cy - vc * scale + rb * scale) + 2, H_)
            return x0, x1, y0, y1

        for V, F, VN, mid, cull, FN in self.meshes:
            if mid in hidden:
                continue
            raster_mesh(V, F, VN, mid, (z, nrm, mat, sid), cam, right, up, scale, cx, cy, ctr, cull, FN,
                        exact=step == 1)                # черновик (step > 1) - быстрым способом

        for c, r, mid in self.ell:
            if mid in hidden:
                continue
            rel = c - ctr
            uc, vc = float(rel @ right), float(rel @ up)
            x0, x1, y0, y1 = box(uc, vc, float(r.max()))
            if x1 <= x0 or y1 <= y0:
                continue
            u = Ug[x0:x1][None, :]
            v = Vg[y0:y1][:, None]
            ir2 = 1.0 / (r * r)
            q = [(ctr[k] - c[k]) + u * right[k] + v * up[k] for k in range(3)]
            A = sum(cam[k] ** 2 * ir2[k] for k in range(3))
            B = sum(q[k] * cam[k] * ir2[k] for k in range(3))
            C0 = sum(q[k] ** 2 * ir2[k] for k in range(3)) - 1.0
            disc = B * B - A * C0
            ok = disc > 0
            zz = (-B + np.sqrt(np.where(ok, disc, 0))) / A
            zs = z[y0:y1, x0:x1]
            upd = ok & (zz > zs)
            if not upd.any():
                continue
            zs[upd] = zz[upd]
            pk = [(q[k] + zz * cam[k]) * ir2[k] for k in range(3)]
            ln = np.sqrt(pk[0] ** 2 + pk[1] ** 2 + pk[2] ** 2) + 1e-9
            for k in range(3):
                nrm[k, y0:y1, x0:x1][upd] = (pk[k] / ln)[upd]
            mat[y0:y1, x0:x1][upd] = mid
            sid[y0:y1, x0:x1][upd] = -1

        for i in range(0, len(self.C), step):
            if hidden and int(self.M[i]) in hidden:
                continue
            rel = self.C[i] - ctr
            r = float(self.R[i])
            uc, vc, zc = float(rel @ right), float(rel @ up), float(rel @ cam)
            x0, x1, y0, y1 = box(uc, vc, r)
            if x1 <= x0 or y1 <= y0:
                continue
            du = Ug[x0:x1][None, :] - uc
            dv = Vg[y0:y1][:, None] - vc
            rr = r * r - du * du - dv * dv
            ok = rr > 0
            sq = np.sqrt(np.where(ok, rr, 0))
            zz = zc + sq
            zs = z[y0:y1, x0:x1]
            upd = ok & (zz > zs)
            if not upd.any():
                continue
            zs[upd] = zz[upd]
            for k in range(3):
                nrm[k, y0:y1, x0:x1][upd] = ((du * right[k] + dv * up[k] + sq * cam[k]) / r)[upd]
            mat[y0:y1, x0:x1][upd] = int(self.M[i])
            sid[y0:y1, x0:x1][upd] = i

        return z, nrm, mat, sid, Ug, Vg

    def _soften_seams(self, lk, nrm, z, mat, hit, size):
        """скругление стыков между частями одной ткани (камеры сердца, доли печени): у шва нормали
        плавно усредняются по обе стороны, и острая складка пересечения двух эллипсоидов исчезает.
        Силуэт не меняется, меняется только освещение у шва."""
        ids = [i for i, m in enumerate(self.mats) if m["tex"] in lk["seams"]["textures"]]
        if len(ids) < 2:
            return
        blend = np.isin(mat, ids) & hit
        tol = 0.05 * self.radius                       # больше - это уже перекрытие, а не стык
        seam = np.zeros_like(blend)
        for dy, dx in ((0, 1), (1, 0)):
            m2 = np.roll(mat, (-dy, -dx), (0, 1))
            z2 = np.roll(z, (-dy, -dx), (0, 1))
            b2 = np.roll(blend, (-dy, -dx), (0, 1))
            seam |= blend & b2 & (mat != m2) & (np.abs(z - z2) < tol)
        if not seam.any():
            return
        s = lk["seams"]["width"] * size
        # размываем только рамку вокруг швов (с запасом в 4 сигмы), а не весь кадр
        ys, xs = np.nonzero(seam)
        pad = int(4 * s) + 2
        y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, seam.shape[0])
        x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, seam.shape[1])
        win = (slice(y0, y1), slice(x0, x1))
        bl = blend[win]
        w = np.clip(gblur(seam[win].astype(np.float32), s) * 2.5 * s, 0, 1) * bl
        bw = gblur(bl.astype(np.float32), s) + 1e-6
        part = nrm[:, y0:y1, x0:x1]
        nb = [gblur(part[k] * bl, s) / bw for k in range(3)]
        for k in range(3):
            part[k] = part[k] * (1 - w) + nb[k] * w
        part /= np.sqrt(part[0] ** 2 + part[1] ** 2 + part[2] ** 2)[None] + 1e-9

    def _shadow(self, lk, P, L, hidden=()):
        """освещённость точек P ключевым светом с направления L: карта глубины из точки зрения
        света и мягкий край тени (выборка по кольцу, PCF). 1 - светло, 1 - strength - тень"""
        cfg = lk["shadows"]
        S = int(cfg["map_size"])
        ref = np.array([0.0, 0.0, 1.0]) if abs(L[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        rl = unit(np.cross(ref, L))
        ul = unit(np.cross(L, rl))
        scale = 0.5 * S / (1.1 * self.radius)
        zl, _, _, _, _, _ = self._raster(S, S, L, rl, ul, scale, S / 2.0, S / 2.0, 1, hidden)
        rel = (P - self.center[None, :]).astype(np.float64)
        x = S / 2.0 + (rel @ rl) * scale - 0.5
        y = S / 2.0 - (rel @ ul) * scale - 0.5
        d = rel @ L
        bias = 2.5 / scale
        r = cfg["softness"]
        taps = [(0.0, 0.0)] + [(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)] + \
               [(0.5 * r * math.cos(t), 0.5 * r * math.sin(t)) for t in np.linspace(0.4, 2 * math.pi + 0.4, 4, endpoint=False)]
        dark = np.zeros(len(P), np.float32)
        for ox, oy in taps:
            xi = np.clip(np.rint(x + ox).astype(np.int64), 0, S - 1)
            yi = np.clip(np.rint(y + oy).astype(np.int64), 0, S - 1)
            dark += zl[yi, xi] > d + bias
        return 1.0 - cfg["strength"] * dark / len(taps)

    def render(self, w, h, az, el, zoom=1.0, ss=1, ao=0.55, step=1, style=None, shadows=None, bg=BG, hidden=(),
               ids=False):
        """кадр w x h; ss - суперсэмплинг, step - прореживание узлов трубок (черновик).
        bg - цвета фона (фон, пятно в центре), см. background.
        hidden - номера частей, которые не рисуются (и не отбрасывают тени); камера от этого не сдвигается.
        ids=True - вернуть (кадр, карта частей): массив h x w с номером части в пикселе, -1 - фон.
        style: realistic / classic, по умолчанию из look.json; ao - сила AO классического стиля.
        shadows: None - как в look.json, но в черновике (step > 1) без теней, чтобы вращение не тормозило"""
        lk = look.get()
        style = style or lk["style"]
        if "lights" not in lk:                       # look.json не прочитался: только классический вид
            style = "classic"
        W_, H_ = w * ss, h * ss
        a, e = math.radians(az), math.radians(el)
        cam = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
        right = np.array([-math.sin(a), math.cos(a), 0.0])
        up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
        scale = zoom * 0.5 * min(W_, H_) / self.radius
        cx, cy = W_ / 2.0, H_ / 2.0
        ctr = self.center
        z, nrm, mat, sid, Ug, Vg = self._raster(W_, H_, cam, right, up, scale, cx, cy, step, hidden)
        hit = mat >= 0
        if style == "realistic" and step == 1 and hit.any():       # в черновике шов не заметен
            self._soften_seams(lk, nrm, z, mat, hit, min(W_, H_))
        img = np.broadcast_to(self.background(W_, H_, tuple(bg)), (H_, W_, 3)).copy()
        if hit.any():
            jj, ii = np.nonzero(hit)
            N = np.stack([nrm[0][hit], nrm[1][hit], nrm[2][hit]], 1)
            N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
            zv = z[hit]
            uu, vv = Ug[ii], Vg[jj]
            P = (ctr[None, :] + uu[:, None] * right[None, :] + vv[:, None] * up[None, :] +
                 zv[:, None] * cam[None, :]).astype(np.float32)
            mv, sidv = mat[hit], sid[hit]
            sv = (np.where(sidv >= 0, self.S[np.maximum(sidv, 0)], 0.0) if len(self.S)   # длина вдоль трубки
                  else np.zeros(len(sidv))).astype(np.float32)
            tb = sidv >= 0
            if tb.any():                       # трубки: убираем осевую компоненту нормали (нет «ребристости»)
                ti = sidv[tb]
                Tt = self.TG[ti].astype(np.float32)
                nn = N[tb]
                npd = nn - (nn * Tt).sum(1, keepdims=True) * Tt
                npd /= np.linalg.norm(npd, axis=1, keepdims=True) + 1e-9
                nt = npd - self.SL[ti][:, None].astype(np.float32) * Tt
                nt /= np.linalg.norm(nt, axis=1, keepdims=True) + 1e-9
                wv = self.CW[ti][:, None].astype(np.float32)
                nm = wv * nt + (1 - wv) * nn
                N[tb] = nm / (np.linalg.norm(nm, axis=1, keepdims=True) + 1e-9)
            alb = np.zeros((len(P), 3), np.float32)
            gl = np.zeros(len(P), np.float32)
            eps = 0.02
            for m_id, mt in enumerate(self.mats):
                sel = mv == m_id
                if not sel.any():
                    continue
                Ps, Ns, ss_ = P[sel], N[sel], sv[sel]
                a0, h0 = surface(mt, Ps, Ns, ss_)
                alb[sel] = a0
                gl[sel] = mt["gloss"]
                if np.abs(h0).max() > 0:
                    _, hu = surface(mt, Ps + eps * right.astype(np.float32), Ns, ss_)
                    _, hv = surface(mt, Ps + eps * up.astype(np.float32), Ns, ss_)
                    gu, gv = (hu - h0) / eps, (hv - h0) / eps
                    Nn = Ns - 0.9 * (gu[:, None] * right[None, :] + gv[:, None] * up[None, :])
                    N[sel] = Nn / (np.linalg.norm(Nn, axis=1, keepdims=True) + 1e-9)
            if style == "classic":
                key = unit(0.85 * cam + 0.55 * up - 0.50 * right)
                fill = unit(0.55 * cam - 0.15 * up + 0.85 * right)
                rim = unit(-0.6 * cam + 0.6 * up + 0.4 * right)
                dif = 0.34 + 0.70 * np.clip(N @ key, 0, 1) + 0.20 * np.clip(N @ fill, 0, 1) + \
                    0.22 * np.clip(N @ rim, 0, 1)
                Hv = unit(key + cam)
                sp = np.clip(N @ Hv, 0, 1) ** 28 * gl
                ndc = np.clip(N @ cam, 0, 1)
                fres = (1 - ndc) ** 3 * 0.30
                # экранный AO: углубления и стыки темнее
                zf = np.where(hit, z, z[hit].min() - 2 * self.radius).astype(np.float32)
                zb = gblur(zf, 0.035 * min(W_, H_))
                occ = np.clip((zb - zf)[hit] / (0.45 * self.radius), 0, 1)
                rgb = alb * dif[:, None] * 1.1 * (1 - ao * occ)[:, None] + sp[:, None] + \
                    fres[:, None] * np.array([0.30, 0.50, 0.75], np.float32)
                img[hit] = np.clip(rgb, 0, 1)
            else:
                # экранный AO в двух масштабах: щели и стыки плюс общий объём
                zf = np.where(hit, z, z[hit].min() - 2 * self.radius).astype(np.float32)
                r_ao = lk["ao"]["radius"] * min(W_, H_)
                occ = np.zeros(int(hit.sum()), np.float32)
                for k_r, k_d in ((0.45, 0.10), (1.0, 0.45))[(step > 1):]:      # черновик: только крупный масштаб
                    zb = gblur(zf, k_r * r_ao)
                    occ = np.maximum(occ, np.clip((zb - zf)[hit] / (k_d * self.radius), 0, 1))
                sh = lk["shadows"]["enabled"] if shadows is None else shadows
                if shadows is None and step > 1:
                    sh = False
                key_dir = shading.light_dirs(lk, cam, right, up)["key"]
                vis = self._shadow(lk, P, key_dir, hidden) if sh else None
                img[hit] = shading.shade(lk, self.mats, P, N, alb, gl, mv, cam, right, up, occ, vis, draft=step > 1)
        out = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
        im = Image.fromarray(out)
        im = im.reduce(ss) if ss > 1 else im
        if ids:                                      # номер части в центре каждого итогового пикселя
            return im, mat[ss // 2::ss, ss // 2::ss][:h, :w].copy()
        return im
