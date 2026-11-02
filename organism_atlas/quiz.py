"""Логика викторины без привязки к интерфейсу: порядок и число вопросов, варианты ответа, таймер,
вопросы по фактам, по расположению, о системе органов, о болезнях, по латинскому названию и «верно ли»."""

import functools
import random
import re
import time

from . import i18n, questions, settings
from .i18n import t

# найди орган / угадай название / угадай по факту / вперемешку / угадай по 3D-модели / найди кость или мышцу /
# расставь органы маршрута по порядку (order.py) / экзамен / испытание дня
MODES = ("find", "name", "facts", "mix", "model", "body", "order", "exam", "daily")
CLASSIC_MODES = ("find", "name", "facts", "mix")  # четыре викторины по органам (достижение «Универсал»)
NOT_ORGANS = ("body",)                           # режимы, где спрашивают не об органах, а о костях и мышцах
MIXED_MODES = ("mix", "exam", "daily")           # у каждого вопроса свой случайный тип (kinds_for)
NO_CARDS = ("exam", "daily")                     # не двигают карточки повторения: набор вопросов задан заранее
DAILY_LENGTH = 10                                # вопросов в «Испытании дня»
EXAM_SECONDS = 30                                # секунд на вопрос в «Экзамене» (время общее на весь экзамен)
EXAM_GRADES = ((90, 5), (75, 4), (50, 3), (0, 2))   # оценка по доле верных ответов, %
# типы вопросов: три режима и ещё пять, которые есть только во «Вперемешку»:
# where - угадай орган по расположению, system - к какой системе органов относится орган,
# disease - какой орган поражает болезнь, latin - что за орган по латинскому названию,
# truth - верно ли утверждение об органе (факт с карточки этого или другого органа)
# body - найди кость или мышцу (structures.py): как find, но органы скрыты, а видны скелет и мышцы;
# model - что за орган на 3D-модели (варианты - названия, как у name)
KINDS = ("find", "name", "facts", "where", "system", "disease", "latin", "truth", "body", "model")
LEVELS = settings.CHOICES["quiz_level"]
TIMERS = settings.CHOICES["quiz_timer"]
LENGTHS = settings.CHOICES["quiz_length"]        # сколько вопросов в игре; 0 - про все органы
OPTIONS = {"easy": 3, "medium": 4, "hard": 6}    # сколько вариантов ответа на кнопках
# болезни, о которых не спрашиваем «какой орган поражает»: прежде всего они поражают другой орган схемы.
# {орган: ключи болезней из diseases.ON_CARD}
VAGUE_DISEASES = {"pancreas": ("cystic_fibrosis",),      # муковисцидоз - в первую очередь лёгкие
                  "stomach": ("gerd",),                  # рефлюкс - воспаление пищевода
                  "spleen": ("spleen_rupture",),         # разрыв при травме живота бывает и у печени
                  "thymus": ("myasthenia",),             # миастения поражает передачу сигнала к мышцам
                  "spinal_cord": ("herniated_disc",),    # грыжа диска - болезнь позвоночника
                  "pituitary": ("acromegaly", "diabetes_insipidus"),   # следствие болезни гипофиза, а не её место
                  "lymph_nodes": ("lymphedema",)}        # застой лимфы в руке или ноге
# факты, которые не годятся для «верно ли»: они верны или почти верны и для другого органа схемы
# (у сердца и почек размер с кулак, у щитовидной железы и простаты масса около 20 г...).
# {орган: ключи фактов из поля facts карточки в lang/*.json}; добавляете похожий факт - проверьте этот список
SHARED_FACTS = {"gallbladder": ("pear",), "heart": ("fist",), "brain": ("weight",), "thyroid": ("weight",),
                "spleen": ("weight", "reserve", "live_without"), "bladder": ("stretch",), "trachea": ("length",),
                "rectum": ("length", "sphincters"), "prostate": ("weight",), "thymus": ("weight",)}


def _norm(s):
    return s.lower().replace("ё", "е")


