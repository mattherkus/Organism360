"""Импорт анатомических 3D-моделей органов из Human Reference Atlas (HuBMAP) и атласа головы и шеи
Open Anatomy (Harvard SPL) в organism_atlas/models/mesh/. Обработка та же, что у BodyParts3D
(tools/bp3d_import.py: упрощение, сглаживание, отбор видимых частей, масштаб, цвета).

Источники:
  * Human Reference Atlas, 3D Reference Organs (по данным Visible Human), CC BY 4.0:
    https://humanatlas.io/3d-reference-library, файлы
    https://cdn.humanatlas.io/digital-objects/ref-organ/<орган>/<версия>/assets/<файл>.glb
  * Open Anatomy / SPL, CT-based Atlas of the Head and Neck (2016-09), 3D Slicer License, Part B:
    https://www.openanatomy.org/atlases/nac/head-neck-2016-09/models/<файл>.vtk

Запуск (из корня проекта):
    python tools/atlas_import.py <папка со скачанными файлами> [орган ...] [--out <папка>]

Оси: у GLB - метры, +x - к левому боку пациента, +y - вверх, +z - вперёд; у VTK - миллиметры,
RAS (+x - вправо, +y - вперёд, +z - вверх). Оба переводятся в оси проекта (x - влево, y - назад, z - вверх).
"""

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bp3d_import as bp                                       # noqa: E402
from mesh_formats import read_glb, read_vtk                     # noqa: E402

HRA = "Human Reference Atlas 3D Reference Organs (HuBMAP), based on the Visible Human Project, " \
      "licensed under CC Attribution 4.0 International"
SPL = "CT-based Atlas of the Head and Neck, Surgical Planning Laboratory (Brigham and Women's Hospital), " \
      "Open Anatomy Project; 3D Slicer License, Part B"

# орган -> файлы, правила групп (регулярное выражение по названию части -> группа, None - не брать),
# вид новых групп, источник; weld - группы, части которых - лоскуты одной поверхности с общими вершинами
# на границах: они свариваются в одну сетку, иначе после упрощения по отдельности между ними видны швы
TUBES = ["3d-vh-f-fallopian-tube-l.glb", "3d-vh-f-fallopian-tube-r.glb"]
OVARIES = ["3d-vh-f-ovary-l.glb", "3d-vh-f-ovary-r.glb"]
FEMALE_RULES = [(r"cervicovaginal", None), (r"ovary", "ovary"),
                (r"tube|fibria|infundibulum|ampulla|ostium", "tube"), (r"cervi", "cervix"), (r"", "uterus")]
FEMALE_WELD = ["uterus", "cervix", "tube"]

RECIPES = {
    "spleen": {"files": ["3d-vh-m-spleen.glb"], "rules": [(r"", "spleen")], "weld": ["spleen"],
               "looks": {"spleen": ("#7e3253", "liver", 0.55)}, "src": HRA},
    "prostate": {"files": ["3d-vh-m-prostate.glb"], "rules": [(r"stroma", "stroma"), (r"", "prostate")],
                 "looks": {"prostate": ("#bb796b", "gland", 0.45), "stroma": ("#c9a27e", "muscle", 0.45)}, "src": HRA},
    # матка - вместе с трубами и яичниками (как в учебнике), яичники - то же, но в цвете только они
    "uterus": {"files": ["3d-vh-f-uterus.glb"] + TUBES + OVARIES, "rules": FEMALE_RULES, "weld": FEMALE_WELD,
               "looks": {"uterus": ("#d6738a", "muscle", 0.5), "cervix": ("#e0899b", "muscle", 0.45),
                         "tube": ("#e0899b", "smooth", 0.4), "ovary": ("#ebbcae", "gland", 0.45)}, "src": HRA},
    "ovaries": {"files": ["3d-vh-f-uterus.glb"] + TUBES + OVARIES, "rules": FEMALE_RULES, "weld": FEMALE_WELD,
                "looks": {"ovary": ("#f0b49a", "gland", 0.5), "tube": ("#b98f99", "smooth", 0.3),
                          "uterus": ("#a9858e", "smooth", 0.3), "cervix": ("#a9858e", "smooth", 0.3)}, "src": HRA},
    "thyroid": {"files": ["Model_118_thyroid_gland.vtk", "Model_120_cricoid_cartilage.vtk"],
                "rules": [(r"gland", "thyroid"), (r"", "cartilage")],
                "looks": {"thyroid": ("#b84a46", "gland", 0.45), "cartilage": ("#dfe6ea", "smooth", 0.4)}, "src": SPL},
    # поверхность лёгкого в атласе - лоскуты бронхолёгочных сегментов: они свариваются в одну поверхность
    "lungs": {"files": ["3d-vh-m-lung.glb", "3d-vh-m-trachea.glb"],
              "rules": [(r"segment", "lung"), (r"hilum", None), (r"bronch|trache|carina|cartilage", "airway"),
                        (r"", "lung")], "weld": ["lung"], "src": HRA},
    # кандидаты, которые проиграли сравнению с BodyParts3D (можно собрать в другую папку через --out)
    "trachea_hra": {"files": ["3d-vh-m-trachea.glb"], "rules": [(r"cartilage", "cartilage"), (r"", "trachea")],
                    "looks": {"trachea": ("#d7dfe4", "smooth", 0.4), "cartilage": ("#dfe6ea", "smooth", 0.4)},
                    "src": HRA, "organ": "trachea"},
    "rectum_hra": {"files": ["3d-sbu-m-large-intestine.glb"],
                   "rules": [(r"rectum", "rectum"), (r"sigmoid", "colon"), (r"", None)],
                   "looks": {"rectum": ("#cf7a66", "bowel", 0.45), "colon": ("#d27a50", "bowel", 0.4)},
                   "src": HRA, "organ": "rectum"},
    "appendix_hra": {"files": ["3d-sbu-m-large-intestine.glb"],
                     "rules": [(r"appendix", "appendix"), (r"caecum|ileocecal|ascending", "colon"), (r"", None)],
                     "looks": {"appendix": ("#e8a77f", "bowel", 0.45), "colon": ("#dd9269", "bowel", 0.5)},
                     "src": HRA, "organ": "appendix"},
}
ADOPTED = ["spleen", "prostate", "uterus", "ovaries", "thyroid", "lungs"]      # что собирается по умолчанию


