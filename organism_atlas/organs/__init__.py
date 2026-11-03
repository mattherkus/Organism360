"""Реестр органов.

Чтобы добавить орган: создайте модуль organs/<имя>.py с COLOR, SYSTEMS и paint() по образцу
существующих (SEX - если орган есть только у одного пола; parts() - если 3D-модель не из models/<имя>.json
или models/mesh/<имя>.*), впишите его в _MODULES (порядок = порядок
в карточках) и в ORDER (порядок слоёв), а тексты карточки добавьте в lang/ru.json (и в другие языки)
под тем же ключом.
"""
import functools

from .. import i18n, settings
from ..models import load_parts
from . import (adrenals, aorta, appendix, bladder, brain, diaphragm, esophagus, gallbladder, heart, intestines,
               kidneys, liver, lungs, lymph_nodes, ovaries, pancreas, pituitary, prostate, rectum, spinal_cord, spleen,
               stomach, thymus, thyroid, trachea, uterus, vena_cava)

# порядок в карточках и в викторине
_MODULES = {
    "lungs": lungs, "diaphragm": diaphragm, "liver": liver, "gallbladder": gallbladder, "stomach": stomach,
    "intestines": intestines, "kidneys": kidneys, "heart": heart, "aorta": aorta, "vena_cava": vena_cava,
    "brain": brain, "spinal_cord": spinal_cord, "pituitary": pituitary, "thyroid": thyroid,
    "spleen": spleen, "thymus": thymus, "lymph_nodes": lymph_nodes, "pancreas": pancreas, "bladder": bladder,
    "esophagus": esophagus, "trachea": trachea, "adrenals": adrenals, "appendix": appendix, "rectum": rectum,
    "uterus": uterus, "ovaries": ovaries, "prostate": prostate,
}

# порядок слоёв на схеме: снизу вверх (последний лежит выше и первым ловит клик). Органы, которые лежат выше,
# но за некоторыми нижними (аорта и полые вены - за органами живота), перечисляют их в BEHIND своего модуля
ORDER = ["spinal_cord", "intestines", "rectum", "appendix", "kidneys", "uterus", "ovaries", "bladder", "prostate",
         "spleen", "pancreas", "stomach", "adrenals", "gallbladder", "liver", "diaphragm", "lungs", "esophagus",
         "trachea", "thyroid", "vena_cava", "aorta", "thymus", "heart", "lymph_nodes", "brain", "pituitary"]

# системы органов (тема викторины и вопрос «к какой системе относится»); названия - в lang/*.json: system_<ключ>
SYSTEMS = ("digestive", "respiratory", "circulatory", "nervous", "endocrine", "urinary", "reproductive", "immune")

# цвет системы: значок в панели слоёв и полоска со значком в карточке органа (одинаковые во всех темах;
# это не цвет текста - рядом всегда название системы)
SYSTEM_COLORS = {"circulatory": "#d2474f", "respiratory": "#4f9fd8", "digestive": "#e08a3c", "nervous": "#d9b63a",
                 "endocrine": "#9b6fd0", "urinary": "#3fb3a6", "reproductive": "#d971a6", "immune": "#6aaa4f"}

# порядок групп органов в панели слоёв (орган попадает в группу своей главной системы)
PANEL_SYSTEMS = ("respiratory", "digestive", "endocrine", "immune", "urinary", "circulatory", "nervous",
                 "reproductive")

# схема тела: женская или мужская (органы малого таза); выбирается в настройках
SEXES = settings.CHOICES["body"]

# {ключ: {color, parts, systems, sex}}: не зависящее от языка; тексты берутся через i18n.
# parts() - 3D-модель (по умолчанию models/<ключ>.json или анатомическая сетка), sex - None, если орган есть у всех
ORGANS = {key: {"color": m.COLOR, "parts": getattr(m, "parts", functools.partial(load_parts, key)), "systems": m.SYSTEMS,
                "sex": getattr(m, "SEX", None)}
          for key, m in _MODULES.items()}

# {ключ: функция рисования органа на схеме тела}
PAINT = {key: m.paint for key, m in _MODULES.items()}

# {орган: органы, которые его закрывают, хотя лежат ниже в ORDER}. Так крупный сосуд может лежать над сердцем
# (дуга аорты видна) и при этом за органами живота: схема вырезает его там, где видны органы из BEHIND
# (скрыли орган - сосуд за ним снова виден). BEHIND в модуле органа - кортеж ключей
BEHIND = {key: tuple(m.BEHIND) for key, m in _MODULES.items() if getattr(m, "BEHIND", ())}


def for_body(sex):
    """органы схемы этого пола (в порядке ORGANS): без органов другого пола"""
    return [k for k, o in ORGANS.items() if o["sex"] in (None, sex)]


def other_sex(sex):
    """органы, которых на схеме этого пола нет: они скрыты всегда, в том числе в викторине"""
    return {k for k, o in ORGANS.items() if o["sex"] not in (None, sex)}


def in_system(keys, system):
    """органы из keys, которые относятся к системе (system=None - все)"""
    return [k for k in keys if system is None or system in ORGANS[k]["systems"]]


def by_system(keys):
    """[(система, [органы])] в порядке PANEL_SYSTEMS по главной системе органа, без пустых групп;
    порядок органов внутри группы - как в keys"""
    groups = [(name, [k for k in keys if ORGANS[k]["systems"][0] == name]) for name in PANEL_SYSTEMS]
    return [(name, ks) for name, ks in groups if ks]


def search(keys, query):
    """органы из keys, подходящие под строку поиска (регистр и ё не важны): часть названия органа
    на любом языке или часть названия системы органов на текущем языке. Пустая строка - все органы"""
    q = i18n.fold(query)
    if not q:
        return list(keys)
    systems = {s for s in SYSTEMS if q in i18n.fold(i18n.t("system_" + s))}
    return [k for k in keys if any(q in i18n.fold(n) for n in i18n.all_names(k)) or systems & set(ORGANS[k]["systems"])]


def fact_of_day(key, day=None):
    return i18n.fact_of_day(key, list(ORGANS).index(key), day)
