"""Кости и мышцы на схеме: реестр и маски для наведения и клика. Без Qt.

Кости и мышцы рисуются слоями тела (body/skeleton.py, body/muscles.py) - одним рисунком на слой. Чтобы по ним
можно было щёлкать, рисунок размечен вызовами K.part(ключ): masks() проигрывает те же вызовы, но каждую
отмеченную часть рисует в свою маску. Поэтому форма кости или мышцы для клика всегда совпадает с рисунком.
Тексты карточек - в разделе structures файлов lang/*.json (name, desc, location, facts), латынь - в la.json.
"""

import numpy as np

from .config import BONE_C, MUSCLE_C
from .geometry import H, W
from .render2d.layers import Layer

# порядок в карточках, панели и викторине: сверху вниз
BONES = ("skull", "mandible", "clavicle", "scapula", "sternum", "ribs", "spine", "humerus", "ulna", "radius",
         "carpals", "metacarpals", "phalanges", "pelvis", "sacrum", "femur", "patella", "tibia", "fibula", "foot")
MUSCLES = ("sternocleidomastoid", "scalenes", "sternohyoid", "trapezius", "deltoid", "pectoralis", "intercostals",
           "biceps", "brachioradialis", "pronator_teres", "flexor_carpi_radialis", "flexor_carpi_ulnaris",
           "rectus_abdominis", "external_oblique", "sartorius", "rectus_femoris", "vastus_lateralis",
           "vastus_medialis", "adductors", "tibialis_anterior", "gastrocnemius", "fibularis_longus")
KINDS = {"bone": BONES, "muscle": MUSCLES}
LAYER_OF = {"bone": "skeleton", "muscle": "muscles"}                  # слой тела, на котором они нарисованы
COLOR = {"bone": BONE_C, "muscle": MUSCLE_C}

# {ключ: {"kind": bone/muscle, "color": цвет полоски в карточке}}
STRUCTURES = {k: {"kind": kind, "color": COLOR[kind]} for kind, keys in KINDS.items() for k in keys}

# кто первым ловит клик, если части перекрываются (мелкие и лежащие сверху - первыми)
HIT_ORDER = ("phalanges", "metacarpals", "carpals", "patella", "foot", "mandible", "sternum", "clavicle", "sacrum",
             "fibula", "tibia", "femur", "ulna", "radius", "humerus", "spine", "pelvis", "ribs", "scapula", "skull",
             "sternohyoid", "scalenes", "sternocleidomastoid", "deltoid", "biceps", "pronator_teres",
             "flexor_carpi_radialis", "flexor_carpi_ulnaris", "brachioradialis", "pectoralis", "trapezius",
             "rectus_abdominis", "external_oblique", "sartorius", "vastus_medialis", "rectus_femoris",
             "vastus_lateralis", "adductors", "tibialis_anterior", "fibularis_longus", "gastrocnemius",
             "intercostals")
PAD = 3.0                                       # запас к рамке части: сглаженный контур выходит за опорные точки


def kind(key):
    return STRUCTURES[key]["kind"]


def keys(which=None):
    """ключи частей: which - bone, muscle или None (все)"""
    return list(KINDS[which]) if which else list(BONES + MUSCLES)


class _Sink:
    """карта высоты Ink - маскам не нужна: всё, что в неё рисуется, пропускается"""

    def __getattr__(self, _name):
        return lambda *a, **kw: None


class _Cover:
    """покрытие Ink: записывает рисование в текущую часть"""

    def __init__(self, rec):
        self.rec = rec

    def ellipse(self, cx, cy, rx, ry, v=255):
        self.rec.add(("ellipse", (cx, cy, rx, ry, v)), [(cx - rx, cy - ry), (cx + rx, cy + ry)])

    def poly(self, pts, v=255, smooth=True, closed=True):
        self.rec.add(("poly", (list(pts), v, smooth)), pts)

    def line(self, pts, width, v=255, smooth=True):
        self.rec.add(("line", (list(pts), width, v, smooth)), pts, width / 2)


class Recorder:
    """заменяет Ink для skeleton() и muscles(): запоминает, что и в какую часть рисуется"""

    def __init__(self):
        self.cur = None
        self.ops = {}                                   # {часть: [(операция, точки, запас)]}
        self.cov, self.hgt = _Cover(self), _Sink()

    def part(self, name):
        self.cur = name

    def add(self, op, pts, pad=0.0):
        if self.cur is not None:
            self.ops.setdefault(self.cur, []).append((op, [tuple(p) for p in pts], pad))

    def tube(self, pts, widths, n=14):
        w = max(widths) if not np.isscalar(widths) else widths
        self.add(("tube", (list(pts), widths)), pts, w / 2)

    def line(self, pts, width, smooth=True):
        self.tube(pts, [width] * len(pts))

    def disc(self, x, y, r):
        self.cov.ellipse(x, y, r, r)

    def poly(self, pts, smooth=True):
        self.cov.poly(pts, smooth=smooth)

    def cut(self, cx, cy, rx, ry):
        self.cov.ellipse(cx, cy, rx, ry, 0)


def record():
    """{часть: операции рисования} по разметке скелета и мышц"""
    from .body.muscles import muscles
    from .body.skeleton import skeleton
    rec = Recorder()
    skeleton(rec)
    rec.part(None)
    muscles(rec)
    return rec.ops


def masks(Z, ss=2):
    """{часть: {"hit": маска float32 0..1, "origin": (x, y)}} в пикселях схемы масштаба Z"""
    out = {}
    for key, ops in record().items():
        xs, ys = [], []
        for _op, pts, pad in ops:
            for x, y in pts:
                xs += [x - pad - PAD, x + pad + PAD]
                ys += [y - pad - PAD, y + pad + PAD]
        box = (max(0.0, min(xs)), max(0.0, min(ys)), min(float(W), max(xs)), min(float(H), max(ys)))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        L = Layer(box, Z, ss)
        for (name, args), _pts, _pad in ops:
            if name == "ellipse":
                L.ellipse(*args)
            elif name == "poly":
                pts, v, smooth = args
                L.poly(pts, v, smooth=smooth)
            elif name == "line":
                pts, width, v, smooth = args
                L.line(pts, width, v=v, smooth=smooth)
            else:
                L.tube(*args)
        out[key] = {"hit": L.get(), "origin": L.origin}
    return out