def to_project(path, parts):
    """части файла - в миллиметры и оси проекта"""
    out = []
    for name, V, F in parts:
        if path.suffix == ".glb":
            V = np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1) * 1000.0
        else:
            V = np.stack([-V[:, 0], -V[:, 1], V[:, 2]], 1)
        out.append((name, V, F))
    return out


def closed(F):
    """каждое ребро - ровно у двух треугольников"""
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def orient(parts):
    """грани наружу. Замкнутая часть - по знаку её объёма. Открытые части одного файла (лоскуты одной
    поверхности, например стороны селезёнки) - все вместе: по знаку объёма, который они замыкают;
    у отдельного вогнутого лоскута знак «от центра» был бы неверным"""
    out, loose = [], []
    for name, V, F in parts:
        if closed(F):
            out.append((name, V, bp.orient_outward(V, F)))
        else:
            loose.append((name, V, F))
    if loose:
        c = np.concatenate([V for _, V, _ in loose]).mean(0)
        vol = sum(float(np.einsum("ij,ij->", V[F[:, 0]] - c, np.cross(V[F[:, 1]] - c, V[F[:, 2]] - c)))
                  for _, V, F in loose)
        out += [(n, V, F[:, ::-1] if vol < 0 else F) for n, V, F in loose]
    return out


def weld(parts, groups, group_of):
    """части групп groups - в одну сетку на группу; совпадающие (до 0,01 мм) вершины - в одну"""
    out, merged = [], {}
    for n, V, F in parts:
        if group_of(n) in groups:
            merged.setdefault(group_of(n), []).append((V, F))
        else:
            out.append((n, V, F))
    for g, items in merged.items():
        off = np.cumsum([0] + [len(V) for V, _ in items])
        V = np.concatenate([V for V, _ in items])
        F = np.concatenate([F + o for (_, F), o in zip(items, off)])
        _, first, inv = np.unique(np.round(V * 100).astype(np.int64), axis=0, return_index=True, return_inverse=True)
        F = inv.reshape(-1)[F]
        F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
        out.append((g + " (welded)", V[first], F))
    return out


def build(name, src, out=None):
    r = RECIPES[name]
    organ = r.get("organ", name)
    group_of = lambda n: next(g for rx, g in r["rules"] if re.search(rx, n, re.I))
    parts = []
    for fn in r["files"]:
        path = src / fn
        raw = read_glb(path) if path.suffix == ".glb" else read_vtk(path, path.stem)
        raw = [(n, V, F) for n, V, F in to_project(path, raw) if len(F) and group_of(n) is not None]
        parts += orient(weld(raw, r.get("weld", ()), group_of))
    if out is not None:
        bp.OUT = Path(out)
    return bp.finish(organ, parts, group_of, r["src"], "Human Reference Atlas" if r["src"] == HRA else
                     "атласа головы и шеи Open Anatomy (SPL)", "tools/atlas_import.py", looks=r.get("looks"),
                     inflate=r.get("inflate", {}))


def main():
    args = sys.argv[1:]
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    src = Path(args[0])
    for name in [a for a in args[1:] if not a.startswith("-")] or ADOPTED:
        dropped = build(name, src, out)
        if "-v" in args:
            print("   hidden, dropped:", "; ".join(dropped))


if __name__ == "__main__":
    main()
