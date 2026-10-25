"""Эталонные картинки схемы и 3D-моделей для регрессионных тестов.

    python tools/make_golden.py                  # tests/golden/2d и tests/golden/3d
    python tools/make_golden.py --out <папка>    # куда-то ещё (например, чтобы сравнить с эталоном)

2D, для каждого масштаба Z (1.0 и 0.7): full.png - схема целиком (фон тёмной темы), base.png - схема
без органов (кожа, кости, вены, артерии), <орган>.png - RGBA органа и origins.json - где он лежит.
3D: <орган>.png - кадр с углом просмотра по умолчанию.
Эталоны не перезаписываются молча: существующий файл оставляется, если не передан --force.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from organism_atlas.atlas import build_atlas, to_u8  # noqa: E402
from organism_atlas.body.base import background, compose, over  # noqa: E402
from organism_atlas.organs import ORDER, ORGANS  # noqa: E402

ZOOMS = (1.0, 0.7)
VIEW_3D = dict(w=200, h=160, az=-62, el=18)
ORGANS_3D = ("lungs", "liver", "stomach", "intestines", "kidneys", "heart", "brain")


def save(img, path, force):
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return True


def golden_2d(out, force):
    for Z in ZOOMS:
        d = out / "2d" / ("z%.1f" % Z)
        body, organs = build_atlas(Z)
        back = background(Z)
        base = compose(body, back)
        save(Image.fromarray(to_u8(base)), d / "base.png", force)
        full = base.copy()
        for k in ORDER:
            (ox, oy), (h, w) = organs[k]["origin"], organs[k]["rgba"].shape[:2]
            over(full[oy:oy + h, ox:ox + w], organs[k]["rgba"])
        save(Image.fromarray(to_u8(full)), d / "full.png", force)
        origins = {}
        for k in ORDER:
            save(Image.fromarray(to_u8(organs[k]["rgba"]), "RGBA"), d / (k + ".png"), force)
            origins[k] = list(map(int, organs[k]["origin"]))
        p = d / "origins.json"
        if force or not p.exists():
            p.write_text(json.dumps(origins, indent=1), encoding="utf-8")
        print("2d z=%.1f: %s" % (Z, d))


def golden_3d(out, force, keys=ORGANS_3D):
    from organism_atlas.render3d.scene import Scene3D
    for k in keys:
        p = out / "3d" / (k + ".png")
        if p.exists() and not force:
            continue
        im = Scene3D(ORGANS[k]["parts"]()).render(VIEW_3D["w"], VIEW_3D["h"], VIEW_3D["az"], VIEW_3D["el"])
        save(im, p, True)
        print("3d:", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "tests" / "golden"))
    ap.add_argument("--force", action="store_true", help="перезаписать существующие файлы")
    ap.add_argument("--no-3d", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    golden_2d(out, a.force)
    if not a.no_3d:
        golden_3d(out, a.force)


if __name__ == "__main__":
    main()
