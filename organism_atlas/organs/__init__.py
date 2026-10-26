"""Реестр органов.

Чтобы добавить орган: создайте модуль organs/<имя>.py с COLOR, SYSTEMS, paint() и parts() по образцу
существующих (SEX - если орган есть только у одного пола), впишите его в _MODULES (порядок = порядок
в карточках) и в ORDER (порядок слоёв), а тексты карточки добавьте в lang/ru.json (и в другие языки)
под тем же ключом.
"""
from .. import i18n, settings
from . import (adrenals, appendix, bladder, brain, esophagus, gallbladder, heart, intestines, kidneys, liver, lungs,
               ovaries, pancreas, prostate, rectum, spleen, stomach, thyroid, trachea, uterus)

# порядок в карточках и в викторине
_MODULES = {
    "lungs": lungs, "liver": liver, "gallbladder": gallbladder, "stomach": stomach, "intestines": intestines,
    "kidneys": kidneys, "heart": heart, "brain": brain, "thyroid": thyroid,
    "spleen": spleen, "pancreas": pancreas, "bladder": bladder,
    "esophagus": esophagus, "trachea": trachea, "adrenals": adrenals, "appendix": appendix, "rectum": rectum,
    "uterus": uterus, "ovaries": ovaries, "prostate": prostate,
}

# порядок слоёв на схеме: снизу вверх (последний лежит выше и первым ловит клик)
ORDER = ["intestines", "rectum", "appendix", "kidneys", "uterus", "ovaries", "bladder", "prostate", "spleen",
         "pancreas", "stomach", "adrenals", "gallbladder", "liver", "lungs", "esophagus", "trachea", "thyroid",
         "heart", "brain"]

# системы органов (тема викторины и вопрос «к какой системе относится»); названия - в lang/*.json: system_<ключ>
SYSTEMS = ("digestive", "respiratory", "circulatory", "nervous", "endocrine", "urinary", "reproductive", "immune")

# порядок групп органов в панели слоёв (орган попадает в группу своей главной системы)
PANEL_SYSTEMS = ("respiratory", "digestive", "endocrine", "immune", "urinary", "circulatory", "nervous",
                 "reproductive")

# схема тела: женская или мужская (органы малого таза); выбирается в настройках
SEXES = settings.CHOICES["body"]

# {ключ: {color, parts, systems, sex}}: не зависящее от языка; тексты берутся через i18n.
# sex - None, если орган есть у всех
ORGANS = {key: {"color": m.COLOR, "parts": m.parts, "systems": m.SYSTEMS, "sex": getattr(m, "SEX", None)}
          for key, m in _MODULES.items()}

# {ключ: функция рисования органа на схеме тела}
PAINT = {key: m.paint for key, m in _MODULES.items()}


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


def _norm(s):
    return s.lower().replace("ё", "е").strip()


def search(keys, query):
    """органы из keys, подходящие под строку поиска (регистр и ё не важны): часть названия органа
    на любом языке или часть названия системы органов на текущем языке. Пустая строка - все органы"""
    q = _norm(query)
    if not q:
        return list(keys)
    systems = {s for s in SYSTEMS if q in _norm(i18n.t("system_" + s))}
    return [k for k in keys if any(q in _norm(n) for n in i18n.all_names(k)) or systems & set(ORGANS[k]["systems"])]


def fact_of_day(key, day=None):
    return i18n.fact_of_day(key, list(ORGANS).index(key), day)
