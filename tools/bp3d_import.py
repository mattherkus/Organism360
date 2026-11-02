"""Импорт анатомических 3D-моделей органов из BodyParts3D в organism_atlas/models/mesh/.

Источник: BodyParts3D, © The Database Center for Life Science, CC BY 4.0
https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html
Нужны файлы partof_element_parts.txt и partof_BP3D_4.0_obj_99.zip (PART-OF tree, 99% reduction).

Запуск (из корня проекта):
    python tools/bp3d_import.py <папка со скачанными файлами> [орган ...] [--out <папка>]

Что делает с каждым органом:
  1. собирает его части (OBJ) по списку FMA-понятий из ORGANS;
  2. разворачивает грани наружу и переводит миллиметры в единицы сцены (размер как у старой модели);
  3. упрощает сетку кластеризацией вершин (части из WELD - вместе, чтобы не было швов),
     грубые сетки подразделяет, всё сглаживает фильтром Таубина (без усадки);
     поверхности из ENVELOPE строятся как гладкая оболочка вокруг облака точек: у лёгких
     в BodyParts3D 4.0 поверхности нет (только бронхи и сосуды), и она восстанавливается вокруг
     этого дерева;
  4. рендерит орган с 26 направлений и выбрасывает части, которых снаружи не видно
     (клапаны, желудочки мозга, сосуды внутри печени, бронхи внутри лёгких);
  5. раскрашивает части по названиям (правила RULES) и объединяет их в группы материалов;
  6. пишет models/mesh/<орган>.npz (геометрия) и <орган>.json (группы, цвета - можно править руками).
Оси BodyParts3D совпадают с осями проекта: x - к левому боку пациента, y - назад, z - вверх.
"""

import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from organism_atlas.models import load_procedural                    # noqa: E402
from organism_atlas.render3d.meshraster import vertex_normals        # noqa: E402
from organism_atlas.render3d.scene import Scene3D                    # noqa: E402

OUT = ROOT / "organism_atlas" / "models" / "mesh"
ATTRIBUTION = "BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International"

# орган проекта -> FMA-понятия BodyParts3D (PART-OF tree)
ORGANS = {
    "heart": ["FMA7088"],
    "brain": ["FMA50801"],
    "liver": ["FMA7197"],                                               # печень (без жёлчного пузыря)
    "gallbladder": ["FMA7202"],                                         # жёлчный пузырь
    "lungs": ["FMA7309", "FMA7310", "FMA7394", "FMA7395", "FMA7396"],   # лёгкие, трахея, главные бронхи
    "stomach": ["FMA7148"],
    "intestines": ["FMA7200", "FMA7201"],
    "kidneys": ["FMA7204", "FMA7205", "FMA14752", "FMA14753", "FMA15571", "FMA15572"],  # + почечные артерии, мочеточники
    "pancreas": ["FMA7198", "FMA7206", "FMA14773"],          # + двенадцатиперстная кишка, селезёночная артерия
    "bladder": ["FMA15900"],
    "adrenals": ["FMA15629", "FMA15630", "FMA7204", "FMA7205"],     # надпочечники на верхушках почек
    "esophagus": ["FMA7131", "FMA7148"],                             # пищевод и (для ориентира) желудок
    "rectum": ["FMA14544"],
    "appendix": ["FMA14542", "FMA14541"],                            # аппендикс и слепая кишка
    "trachea": ["FMA7394", "FMA7395", "FMA7396"],                    # трахея и главные бронхи
    # аорта и устья её ветвей: плечеголовной ствол, левые общая сонная и подключичная, чревный ствол,
    # верхняя брыжеечная, почечные и общие подвздошные артерии (дальше ветви обрезаны правилами RULES)
    "aorta": ["FMA3734", "FMA3932", "FMA4058", "FMA4694", "FMA14812", "FMA14749", "FMA14752", "FMA14753",
              "FMA14765", "FMA14766"],
    # полые вены и впадающие в них: плечеголовные, общие подвздошные, печёночные, непарная
    "vena_cava": ["FMA10951", "FMA4720", "FMA4751", "FMA4761", "FMA21387", "FMA21388", "FMA14338", "FMA14339",
                  "FMA4838"],
    "diaphragm": ["FMA13295"],
    "pituitary": ["FMA13889"],
    "thymus": ["FMA9607"],
}
# органы, модели которых теперь берутся из другого источника (tools/atlas_import.py): по умолчанию
# не собираются, только если назвать их явно
REPLACED = {"lungs", "liver", "gallbladder", "bladder"}
FACE_BUDGET = 45000            # треугольников на орган после упрощения
# сосуды сердца утоплены в стенку; сегменты печени разделены щелями - раздуваем, чтобы перекрылись
INFLATE = {"heart": {"artery": 1.0, "vein": 1.0}, "liver": {"parenchyma": 1.2}}
COARSE_EDGE = 1 / 70          # части со средним ребром длиннее этой доли органа подразделяются
# оболочки: имя новой части, откуда брать точки (FMA-понятия или группа), размытие и шаг решётки
# в мм, доля точек внутри; replace - убрать исходные части группы (их заменяет оболочка)
ENVELOPE = {
    "lungs": [
        {"name": "Right lung surface (reconstructed)", "from": ["FMA7309"], "sigma": 28, "cell": 3, "cover": 0.99},
        {"name": "Left lung surface (reconstructed)", "from": ["FMA7310"], "sigma": 28, "cell": 3, "cover": 0.99},
    ],
}
SMOOTH_ITERS = 4