def _stems(text):
    """основы слов текста: «желудок» -> «желуд», «лёгкие» -> «легк» (короткие слова не берём)"""
    return {w[:max(4, len(w) - 2)] for w in re.findall(r"\w+", _norm(text)) if len(w) >= 4}


@functools.lru_cache(maxsize=None)
def name_stems(key):
    """основы слов названия органа на всех языках (названия в lang/*.json за время работы не меняются)"""
    stems = set()
    for n in i18n.all_names(key):
        stems |= _stems(n)
    return frozenset(stems)


@functools.lru_cache(maxsize=8192)
def _linked(text):
    """ключи органов, костей и болезней, которые текст упоминает сочетаниями из раздела links"""
    return frozenset(k for _, k in i18n.links(text) if k)


def leaks(text, key):
    """выдаёт ли текст ответ: упоминает ли он сам орган - основой слова названия или сочетанием из раздела links
    (оно ловит формы, которых не видно по основе: «полой вены» у «Полые вены»)"""
    s = _norm(text)
    return any(stem in s for stem in name_stems(key)) or key in _linked(text)


def _candidates(key, levels):
    """номера вопросов органа (questions/<орган>.json) нужных уровней, которые не выдают ответ.
    Вопрос со своими вариантами может называть орган: ответ на него - не орган."""
    return [i for i, q in enumerate(questions.for_organ(key))
            if q["level"] in levels and ("answer" in q or not leaks(questions.text(key, i), key))]


def fact_prompts(keys, level, rng=random):
    """{орган: номер вопроса} - что спросить про каждый орган; None - вопросов нет, спросим о функции"""
    out = {}
    for k in keys:
        cand = _candidates(k, questions.POOL[level]) or _candidates(k, questions.LEVELS)
        out[k] = rng.choice(cand) if cand else None
    return out


def location_leaks(key):
    """выдаёт ли расположение органа (поле location карточки) ответ хотя бы на одном языке"""
    return any(leaks(i18n.organ_in(code, key, "location"), key) for code in i18n.available())


def _names_any(text):
    """называет ли текст хоть один орган схемы"""
    from .organs import ORGANS
    return any(leaks(text, k) for k in ORGANS)


def disease_choices(key):
    """ключи болезней органа (diseases.ON_CARD), по которым можно спросить «какой орган поражает эта болезнь»:
    болезнь ни на одном языке не называет орган схемы, не записана и у другого органа и не из VAGUE_DISEASES"""
    from . import diseases
    out = []
    for d in diseases.ON_CARD.get(key, ()):
        names = [diseases.name_in(code, d) for code in i18n.available()]
        if d in VAGUE_DISEASES.get(key, ()) or len(diseases.ORGANS_OF[d]) > 1 or any(_names_any(s) for s in names):
            continue
        out.append(d)
    return out


def truth_facts(key):
    """ключи фактов карточки органа для вопроса «верно ли»: факт не из SHARED_FACTS и не называет
    ни один орган схемы, иначе подставленный к чужому органу он сразу выдаёт себя"""
    out = []
    for fid, _ in i18n.facts(key):
        texts = [i18n.fact_in(code, key, fid) for code in i18n.available()]
        if fid not in SHARED_FACTS.get(key, ()) and not any(_names_any(s) for s in texts):
            out.append(fid)
    return out


def plain_name(key):
    """название органа не по-латыни: в латинском режиме - на языке, выбранном перед латынью"""
    return i18n.organ(key, "name", skip_current=i18n.current() == "la")


def latin_name(key):
    return i18n.organ_in("la", key, "name") if "la" in i18n.available() else ""


def latin_ok(key):
    """можно ли спросить «что это за орган» по латинскому названию: оно есть и не похоже на название,
    которым подписаны варианты (Pancreas - Pancreas, Trachea - Трахея спрашивать незачем)"""
    la, plain = latin_name(key), plain_name(key)
    if not la:
        return False
    return not (_stems(plain) & _stems(la) or any(s in _norm(la) for s in _stems(plain))
                or any(s in _norm(plain) for s in _stems(la)))


