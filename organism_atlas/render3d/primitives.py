"""Примитивы 3D-моделей во внутреннем виде для Scene3D: E (эллипсоид), T (трубка вдоль пути).
Сами модели лежат в models/*.json и читаются через organism_atlas.models.load_parts."""


def E(c, r, color, tex="smooth", gloss=0.35):
    return {"k": "e", "c": c, "r": r, "color": color, "tex": tex, "gloss": gloss}


def T(path, rad, color, tex="smooth", gloss=0.35, rings=0.0, hause=0.0):
    return {"k": "t", "path": path, "rad": rad, "color": color, "tex": tex, "gloss": gloss,
            "rings": rings, "hause": hause}