# группы материалов: (регулярное выражение по английскому названию части, группа); первое совпадение
RULES = {
    "heart": [(r"coronary artery|artery", "artery"), (r"vein|sinus", "vein"),
              (r"aort|pulmonary trunk|vena cava", "vessel"), (r"", "myocardium")],
    "brain": [(r"cerebell", "cerebellum"), (r"pons|medulla|midbrain|brainstem", "brainstem"), (r"", "cortex")],
    "gallbladder": [(r"", "gallbladder")],
    "liver": [(r"gallbladder|cystic", "gallbladder"), (r"artery", "artery"), (r"portal|vein", "vein"),
              (r"biliary|bile|hepatic duct", "bile"), (r"", "parenchyma")],     # Liver surface - parenchyma
    "lungs": [(r"trachea|bronch", "airway"), (r"artery|arterial", "artery"), (r"vein", "vein"), (r"", "lung")],
    "stomach": [(r"", "wall")],
    "intestines": [(r"taenia", "taenia"), (r"colon|rectum|cecum|appendix|ileocecal", "colon"), (r"", "small")],
    "kidneys": [(r"artery", "artery"), (r"ureter", "ureter"), (r"", "kidney")],
    # None - не брать (проток внутри железы)
    "pancreas": [(r"duct", None), (r"duoden", "duodenum"), (r"artery", "artery"), (r"", "gland")],
    "bladder": [(r"", "wall")],
    "adrenals": [(r"adrenal|suprarenal", "adrenal"), (r"kidney|renal", "kidney_dim")],
    "esophagus": [(r"esophag", "esophagus"), (r"", "stomach_dim")],
    "rectum": [(r"", "rectum")],
    "appendix": [(r"appendix", "appendix"), (r"", "cecum")],
    "trachea": [(r"", "airway")],
    # в понятия аорты и вен входит всё дерево сосудов до кистей и стоп: берём только названные
    "aorta": [(r"valve|cusp|sinus", None), (r"aort", "aorta"),
              (r"^(brachiocephalic artery|left common carotid artery|left subclavian artery|celiac trunk"
               r"|trunk of superior mesenteric artery|right renal artery|trunk of left renal artery"
               r"|(left|right) common iliac artery)$", "branch"), (r"", None)],
    "vena_cava": [(r"vena cava", "cava"),
                  (r"^((left|right) brachiocephalic vein|(left|right) common iliac vein|azygos vein"
                   r"|(left|right|middle) hepatic vein)$", "tributary"), (r"", None)],
    "diaphragm": [(r"", "diaphragm")],
    "pituitary": [(r"", "pituitary")],
    "thymus": [(r"", "thymus")],
}
# вид групп: цвет (sRGB), текстура и блеск - те же понятия, что в procedural-моделях
LOOKS = {
    "myocardium": ("#8a2f2b", "muscle", 0.5), "artery": ("#d24a3c", "smooth", 0.6),
    "vein": ("#4a3d78", "smooth", 0.55), "vessel": ("#b53a40", "smooth", 0.55),
    "cortex": ("#e2a3ae", "gyri", 0.3), "cerebellum": ("#cf8d9c", "folia", 0.28), "brainstem": ("#d8aeb2", "smooth", 0.3),
    "parenchyma": ("#7b2d26", "liver", 0.55), "gallbladder": ("#4f8a3c", "smooth", 0.5), "bile": ("#6aa04a", "smooth", 0.4),
    "airway": ("#dfe2e0", "smooth", 0.4), "lung": ("#e08a9a", "lung", 0.22),
    "wall": None,                                        # цвет стенки берётся из старой модели органа
    "taenia": ("#c98a5c", "bowel", 0.4), "colon": ("#d27a50", "bowel", 0.4), "small": ("#ee9f8a", "bowel", 0.5),
    "kidney": ("#a2384a", "smooth", 0.5), "ureter": ("#e6d28a", "smooth", 0.45),
    "duodenum": ("#ee9f8a", "bowel", 0.45), "gland": ("#ecb688", "gland", 0.4),
    "adrenal": ("#dda03a", "gland", 0.45), "kidney_dim": ("#ad3b4d", "smooth", 0.45),
    "esophagus": ("#cc7a70", "muscle", 0.5), "stomach_dim": ("#c79a8c", "smooth", 0.35), "rectum": ("#cf7a66", "bowel", 0.45),
    "appendix": ("#e8a77f", "bowel", 0.45), "cecum": ("#dd9269", "bowel", 0.5),
    "aorta": ("#d24a3c", "smooth", 0.6), "branch": ("#b9564b", "smooth", 0.45),
    "cava": ("#4d6fb8", "smooth", 0.5), "tributary": ("#6f88c4", "smooth", 0.42),
    "diaphragm": ("#b5534d", "muscle", 0.45), "pituitary": ("#df8d5c", "gland", 0.5), "thymus": ("#d79a9c", "gland", 0.4),
}


