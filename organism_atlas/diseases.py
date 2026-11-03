"""Справочник болезней: какие болезни у какого органа (не зависит от языка).

Статьи (название, что это, признаки, причины, лечение) - в lang/*.json, раздел diseases, под теми же ключами.
ON_CARD - раздел «Заболевания» карточки органа: болезни по порядку, названия - из статей. Чтобы добавить
болезнь: впишите ключ сюда, статью - в lang/ru.json (и в другие языки), а слова, по которым её узнавать
в тексте, - в раздел links.diseases.
"""

from . import i18n
from .organs import ORGANS, PANEL_SYSTEMS

ON_CARD = {
    "lungs": ("pneumonia", "asthma", "copd", "lung_cancer"),
    "liver": ("hepatitis", "fatty_liver", "cirrhosis", "liver_cancer"),
    "gallbladder": ("gallstones", "cholecystitis"),
    "stomach": ("gastritis", "peptic_ulcer", "gerd", "stomach_cancer"),
    "intestines": ("ibs", "ibd", "appendicitis", "colorectal_cancer"),
    "kidneys": ("kidney_stones", "pyelonephritis", "glomerulonephritis", "ckd"),
    "heart": ("ihd", "hypertension", "arrhythmia", "heart_failure"),
    "brain": ("stroke", "migraine", "epilepsy", "alzheimer"),
    "thyroid": ("hypothyroidism", "hyperthyroidism", "thyroiditis", "goiter"),
    "spleen": ("splenomegaly", "spleen_rupture", "spleen_infarction", "hypersplenism"),
    "pancreas": ("pancreatitis", "diabetes", "pancreatic_cancer", "cystic_fibrosis"),
    "bladder": ("cystitis", "overactive_bladder", "bladder_stones", "incontinence"),
    "esophagus": ("gerd", "esophagitis", "barrett", "hiatal_hernia"),
    "trachea": ("tracheitis", "tracheal_stenosis", "foreign_body", "tracheomalacia"),
    "adrenals": ("addison", "cushing", "pheochromocytoma", "conn"),
    "appendix": ("appendicitis", "appendix_tumors", "mucocele"),
    "rectum": ("hemorrhoids", "anal_fissure", "proctitis", "colorectal_cancer"),
    "uterus": ("fibroids", "endometriosis", "cervical_cancer", "endometritis"),
    "ovaries": ("pcos", "ovarian_cyst", "ovarian_cancer", "ovarian_apoplexy"),
    "prostate": ("prostatitis", "bph", "prostate_cancer"),
    "aorta": ("aortic_aneurysm", "aortic_dissection", "atherosclerosis", "coarctation"),
    "vena_cava": ("svc_syndrome", "ivc_thrombosis"),
    "spinal_cord": ("spinal_injury", "herniated_disc", "multiple_sclerosis", "carpal_tunnel"),
    "thymus": ("myasthenia", "thymoma"),
    "pituitary": ("pituitary_adenoma", "acromegaly", "hypopituitarism", "diabetes_insipidus"),
    "diaphragm": ("hiatal_hernia", "diaphragmatic_hernia", "diaphragm_paralysis", "hiccups"),
    "lymph_nodes": ("lymphadenitis", "lymphoma", "lymphedema"),
}

# органы, которых нет в карточке, но болезнь заметно их поражает
EXTRA_ORGANS = {"cystic_fibrosis": ("lungs", "intestines"), "hiatal_hernia": ("stomach",),
                "multiple_sclerosis": ("brain",), "atherosclerosis": ("heart", "brain"), "lymphoma": ("spleen",)}

# {болезнь: (органы)}: сначала органы, в чьих карточках она записана (в порядке ORGANS), затем EXTRA_ORGANS
ORGANS_OF = {}
for _organ in ORGANS:
    for _d in ON_CARD.get(_organ, ()):
        ORGANS_OF.setdefault(_d, ())
        ORGANS_OF[_d] += (_organ,)
for _d, _extra in EXTRA_ORGANS.items():
    ORGANS_OF[_d] += tuple(o for o in _extra if o not in ORGANS_OF[_d])


def system(key):
    """система органов болезни - главная система её первого органа"""
    return ORGANS[ORGANS_OF[key][0]]["systems"][0]


# все болезни в порядке справочника: по системам (как в панели слоёв), внутри - по органам и карточкам
KEYS = [d for s in PANEL_SYSTEMS for d in dict.fromkeys(d for o in ORGANS for d in ON_CARD.get(o, ()))
        if system(d) == s]


def text(key, field):
    """поле статьи: name, desc, symptoms, causes, treatment (с откатом на другие языки, как у органов)"""
    for code in i18n.chain():
        v = i18n.section(code, "diseases").get(key, {}).get(field)
        if v:
            return v
    return key if field == "name" else ""


def name_in(code, key):
    """название болезни на языке code как есть, без отката ("" - перевода нет)"""
    return i18n.section(code, "diseases").get(key, {}).get("name", "")


def sources(key):
    """[(название, адрес)] - откуда сведения статьи (поле sources статьи на текущем языке с откатом); [] - не указано"""
    for code in i18n.chain():
        v = i18n.section(code, "diseases").get(key, {}).get("sources")
        if isinstance(v, list) and v:
            return [(s.get("name", s.get("url", "")), s["url"]) for s in v if isinstance(s, dict) and s.get("url")]
    return []


def general_sources():
    """[(название, адрес)] - авторитетные сайты для «Где узнать больше» (раздел sources файла языка)"""
    for code in i18n.chain():
        v = i18n.section(code, "sources")
        if isinstance(v, list) and v:
            return [(s.get("name", s["url"]), s["url"]) for s in v if isinstance(s, dict) and s.get("url")]
    return []


def reviewed(key):
    """проверил ли статью врач (поле reviewed статьи в ru.json; ставит только врач)"""
    return i18n.section(i18n.BASE, "diseases").get(key, {}).get("reviewed") is True


def subtitle(key):
    """подпись под названием статьи: латинское название, а при включённых латинских названиях - обычное"""
    if i18n.latin():
        for code in i18n.chain()[1:]:
            if name_in(code, key):
                return name_in(code, key)
        return ""
    return name_in(i18n.LATIN, key) if i18n.LATIN in i18n.available() else ""


def on_card(organ):
    """[(название, ключ болезни)] для раздела «Заболевания» карточки органа"""
    return [(text(d, "name"), d) for d in ON_CARD.get(organ, ())]


def related(key):
    """другие болезни тех же органов, в порядке справочника"""
    organs = set(ORGANS_OF[key])
    return [d for d in KEYS if d != key and organs & set(ORGANS_OF[d])]


def search(query):
    """болезни, подходящие под строку: часть названия болезни на любом языке или органа на любом языке"""
    q = i18n.fold(query)
    if not q:
        return list(KEYS)
    out = []
    for d in KEYS:
        names = [i18n.section(code, "diseases").get(d, {}).get("name", "") for code in i18n.available()]
        names += [n for o in ORGANS_OF[d] for n in i18n.all_names(o)]
        if any(q in i18n.fold(n) for n in names if n):
            out.append(d)
    return out
