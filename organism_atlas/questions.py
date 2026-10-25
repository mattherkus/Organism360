"""Вопросы викторины «Угадай по факту» из файлов questions/<орган>.json.

Файл на орган; ответ на любой вопрос из файла - этот орган:
  {"questions": [
     {"level": "easy", "ru": "Мышечный насос, который гоняет кровь по сосудам.", "en": "A muscular pump..."},
     ...
  ]}
level - easy, medium или hard (какие уровни идут в игру на каждой сложности - см. POOL).
Текст на русском (ru) обязателен; на других языках по желанию, без перевода вопрос показывается
так же, как остальной текст: на предыдущем выбранном языке или по-русски.
Ключи, начинающиеся с «_» (например, _comment), игнорируются.

Вопрос со своими вариантами ответа (ответ - не орган, а один из вариантов):
  {"level": "medium", "ru": "Сколько камер у сердца?", "en": "How many chambers does the heart have?",
   "answer": "4", "wrong": ["2", "3", "6"]}
answer - верный ответ, wrong - неверные (из них берётся столько, сколько вариантов на этой сложности).
Если ответы одинаковы на всех языках (числа), достаточно строки и списка; если нет - словари по языкам:
  "answer": {"ru": "Кровь", "en": "Blood"}, "wrong": {"ru": ["Лимфу", "Воду"], "en": ["Lymph", "Water"]}
Списки неверных ответов на всех языках одной длины и в одном порядке. Такой вопрос может называть орган.

Чтобы добавить вопрос, допишите его в файл органа; новый орган - новый файл <ключ органа>.json.
Вопрос, в котором назван сам орган, выдаёт ответ, и викторина его пропускает.
Проверить все файлы: python -m organism_atlas.questions
"""

import json
from pathlib import Path

from . import i18n

DIR = Path(__file__).with_name("questions")
LEVELS = ("easy", "medium", "hard")
# какие вопросы попадают в игру на каждой сложности
POOL = {"easy": ("easy",), "medium": ("easy", "medium"), "hard": ("medium", "hard")}

_cache = None


def _fail(path, msg):
    raise ValueError("Ошибка в файле questions/%s: %s" % (path.name, msg))