# ----------------------------------------------------------------------------------- чтение
def read_obj(text):
    name = re.search(r"# English name : (.*)", text)
    vs, fs = [], []
    for ln in text.splitlines():
        if ln.startswith("v "):
            vs.append(ln.split()[1:4])
        elif ln.startswith("f "):
            idx = [int(t.split("/")[0]) for t in ln.split()[1:]]
            for k in range(1, len(idx) - 1):                     # многоугольники -> треугольники
                fs.append((idx[0], idx[k], idx[k + 1]))
    V = np.asarray(vs, np.float64)
    F = np.asarray(fs, np.int64) - 1
    return (name.group(1).strip() if name else "?"), V, F


def orient_outward(V, F):
    """закрытая часть: знак объёма показывает, куда смотрят грани; разворачиваем наружу"""
    vol = np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]])).sum()
    return F[:, ::-1] if vol < 0 else F


# ----------------------------------------------------------------------------------- упрощение
def cluster(V, F, cell):
    """упрощение кластеризацией вершин по решётке с шагом cell"""
    key = np.floor((V - V.min(0)) / cell).astype(np.int64)
    key = key[:, 0] * 1_000_003 ** 2 + key[:, 1] * 1_000_003 + key[:, 2]
    _, inv = np.unique(key, return_inverse=True)
    inv = inv.reshape(-1)
    n = inv.max() + 1
    NV = np.zeros((n, 3))
    np.add.at(NV, inv, V)
    NV /= np.bincount(inv, minlength=n)[:, None]
    NF = inv[F]
    ok = (NF[:, 0] != NF[:, 1]) & (NF[:, 1] != NF[:, 2]) & (NF[:, 0] != NF[:, 2])
    NF = NF[ok]
    _, first = np.unique(np.sort(NF, 1), axis=0, return_index=True)
    NF = NF[np.sort(first)]
    used = np.unique(NF)
    remap = np.full(n, -1)
    remap[used] = np.arange(len(used))
    return NV[used], remap[NF]