# части 3D-моделей, о которых не спрашиваем по латыни «часть какого органа»: это соседи для ориентира
# (двенадцатиперстная кишка у поджелудочной), отдельный орган (мочеточники) или название ничего не говорит
LATIN_PART_SKIP = {("pancreas", "duodenum"), ("pancreas", "artery"), ("appendix", "cecum"), ("thyroid", "cartilage"),
                   ("prostate", "prostate"), ("kidneys", "ureter")}


def latin_parts(key):
    """группы 3D-модели органа (раздел parts в la.json), о которых можно спросить «часть какого органа»: латынь есть,
    это часть самого органа, а не сосед для ориентира, и название не называет ни один орган схемы"""
    from .organs import ORGANS
    if "la" not in i18n.available():
        return []
    parts = i18n.section("la", "parts").get(key, {})
    return [g for g, name in parts.items() if name and not g.endswith("_dim") and (key, g) not in LATIN_PART_SKIP
            and not any(leaks(name, k) for k in ORGANS)]


def latin_part_name(key, group):
    return i18n.section("la", "parts").get(key, {}).get(group, "")


def kinds_for(key):
    """какие типы вопросов можно задать про орган во «Вперемешку»"""
    from .organs import ORGANS
    out = ["find", "name", "facts"]
    if not location_leaks(key):
        out.append("where")
    if key in ORGANS:
        out.append("system")
        if disease_choices(key):
            out.append("disease")
        if truth_facts(key):
            out.append("truth")
    if latin_ok(key) or latin_parts(key):
        out.append("latin")
    return out


def game_length(length, available):
    """сколько вопросов будет в игре: length (0 - все), но не больше, чем есть органов"""
    return available if not length or length > available else length


def prompt_text(key, idx):
    """текст вопроса по факту на текущем языке"""
    if idx is None or idx >= len(questions.for_organ(key)):
        return i18n.organ(key, "desc")
    return questions.text(key, idx)