def read_file(path):
    """прочитать и проверить файл вопросов; ошибка - ValueError с понятным текстом"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _fail(path, "строка %d, столбец %d: %s" % (e.lineno, e.colno, e.msg))
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        _fail(path, "нужен объект вида {\"questions\": [...]}")
    out = []
    for n, q in enumerate(data["questions"], 1):
        if not isinstance(q, dict):
            _fail(path, "вопрос %d - не объект в фигурных скобках" % n)
        if q.get("level") not in LEVELS:
            _fail(path, "вопрос %d: level «%s», а нужен один из: %s" % (n, q.get("level"), ", ".join(LEVELS)))
        texts = {k: v for k, v in q.items() if k not in ("level", "answer", "wrong") and not k.startswith("_")}
        for lang, text in texts.items():
            if not isinstance(text, str) or not text.strip():
                _fail(path, "вопрос %d: текст «%s» пустой или не строка" % (n, lang))
        if i18n.BASE not in texts:
            _fail(path, "вопрос %d: нет текста на русском (\"%s\")" % (n, i18n.BASE))
        item = {"level": q["level"], "text": {k: v.strip() for k, v in texts.items()}}
        if "answer" in q or "wrong" in q:
            item["answer"], item["wrong"] = _answers(path, n, q)
        out.append(item)
    return out


def _by_lang(value):
    """строка или список - одинаковы на всех языках (храним как русские), словарь - по языкам"""
    return value if isinstance(value, dict) else {i18n.BASE: value}


def _answers(path, n, q):
    """проверить answer и wrong; вернуть ({язык: верный}, {язык: [неверные]})"""
    if "answer" not in q or "wrong" not in q:
        _fail(path, "вопрос %d: для своих вариантов нужны оба поля, answer и wrong" % n)
    answer, wrong = _by_lang(q["answer"]), _by_lang(q["wrong"])
    if i18n.BASE not in answer or i18n.BASE not in wrong:
        _fail(path, "вопрос %d: в answer и wrong нужен вариант на русском (\"%s\")" % (n, i18n.BASE))
    for lang, a in answer.items():
        if not isinstance(a, str) or not a.strip():
            _fail(path, "вопрос %d: answer «%s» пустой или не строка" % (n, lang))
    size = None
    for lang, w in wrong.items():
        if not isinstance(w, list) or not w or not all(isinstance(x, str) and x.strip() for x in w):
            _fail(path, "вопрос %d: wrong «%s» - нужен непустой список строк" % (n, lang))
        if size is not None and len(w) != size:
            _fail(path, "вопрос %d: в wrong на разных языках разное число вариантов" % n)
        size = len(w)
    for lang, w in wrong.items():
        a = answer.get(lang, answer[i18n.BASE]).strip()
        if a in (x.strip() for x in w):
            _fail(path, "вопрос %d: верный ответ «%s» есть и среди неверных" % (n, a))
    return ({k: v.strip() for k, v in answer.items()}, {k: [x.strip() for x in v] for k, v in wrong.items()})


def load_all(directory=None, known=None):
    """{орган: [вопросы]} из всех файлов папки; known - допустимые ключи органов (проверка имён файлов).
    Папка по умолчанию читается один раз за запуск."""
    global _cache
    if directory is None and _cache is not None and known is None:
        return _cache
    d = Path(directory) if directory else DIR
    data = {}
    for path in sorted(d.glob("*.json")):
        if known is not None and path.stem not in known:
            _fail(path, "нет органа «%s»; файл должен называться как ключ органа: %s"
                  % (path.stem, ", ".join(known)))
        data[path.stem] = read_file(path)
    if directory is None:
        _cache = data
    return data


def for_organ(key):
    return load_all().get(key, [])


def text(key, idx):
    """текст вопроса на текущем языке (с откатом на предыдущий и русский)"""
    q = for_organ(key)[idx]["text"]
    for code in i18n.chain():
        if q.get(code):
            return q[code]
    return q[i18n.BASE]


def has_answers(key, idx):
    """у вопроса свои варианты ответа (а не «какой это орган»)"""
    return "answer" in for_organ(key)[idx]


def n_wrong(key, idx):
    return len(for_organ(key)[idx]["wrong"][i18n.BASE])


def answer_text(key, idx, j):
    """вариант ответа на текущем языке: j = 0 - верный, 1.. - неверные"""
    q = for_organ(key)[idx]
    for code in i18n.chain():
        if j == 0 and q["answer"].get(code):
            return q["answer"][code]
        if j > 0 and q["wrong"].get(code):
            return q["wrong"][code][j - 1]
    return ""


def check():
    """отчёт для авторов вопросов: сколько вопросов и какие из них викторина пропустит"""
    from .organs import ORGANS
    from .quiz import leaks

    data = load_all(known=list(ORGANS))
    lines = []
    for key in ORGANS:
        qs = data.get(key, [])
        by_level = {lv: sum(q["level"] == lv for q in qs) for lv in LEVELS}
        lines.append("%-11s %3d вопросов (%s)" % (key, len(qs), ", ".join("%s %d" % kv for kv in by_level.items())))
        for lv in LEVELS:
            if not any(q["level"] in POOL[lv] for q in qs):
                lines.append("    ! на уровне %s про этот орган спрашивать нечего" % lv)
        custom = sum("answer" in q for q in qs)
        if custom:
            lines[-1] += ", из них со своими вариантами: %d" % custom
        for n, q in enumerate(qs, 1):
            if "answer" in q:                      # ответ - не орган, называть его можно
                continue
            for lang, t in q["text"].items():
                if leaks(t, key):
                    lines.append("    ! вопрос %d (%s) называет сам орган и будет пропущен: %s" % (n, lang, t))
    return lines


if __name__ == "__main__":
    import sys

    try:
        print("\n".join(check()))
    except ValueError as e:
        sys.exit(str(e))