def taubin(V, F, iters, lam=0.5, mu=-0.53):
    """сглаживание без усадки: шаг к среднему соседей, затем шаг обратно"""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    deg = np.bincount(e[:, 0], minlength=len(V)).astype(np.float64)[:, None]
    deg[deg == 0] = 1
    for _ in range(iters):
        for f in (lam, mu):
            avg = np.zeros_like(V)
            np.add.at(avg, e[:, 0], V[e[:, 1]])
            V = V + f * (avg / deg - V)
    return V


def subdivide(V, F):
    """каждый треугольник делится на четыре по серединам рёбер"""
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    uniq, inv = np.unique(e, axis=0, return_inverse=True)
    ab, bc, ca = len(V) + inv.reshape(3, -1)
    a, b, c = F.T
    NF = np.concatenate([np.stack(t, 1) for t in ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca))])
    return np.concatenate([V, (V[uniq[:, 0]] + V[uniq[:, 1]]) / 2]), NF


def blur3d(g, s):
    """гауссово размытие объёма через FFT (s - в ячейках)"""
    k = [np.fft.fftfreq(n) for n in g.shape[:2]] + [np.fft.rfftfreq(g.shape[2])]
    r2 = k[0][:, None, None] ** 2 + k[1][None, :, None] ** 2 + k[2][None, None, :] ** 2
    return np.fft.irfftn(np.fft.rfftn(g) * np.exp(-2 * (np.pi * s) ** 2 * r2), s=g.shape, axes=(0, 1, 2))


def surface_nets(F, lo, cell):
    """поверхность уровня F = 0 (внутри F > 0): вершина в каждой ячейке, через которую проходит
    поверхность (среднее точек пересечения её рёбер), два треугольника на каждое пересечённое ребро решётки"""
    ins = F > 0
    n = np.array(F.shape)
    corners = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    cin = np.stack([ins[i:n[0] - 1 + i, j:n[1] - 1 + j, k:n[2] - 1 + k] for i, j, k in corners])
    active = cin.any(0) & ~cin.all(0)
    ai = np.nonzero(active)
    vid = np.full(active.shape, -1, np.int64)
    vid[ai] = np.arange(len(ai[0]))
    acc = np.zeros((len(ai[0]), 3))
    cnt = np.zeros(len(ai[0]))
    base = np.stack(ai, 1).astype(np.float64)
    for a in range(8):
        for b in range(a + 1, 8):
            d = np.array(corners[b]) - np.array(corners[a])
            if np.abs(d).sum() != 1:
                continue                                       # только 12 рёбер куба
            ia = tuple(ai[q] + corners[a][q] for q in range(3))
            ib = tuple(ai[q] + corners[b][q] for q in range(3))
            fa, fb = F[ia], F[ib]
            x = (fa > 0) != (fb > 0)
            t = np.where(x, fa / np.where(x, fa - fb, 1), 0)
            pos = base + np.array(corners[a]) + t[:, None] * d[None, :]
            acc[x] += pos[x]
            cnt[x] += 1
    V = lo + cell * acc / np.maximum(cnt, 1)[:, None]
    faces = []
    for ax in range(3):
        b, c = (ax + 1) % 3, (ax + 2) % 3
        sl0, sl1 = [slice(None)] * 3, [slice(None)] * 3
        sl0[ax], sl1[ax] = slice(0, n[ax] - 1), slice(1, n[ax])
        ch = ins[tuple(sl0)] != ins[tuple(sl1)]
        inner = [slice(None)] * 3
        inner[b], inner[c] = slice(1, n[b] - 1), slice(1, n[c] - 1)
        idx = list(np.nonzero(ch[tuple(inner)]))
        idx[b] = idx[b] + 1
        idx[c] = idx[c] + 1
        flip = ins[tuple(idx)]
        quad = []
        for db, dc in ((-1, -1), (0, -1), (0, 0), (-1, 0)):
            q = list(idx)
            q[b] = q[b] + db
            q[c] = q[c] + dc
            quad.append(vid[tuple(q)])
        q0, q1, q2, q3 = quad
        tri = np.concatenate([np.stack([q0, q1, q2], 1), np.stack([q0, q2, q3], 1)])
        fl = np.concatenate([flip, flip])
        tri[fl] = tri[fl][:, ::-1]
        faces.append(tri)
    Fm = np.concatenate(faces)
    return V, Fm[(Fm >= 0).all(1)]


