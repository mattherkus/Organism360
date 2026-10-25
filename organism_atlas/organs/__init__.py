"""Реестр органов.

Чтобы добавить орган: создайте модуль organs/<имя>.py с COLOR, paint() и parts() по образцу
существующих, впишите его в _MODULES (порядок = порядок в викторине) и в ORDER (порядок слоёв),
а тексты карточки добавьте в lang/ru.json (и в другие языки) под тем же ключом.
"""
from .. import i18n
from . import (bladder, brain, gallbladder, heart, intestines, kidneys, liver, lungs, pancreas, spleen,
               stomach, thyroid)

# порядок в карточках и в викторине
_MODULES = {
    "lungs": lungs, "liver": liver, "gallbladder": gallbladder, "stomach": stomach, "intestines": intestines,
    "kidneys": kidneys, "heart": heart, "brain": brain, "thyroid": thyroid,
    "spleen": spleen, "pancreas": pancreas, "bladder": bladder,
}

# порядок слоёв на схеме: снизу вверх (последний лежит выше и первым ловит клик)
ORDER = ["intestines", "kidneys", "bladder", "spleen", "pancreas", "stomach", "gallbladder", "liver", "lungs", "thyroid",
         "heart", "brain"]

# {ключ: {color, parts}}: не зависящее от языка; тексты берутся через i18n
ORGANS = {key: {"color": m.COLOR, "parts": m.parts} for key, m in _MODULES.items()}

# {ключ: функция рисования органа на схеме тела}
PAINT = {key: m.paint for key, m in _MODULES.items()}


def fact_of_day(key, day=None):
    return i18n.fact_of_day(key, list(ORGANS).index(key), day)