class QuizSession:
    """Один проход викторины: вопросы в случайном порядке, подсчёт ошибок, таймер и результат.

    keys - органы, о которых можно спросить; count - сколько вопросов (None или 0 - про все), органы
    берутся случайно и не повторяются; pool - из каких органов брать неверные варианты (по умолчанию keys);
    mode - режим из MODES («mix» - у каждого вопроса свой случайный тип из KINDS);
    timer - секунд на вопрос (0 - без таймера); clock - источник времени (подменяется в тестах)."""

    def __init__(self, keys, rng=random, pool=None, mode="find", level="medium", timer=0, clock=time.monotonic,
                 count=None, single_try=False, total_time=0):
        self.rng, self.mode, self.level, self.timer, self.clock = rng, mode, level, timer, clock
        keys = list(keys)
        self.q = rng.sample(keys, game_length(count, len(keys)))     # какие органы и в каком порядке
        self.pool = list(pool) if pool is not None else list(self.q)
        # тип каждого вопроса
        self.kinds = [rng.choice(kinds_for(k)) for k in self.q] if mode in MIXED_MODES else [mode] * len(self.q)
        # «Экзамен»: на вопрос одна попытка (ошибка - сразу следующий вопрос) и общее время на всю игру
        self.single_try, self.total_time = single_try, total_time
        self.log = []                                # [(номер вопроса, верно ли, что ответили или None)]
        self.i = 0                                   # номер текущего вопроса
        self.errors = 0                              # всего ошибок (включая вышедшее время)
        self.first_try = 0                           # верных с первой попытки
        self.timeouts = 0                            # сколько раз не успели
        self.planned = len(self.q)                   # сколько вопросов было задумано (до «Сдаться»)
        self.gave_up = False                         # игру закончили кнопкой «Сдаться»
        self.slipped = False                         # на текущем вопросе уже была ошибка
        self.missed = []                             # ключи органов, на которых ошибались
        self.results = {}                            # {орган: True - с первой попытки, False - нет}
        self._options = {}                           # {номер вопроса: варианты ответа}
        facts = [k for k, kind in zip(self.q, self.kinds) if kind == "facts"]
        self.prompts = fact_prompts(facts, level, rng) if facts else {}
        # {номер вопроса: что спрашиваем}: у disease - ключ болезни, у truth - (чей факт, ключ факта),
        # у latin - часть 3D-модели («часть какого органа») или None (само латинское название органа)
        self.picks = {i: self._pick(k, kind) for i, (k, kind) in enumerate(zip(self.q, self.kinds))
                      if kind in ("disease", "truth", "latin")}
        self.deadline = None                         # когда кончится время на текущий вопрос
        self.started, self.ended = clock(), None

    def _pick(self, key, kind):
        if kind == "disease":
            return self.rng.choice(disease_choices(key))
        if kind == "latin":
            parts = latin_parts(key)
            if parts and (not latin_ok(key) or self.rng.random() < 0.5):
                return self.rng.choice(parts)
            return None
        # «верно ли»: поровну правды и неправды; неправда - факт органа из другой системы (чтобы не
        # оказался верным и для этого органа)
        from .organs import ORGANS
        own = set(ORGANS[key]["systems"])
        strangers = [k for k in self.pool if k != key and k in ORGANS and not own & set(ORGANS[k]["systems"])
                     and truth_facts(k)]
        owner = key if not strangers or self.rng.random() < 0.5 else self.rng.choice(strangers)
        return owner, self.rng.choice(truth_facts(owner))

    @property
    def total(self):
        return len(self.q)

    @property
    def finished(self):
        return self.i >= len(self.q)

    @property
    def current(self):
        """ключ органа, о котором текущий вопрос (None, когда вопросы закончились)"""
        return None if self.finished else self.q[self.i]

    @property
    def kind(self):
        """тип текущего вопроса из KINDS (None, когда вопросы закончились)"""
        return None if self.finished else self.kinds[self.i]

    @property
    def elapsed(self):
        """секунд с начала игры (после конца - длительность игры)"""
        return (self.ended if self.ended is not None else self.clock()) - self.started

    def _next(self, ok, given=None):
        self.results[self.q[self.i]] = ok
        self.log.append((self.i, ok, given))
        self.slipped = False
        if not self.total_time:                      # общее время «Экзамена» идёт дальше
            self.deadline = None
        self.i += 1
        if self.finished:
            self.ended = self.clock()

    def _miss(self):
        self.errors += 1
        self.slipped = True
        if self.q[self.i] not in self.missed:
            self.missed.append(self.q[self.i])

    def answer(self, key):
        """принять ответ; True - верно, False - ошибка, None - викторина уже закончена"""
        if self.finished:
            return None
        if key == self.correct():
            if not self.slipped:
                self.first_try += 1
            self._next(not self.slipped, key)
            return True
        self._miss()
        if self.single_try:                          # «Экзамен»: вторая попытка не даётся
            self._next(False, key)
        return False

    @property
    def time_limit(self):
        """секунд на вопрос или на всю игру («Экзамен»); 0 - без времени"""
        return self.total_time or self.timer

    @property
    def organ_count(self):
        """сколько органов на схеме - для «Марафона» (игра про все органы); None - игра не про органы схемы
        (кости и мышцы) или про заданный набор («Испытание дня»)"""
        return None if self.mode in NOT_ORGANS or self.mode == "daily" else len(self.pool)

    # --- таймер: интерфейс запускает его, когда вопрос появился на экране
    def start_timer(self):
        if self.time_limit and not self.finished and self.deadline is None:
            self.deadline = self.clock() + self.time_limit

    def remaining(self):
        """сколько секунд осталось на текущий вопрос; None - таймера нет или он не запущен"""
        if self.deadline is None or self.finished:
            return None
        return max(0.0, self.deadline - self.clock())

    def time_up(self):
        """если время на вопрос вышло: засчитать ошибку и перейти дальше; возвращает пропущенный орган"""
        rem = self.remaining()
        if rem is None or rem > 0:
            return None
        if self.total_time:                          # время «Экзамена» вышло: оставшиеся вопросы - без ответа
            key = None
            while not self.finished:
                self.timeouts += 1
                key = self._skip()
            return key
        self.timeouts += 1
        return self._skip()

    def _skip(self):
        """засчитать ошибку на текущем вопросе и перейти дальше; возвращает пропущенный орган"""
        key = self.q[self.i]
        if not self.slipped:                         # уже ошибся на этом вопросе - вторую ошибку не берём
            self._miss()
        self._next(False)
        return key

    def finish_all(self):
        """закончить игру сейчас: оставшиеся вопросы - ошибки без ответа («Завершить» в «Экзамене»: в отличие
        от «Сдаться», вопросы не выбрасываются и оценка считается от всех). Возвращает последний орган"""
        key = None
        while not self.finished:
            key = self._skip()
        return key

    def give_up(self):
        """кнопка «Сдаться»: текущий вопрос - ошибка, и игра на нём заканчивается (оставшихся вопросов не будет,
        в итогах - только пройденные). Возвращает орган текущего вопроса (None - викторина уже закончена)"""
        if self.finished:
            return None
        self.gave_up = True
        del self.q[self.i + 1:]
        return self._skip()

    # --- варианты ответа - органы (ключи), кроме трёх случаев:
    # вопрос по факту со своими вариантами - «#0» (верный) и «#1», «#2»... (неверные);
    # вопрос о системе органов - «@система» (ключ из organs.SYSTEMS);
    # вопрос «верно ли» - «?1» (верно) и «?0» (неверно)
    def latin_part(self):
        """у вопроса по латыни - часть 3D-модели органа (группа сетки) или None: спрашивают само название органа"""
        return self.picks.get(self.i) if self.kind == "latin" else None

    def custom(self):
        """у текущего вопроса свои варианты ответа (а не «какой это орган»)"""
        idx = self.prompts.get(self.current) if self.kind == "facts" else None
        return idx is not None and questions.has_answers(self.current, idx)

    def correct(self):
        """что считается верным ответом: ключ органа, «#0» или «@система»"""
        return self._correct(self.i)

    def _correct(self, i):
        key, kind = self.q[i], self.kinds[i]
        if kind == "system":
            from .organs import ORGANS
            return "@" + ORGANS[key]["systems"][0]
        if kind == "truth":
            return "?1" if self.picks[i][0] == key else "?0"
        idx = self.prompts.get(key) if kind == "facts" else None
        if idx is not None and questions.has_answers(key, idx):
            return "#0"
        return key

    def answer_text(self, i):
        """верный ответ вопроса номер i словами, если ответ - не орган (для «Время вышло! Правильный ответ: …»);
        None - ответ на вопрос и есть орган"""
        right = self._correct(i)
        if right.startswith("@"):
            return t("system_" + right[1:])
        if right.startswith("#"):
            return questions.answer_text(self.q[i], self.prompts[self.q[i]], 0)
        if right.startswith("?"):
            return t("truth_yes" if right == "?1" else "truth_no")
        return None

    def option_label(self, opt):
        """текст на кнопке варианта на текущем языке"""
        if opt.startswith("#"):
            return questions.answer_text(self.current, self.prompts[self.current], int(opt[1:]))
        if opt.startswith("@"):
            return t("system_" + opt[1:])
        if opt.startswith("?"):
            return t("truth_yes" if opt == "?1" else "truth_no")
        if self.kind == "latin":                     # вопрос - латинское название, варианты - не по-латыни
            return plain_name(opt)
        return i18n.name(opt)

    def options(self, n=None):
        """варианты ответа: верный и n-1 случайных неверных, в случайном порядке. Неверные - другие органы
        из pool, неверные ответы вопроса или другие системы органов. n по умолчанию зависит от сложности.
        Для одного вопроса список не меняется."""
        if self.finished:
            return []
        if self.i not in self._options:
            n = n or OPTIONS[self.level]
            if self.kind == "truth":                 # всегда два варианта и в одном порядке
                self._options[self.i] = ["?1", "?0"]
                return self._options[self.i]
            if self.custom():
                others = ["#%d" % j for j in range(1, questions.n_wrong(self.current, self.prompts[self.current]) + 1)]
            elif self.kind == "system":
                from .organs import ORGANS, SYSTEMS
                others = ["@" + x for x in SYSTEMS if x not in ORGANS[self.current]["systems"]]
            else:
                others = [k for k in self.pool if k != self.current]
                if self.kind == "disease":           # органы той же системы болеют похоже: их не предлагаем
                    from .organs import ORGANS
                    own = set(ORGANS[self.current]["systems"])
                    far = [k for k in others if not own & set(ORGANS.get(k, {}).get("systems", ()))]
                    others = far if len(far) >= n - 1 else others
            opts = self.rng.sample(others, min(n - 1, len(others))) + [self.correct()]
            self.rng.shuffle(opts)
            self._options[self.i] = opts
        return self._options[self.i]

    def prompt(self):
        """текст вопроса: факт («Угадай по факту»), расположение органа (вопрос «где находится»), болезнь,
        латинское название или утверждение для «верно ли»"""
        return "" if self.finished else self.prompt_at(self.i)

    def prompt_at(self, i):
        """текст вопроса номер i (для разбора ошибок после игры)"""
        key, kind = self.q[i], self.kinds[i]
        if kind == "facts":
            return prompt_text(key, self.prompts[key])
        if kind == "where":
            return i18n.organ(key, "location")
        if kind == "disease":
            from . import diseases
            return diseases.text(self.picks[i], "name")
        if kind == "latin":
            group = self.picks.get(i)
            return latin_part_name(key, group) if group else latin_name(key)
        if kind == "truth":
            owner, fid = self.picks[i]
            return i18n.fact(owner, fid)
        return ""

    def given_text(self, i, given):
        """что ответили на вопрос номер i словами (для разбора ошибок); None - ответа не было"""
        if given is None:
            return None
        if given.startswith("#"):
            return questions.answer_text(self.q[i], self.prompts[self.q[i]], int(given[1:]))
        if given.startswith("@"):
            return t("system_" + given[1:])
        if given.startswith("?"):
            return t("truth_yes" if given == "?1" else "truth_no")
        return i18n.name(given)

    @property
    def percent(self):
        return round(100 * self.first_try / self.total) if self.total else 0

    @property
    def grade(self):
        """оценка «Экзамена» от 2 до 5 по доле верных ответов (EXAM_GRADES)"""
        return next(g for p, g in EXAM_GRADES if self.percent >= p)

    def mistakes(self):
        """вопросы с ошибкой: [(номер вопроса, орган, что ответили или None)] - для разбора после «Экзамена»"""
        return [(i, self.q[i], given) for i, ok, given in self.log if not ok]

    @property
    def verdict(self):
        pct = self.percent
        if pct == 100:
            return t("verdict_perfect")
        if pct >= 70:
            return t("verdict_good")
        if pct >= 40:
            return t("verdict_ok")
        return t("verdict_bad")


def daily_session(body, day=None, clock=time.monotonic):
    """«Испытание дня»: в этот день у всех одни и те же DAILY_LENGTH вопросов «Вперемешку» (для схемы тела body)"""
    import datetime
    from .organs import for_body
    day = day or datetime.date.today()
    rng = random.Random(day.toordinal() * 2 + (body == "male"))
    return QuizSession(for_body(body), rng=rng, mode="daily", level="medium", count=DAILY_LENGTH, clock=clock)


def format_time(seconds):
    s = int(round(seconds))
    return "%d:%02d" % (s // 60, s % 60)