def largest_component(V, F):
    """самый большой связный кусок сетки (по числу треугольников)"""
    lab = np.arange(len(V))
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    while True:                                   # метки стекают к минимуму по рёбрам
        new = lab.copy()
        np.minimum.at(new, e[:, 0], lab[e[:, 1]])
        np.minimum.at(new, e[:, 1], lab[e[:, 0]])
        new = new[new]
        if (new == lab).all():
            break
        lab = new
    fl = lab[F[:, 0]]
    F = F[fl == np.bincount(fl).argmax()]
    used = np.unique(F)
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    return V[used], remap[F]


def envelope(P, cell=2.0, sigma=7.0, cover=0.985):
    """гладкая оболочка вокруг облака точек: размытая плотность точек, а уровень такой,
    чтобы внутри оказалась доля cover точек. Остаётся самый большой связный кусок
    (у полой оболочки это наружная поверхность)"""
    lo = P.min(0) - 4 * sigma
    dims = np.ceil((P.max(0) + 4 * sigma - lo) / cell).astype(int) + 1
    g = np.zeros(dims)
    idx = np.clip(np.round((P - lo) / cell).astype(int), 0, dims - 1)
    np.add.at(g, tuple(idx.T), 1.0)
    field = blur3d(g, sigma / cell)
    level = np.quantile(field[tuple(idx.T)], 1 - cover)
    V, F = largest_component(*surface_nets(field - level, lo, cell))
    return V, orient_outward(V, F)


def drop_outliers(parts):
    """части, лежащие далеко от основной массы органа (в архиве попадаются оторванные кусочки)"""
    allV = np.concatenate([V for _, V, _ in parts])
    lo, hi = np.percentile(allV, 1, 0), np.percentile(allV, 99, 0)
    pad = 0.15 * (hi - lo)
    ok = lambda V: bool(((V.mean(0) > lo - pad) & (V.mean(0) < hi + pad)).all())
    return [p for p in parts if ok(p[1])], sorted(p[0] for p in parts if not ok(p[1]))


def unfold_faces(V, F, rounds=3):
    """сетка без граней, нормаль которых смотрит против нормалей их вершин (складки после упрощения), и без
    оставшихся от них лишних вершин; после удаления нормали вершин пересчитываются - в несколько проходов"""
    for _ in range(rounds):
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        ok = (fn * vertex_normals(V, F)[F].mean(1)).sum(1) > 0
        if ok.all():
            break
        F = F[ok]
    used, F = np.unique(F, return_inverse=True)
    return V[used], F.reshape(-1, 3)


# ----------------------------------------------------------------------------------- видимость
def visible_parts(parts, size=260):
    """номера частей, которые видны снаружи хотя бы с одного из 26 направлений"""
    scene = Scene3D([{"k": "m", "v": V, "f": F, "vn": None, "color": "#808080", "tex": "smooth", "gloss": 0.3}
                     for _, V, F in parts])
    seen = np.zeros(len(parts))
    total = 0
    dirs = [(az, el) for el in (-55, 0, 55) for az in range(0, 360, 45)] + [(0, 89), (0, -89)]
    for az, el in dirs:
        a, e = np.radians(az), np.radians(el)
        cam = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
        right = np.array([-np.sin(a), np.cos(a), 0.0])
        up = np.cross(cam, right)
        scale = 0.5 * size / scene.radius
        _, _, mat, _, _, _ = scene._raster(size, size, cam, right, up, scale, size / 2, size / 2, 1)
        cnt = np.bincount(mat[mat >= 0].astype(np.int64), minlength=len(parts))
        total = max(total, int(cnt.sum()))
        seen = np.maximum(seen, cnt)
    return [i for i in range(len(parts)) if seen[i] >= max(4, 0.0015 * total)]


