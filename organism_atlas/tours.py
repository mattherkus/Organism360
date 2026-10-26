"""Экскурсии по системам органов: маршрут по органам схемы с рассказом на каждом шаге. Без Tk.

Маршрут - TOURS; органы, которых нет на выбранной схеме тела, пропускаются. Тексты - в разделе "tours"
файлов lang/*.json: у экскурсии title (название), intro (вступление) и steps - рассказ про каждый орган
маршрута (если рассказа нет, показывается описание органа с его карточки).
TOPICS - система органов, по которой в конце экскурсии предлагается викторина.
"""

from . import i18n
from .organs import for_body

TOURS = {
    "food": ["esophagus", "stomach", "liver", "gallbladder", "pancreas", "intestines", "appendix", "rectum"],
    "air": ["trachea", "lungs", "heart", "spleen"],
    "water": ["kidneys", "bladder", "prostate"],
    "control": ["brain", "thyroid", "adrenals", "pancreas", "ovaries"],
}
TOPICS = {"food": "digestive", "air": "respiratory", "water": "urinary", "control": "endocrine"}


def steps(tour, body):
    """органы маршрута, которые есть на схеме тела body (female / male)"""
    have = set(for_body(body))
    return [k for k in TOURS[tour] if k in have]


def available(body):
    """экскурсии, в маршруте которых на этой схеме есть хоть один орган"""
    return [name for name in TOURS if steps(name, body)]


def title(tour):
    return i18n.tour(tour, "title") or tour


def intro(tour):
    return i18n.tour(tour, "intro")


def story(tour, key):
    """рассказ про орган на шаге экскурсии; нет рассказа - описание органа с карточки"""
    return i18n.tour(tour, "steps").get(key) or i18n.organ(key, "desc")
