"""Настройки вида 3D-просмотра из render3d/look.json (свет, тени, материалы, стиль).

Файл читается один раз. Если его нет или в нём ошибка, используется классический вид:
3D-просмотр не должен ломаться из-за правки настроек.
"""

import json
import sys
from importlib import resources

CLASSIC = {"style": "classic"}
_cache = {}


def get():
    if "look" not in _cache:
        try:
            data = json.loads((resources.files(__package__) / "look.json").read_text(encoding="utf-8"))
            if data.get("style") not in ("realistic", "classic"):
                raise ValueError("style должен быть realistic или classic")
        except (OSError, ValueError) as e:          # JSONDecodeError - тоже ValueError
            print("render3d/look.json: %s; 3D-просмотр в классическом виде" % e, file=sys.stderr)
            data = CLASSIC
        _cache["look"] = data
    return _cache["look"]


def material(look, tex):
    """параметры материала по типу текстуры; неизвестная текстура получает «smooth»"""
    mats = look["materials"]
    return mats.get(tex, mats["smooth"])