# ----------------------------------------------------------------------------------- орган
def build(organ, z, elements, names_by_fj):
    group_of = lambda n: next(g for rx, g in RULES[organ] if re.search(rx, n, re.I))
    parts, by_fj = [], {}
    for fj in sorted({f for c in ORGANS[organ] for f in elements[c]}):
        name, V, F = read_obj(z.read(names_by_fj[fj]).decode("utf-8", "replace"))
        if len(F):
            by_fj[fj] = V
            if group_of(name) is not None:
                parts.append((name, V, orient_outward(V, F)))
    parts, outliers = drop_outliers(parts)
    kept_v = {id(V) for _, V, _ in parts}
    for env in ENVELOPE.get(organ, []):
        if isinstance(env["from"], str):             # точки частей группы
            src = [p for p in parts if group_of(p[0]) == env["from"]]
            pts = np.concatenate([V for _, V, _ in src])
            if env.get("replace"):
                parts = [p for p in parts if group_of(p[0]) != env["from"]]
        else:                                        # точки всех частей понятий (без выбросов)
            pts = np.concatenate([by_fj[f] for c in env["from"] for f in elements[c]
                                  if f in by_fj and id(by_fj[f]) in kept_v])
        parts.append((env["name"], *envelope(pts, env["cell"], env["sigma"], env["cover"])))
    return finish(organ, parts, group_of, ATTRIBUTION, "BodyParts3D", "tools/bp3d_import.py", outliers)


def finish(organ, parts, group_of, attribution, source, tool, outliers=(), looks=None, budget=FACE_BUDGET,
           inflate=None, detail=1, unfold=False):
    """общая часть импорта для любого источника: parts - [(название части, V, F)] в миллиметрах
    в осях проекта, group_of(название) - группа материала (None - не брать).
    detail > 1 - мельче начальная решётка упрощения: для органа, вытянутого во много раз длиннее своей
    толщины (спинной мозг с корешками); {группа: во сколько раз мельче} - только для тонких частей
    (сеть сосудов), остальные упрощаются под бюджет как обычно.
    unfold - убрать грани, сложенные упрощением (тонкая трубка схлопнулась в лист): их нормаль смотрит против
    нормалей вершин, и такие грани рисуются тёмными пятнами или пропадают при отсечении задних граней.
    Упрощение под бюджет треугольников, сглаживание, отбор видимых снаружи частей, масштаб
    как у процедурной модели, запись models/mesh/<орган>.npz и .json"""
    looks = {**LOOKS, **(looks or {})}
    parts = [p for p in parts if group_of(p[0]) is not None]
    allV = np.concatenate([V for _, V, _ in parts])
    ext = float(np.linalg.norm(allV.max(0) - allV.min(0)))
    total = sum(len(F) for *_, F in parts)

    edge = lambda V, F: float(np.linalg.norm(V[F[:, 1]] - V[F[:, 0]], axis=1).mean())
    coarse = {n for n, V, F in parts if edge(V, F) > COARSE_EDGE * ext}     # грубые уже в архиве

    # упрощение: шаг решётки подбираем под бюджет треугольников
    finer = detail if isinstance(detail, dict) else {}
    cell = ext / (260 * (1 if finer else detail))
    while True:
        simp = [(n, *cluster(V, F, cell / finer.get(group_of(n), 1))) for n, V, F in parts]
        simp = [(n, V, F) for n, V, F in simp if len(F) >= 4]
        nf = sum(len(F) for *_, F in simp)
        if nf <= budget * 1.6:                 # невидимые части ещё отсеются
            break
        cell *= 1.18
    for i, (n, V, F) in enumerate(simp):           # грубые сетки: подразделить, потом сгладятся
        k = 0
        while n in coarse and edge(V, F) > COARSE_EDGE * ext and len(F) * 4 <= budget and k < 3:
            V, F = subdivide(V, F)
            k += 1
        simp[i] = (n, taubin(V, F, SMOOTH_ITERS * (1 + 2 * k)), F)
    infl = INFLATE.get(organ, {}) if inflate is None else inflate
    simp = [(n, V + infl[group_of(n)] * vertex_normals(V, F), F) if group_of(n) in infl else (n, V, F)
            for n, V, F in simp]
    if unfold:
        simp = [(n, *unfold_faces(V, F)) for n, V, F in simp]
        simp = [(n, V, F) for n, V, F in simp if len(F) >= 4]
    vis = visible_parts(simp)
    kept = [simp[i] for i in vis]
    dropped = sorted({simp[i][0] for i in range(len(simp)) if i not in vis}) + ["[outlier] " + o for o in outliers]

    # масштаб как у старой модели: размер сцены и тексту́ры рассчитаны на него
    ref = Scene3D(load_procedural(organ)).radius
    kv = np.concatenate([V for _, V, _ in kept])
    ctr = (kv.max(0) + kv.min(0)) / 2
    s = ref / (float(np.linalg.norm(kv.max(0) - kv.min(0)) / 2) * 0.93)

    wall = next((p["color"] for p in load_procedural(organ)), "#c08080")
    groups = defaultdict(list)
    for n, V, F in kept:
        groups[group_of(n)].append((n, (V - ctr) * s, F))
    arrays, meta = {}, []
    for gi, (g, items) in enumerate(sorted(groups.items())):
        Vs, Fs, off = [], [], 0
        for _, V, F in items:
            Vs.append(V)
            Fs.append(F + off)
            off += len(V)
        V, F = np.concatenate(Vs), np.concatenate(Fs)
        VN = np.concatenate([vertex_normals(v, f - o) for (_, v, _), f, o in
                             zip(items, Fs, np.cumsum([0] + [len(v) for _, v, _ in items])[:-1])])
        arrays["v%d" % gi] = V.astype(np.float32)
        arrays["f%d" % gi] = F.astype(np.int32)
        arrays["n%d" % gi] = VN.astype(np.float16)
        color, tex, gloss = looks[g] or (wall, "muscle", 0.45)
        meta.append({"group": g, "color": color, "texture": tex, "gloss": gloss,
                     "triangles": int(len(F)), "source_parts": sorted({n for n, *_ in items})})
    OUT.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    (OUT / (organ + ".npz")).write_bytes(buf.getvalue())
    model = {"_comment": "Анатомическая модель из %s. Цвет, текстуру и блеск групп можно менять; "
                         "геометрия в %s.npz (пересобрать: %s)." % (source, organ, tool),
             "attribution": attribution, "mesh": organ + ".npz", "groups": meta}
    (OUT / (organ + ".json")).write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kept_faces = sum(m["triangles"] for m in meta)
    print("%-10s %6d -> %5d triangles, %3d of %3d parts kept, %4.0f KB; groups: %s" % (
        organ, total, kept_faces, len(kept), len(simp), len(buf.getvalue()) / 1024,
        ", ".join("%s %d" % (m["group"], m["triangles"]) for m in meta)))
    return dropped


def main():
    global OUT
    args = sys.argv[1:]
    if "--out" in args:                              # собрать в другую папку (например, для сравнения)
        i = args.index("--out")
        OUT = Path(args[i + 1])
        del args[i:i + 2]
    src = Path(args[0])
    only = [a for a in args[1:] if not a.startswith("-")] or [o for o in ORGANS if o not in REPLACED]
    elements = defaultdict(list)
    for line in (src / "partof_element_parts.txt").read_text(encoding="utf-8").splitlines()[1:]:
        cid, _, fj = line.split("\t")
        elements[cid].append(fj)
    with zipfile.ZipFile(src / "partof_BP3D_4.0_obj_99.zip") as z:
        names_by_fj = {Path(n).stem: n for n in z.namelist() if n.endswith(".obj")}
        for organ in only:
            dropped = build(organ, z, elements, names_by_fj)
            if "-v" in sys.argv:
                print("   hidden, dropped:", "; ".join(dropped))


if __name__ == "__main__":
    main()
