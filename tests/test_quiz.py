import random
import unittest

from organism_atlas import diseases, i18n, questions
from organism_atlas.organs import ORGANS, SYSTEMS, for_body
from organism_atlas.quiz import (KINDS, LENGTHS, LEVELS, OPTIONS, SHARED_FACTS, VAGUE_DISEASES, QuizSession, disease_choices,
                                 fact_prompts, format_time, game_length, kinds_for, latin_ok, leaks, location_leaks,
                                 prompt_text, truth_facts)

NAMES = {"a": "Аа", "b": "Бб", "c": "Вв", "d": "Гг"}


def session(seed=0):
    return QuizSession(list(NAMES), rng=random.Random(seed))


class QuizTests(unittest.TestCase):
    def test_all_questions_asked_once(self):
        s = session()
        self.assertCountEqual(s.q, NAMES)
        self.assertEqual(s.total, 4)

    def test_perfect_game(self):
        s = session()
        while not s.finished:
            self.assertTrue(s.answer(s.current))
        self.assertEqual((s.first_try, s.errors, s.missed, s.percent), (4, 0, [], 100))
        self.assertEqual(s.verdict, "Отлично! Ни одной ошибки.")
        self.assertIsNone(s.current)
        self.assertIsNone(s.answer("a"))             # после конца ответы игнорируются

    def test_mistake_costs_first_try_and_is_remembered_once(self):
        s = session()
        wrong = next(k for k in NAMES if k != s.current)
        asked = s.current
        self.assertFalse(s.answer(wrong))
        self.assertFalse(s.answer(wrong))
        self.assertTrue(s.answer(asked))
        self.assertEqual((s.errors, s.first_try, s.i), (2, 0, 1))
        self.assertEqual(s.missed, [asked])

    def test_verdict_thresholds(self):
        s = session()
        for first_try, text in ((4, "Отлично"), (3, "Хороший"), (2, "Неплохо"), (1, "Стоит повторить")):
            s.first_try = first_try
            self.assertTrue(s.verdict.startswith(text), (first_try, s.verdict))

    def test_options_contain_answer_and_are_stable(self):
        s = session()
        while not s.finished:
            opts = s.options()
            self.assertEqual(len(opts), 4)
            self.assertEqual(len(set(opts)), 4)
            self.assertIn(s.current, opts)
            self.assertEqual(s.options(), opts)          # повторный вызов не перемешивает варианты
            s.answer(s.current)
        self.assertEqual(s.options(), [])

    def test_options_with_few_organs(self):
        s = QuizSession(["a", "b"], rng=random.Random(1))
        self.assertCountEqual(s.options(), ["a", "b"])

    def test_answer_position_varies(self):
        positions = set()
        for seed in range(30):
            s = session(seed)
            positions.add(s.options().index(s.current))
        self.assertGreater(len(positions), 2)


class Clock:
    """подменные часы: время двигаем руками"""

    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class LevelAndTimerTests(unittest.TestCase):
    def test_option_count_depends_on_level(self):
        for level in LEVELS:
            s = QuizSession(list(ORGANS), rng=random.Random(2), level=level)
            self.assertEqual(len(s.options()), OPTIONS[level])

    def test_distractors_come_from_pool(self):
        s = QuizSession(["heart"], rng=random.Random(3), pool=list(ORGANS), level="hard")
        opts = s.options()
        self.assertEqual(len(opts), 6)
        self.assertIn("heart", opts)
        self.assertTrue(set(opts) <= set(ORGANS))

    def test_results_per_organ(self):
        s = session()
        first, second = s.q[0], s.q[1]
        s.answer(first)
        s.answer(next(k for k in NAMES if k != second))
        s.answer(second)
        self.assertEqual(s.results, {first: True, second: False})

    def test_timer_runs_out(self):
        clock = Clock()
        s = QuizSession(list(NAMES), rng=random.Random(0), timer=10, clock=clock)
        self.assertIsNone(s.remaining())             # пока вопрос не показан, время не идёт
        s.start_timer()
        clock.t += 4
        self.assertAlmostEqual(s.remaining(), 6)
        self.assertIsNone(s.time_up())
        asked = s.current
        clock.t += 6
        self.assertEqual(s.time_up(), asked)
        self.assertEqual((s.i, s.errors, s.timeouts, s.missed, s.results), (1, 1, 1, [asked], {asked: False}))
        self.assertIsNone(s.remaining())             # у следующего вопроса таймер ещё не запущен
        self.assertIsNone(s.time_up())

    def test_timeout_after_mistake_is_one_error(self):
        clock = Clock()
        s = QuizSession(list(NAMES), rng=random.Random(0), timer=5, clock=clock)
        s.start_timer()
        s.answer(next(k for k in NAMES if k != s.current))
        clock.t += 5
        s.time_up()
        self.assertEqual((s.errors, s.timeouts, len(s.missed)), (1, 1, 1))

    def test_give_up(self):
        """«Сдаться»: одна ошибка (даже после промаха), не «время вышло», остальных вопросов нет"""
        s = QuizSession(list(NAMES), rng=random.Random(0), count=4)
        s.answer(s.current)
        asked = s.current
        s.answer(next(k for k in NAMES if k != asked))
        self.assertEqual(s.give_up(), asked)
        self.assertTrue(s.finished and s.gave_up)
        self.assertEqual((s.total, s.planned, s.errors, s.timeouts, s.missed, s.results[asked]),
                         (2, 4, 1, 0, [asked], False))
        self.assertIsNone(s.give_up())

    def test_skip(self):
        """«Пропустить»: вопрос - одна ошибка без ответа (даже после промаха), игра идёт дальше"""
        s = QuizSession(list(NAMES), rng=random.Random(0), count=3)
        asked = s.current
        s.answer(next(k for k in NAMES if k != asked))
        self.assertEqual(s.skip(), asked)
        self.assertFalse(s.finished or s.gave_up)
        self.assertEqual((s.i, s.total, s.errors, s.timeouts, s.missed, s.results[asked]), (1, 3, 1, 0, [asked], False))
        s.skip()
        last = s.current
        self.assertEqual(s.skip(), last)
        self.assertTrue(s.finished)
        self.assertEqual((s.errors, s.first_try), (3, 0))
        self.assertIsNone(s.skip())

    def test_no_timer(self):
        s = session()
        s.start_timer()
        self.assertIsNone(s.remaining())
        self.assertIsNone(s.time_up())

    def test_elapsed_stops_at_the_end(self):
        clock = Clock()
        s = QuizSession(["a"], rng=random.Random(0), clock=clock)
        clock.t += 7
        s.answer("a")
        clock.t += 100
        self.assertEqual(s.elapsed, 7)
        self.assertEqual(format_time(s.elapsed), "0:07")
        self.assertEqual(format_time(125), "2:05")


class FactQuestionTests(unittest.TestCase):
    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE

    def test_facts_never_name_their_organ(self):
        for lang in ("ru", "en"):
            i18n.set_lang(lang)
            for level in LEVELS:
                for seed in range(5):
                    for key, ref in fact_prompts(list(ORGANS), level, random.Random(seed)).items():
                        text = prompt_text(key, ref)
                        self.assertTrue(text)
                        if ref is not None and questions.has_answers(key, ref):
                            continue                 # свои варианты: орган назвать можно
                        self.assertFalse(leaks(text, key), (lang, level, key, text))

    def test_leak_detection(self):
        self.assertTrue(leaks("Соляная кислота защищает стенки желудка", "stomach"))
        self.assertTrue(leaks("Правое лёгкое имеет три доли", "lungs"))
        self.assertTrue(leaks("The heart has four chambers", "heart"))
        self.assertFalse(leaks("Вмещает около 1–1,5 л", "stomach"))

    def test_level_picks_questions_of_its_pool(self):
        for level in LEVELS:
            for seed in range(5):
                prompts = fact_prompts(list(ORGANS), level, random.Random(seed))
                for key, idx in prompts.items():
                    self.assertIn(questions.for_organ(key)[idx]["level"], questions.POOL[level], (level, key))

    def test_organ_without_questions_falls_back_to_function(self):
        self.assertEqual(fact_prompts(["nope"], "easy", random.Random(0)), {"nope": None})
        self.assertEqual(prompt_text("heart", None), i18n.organ("heart", "desc"))

    def test_session_prompt(self):
        s = QuizSession(list(ORGANS), rng=random.Random(1), mode="facts", level="hard")
        self.assertTrue(s.prompt())
        self.assertTrue(all(questions.for_organ(k)[i]["level"] != "easy" for k, i in s.prompts.items()))
        while not s.finished:
            s.answer(s.correct())
        self.assertEqual(s.prompt(), "")



class LengthTests(unittest.TestCase):
    """длина игры: случайные органы из всего набора, без повторов"""

    def test_game_length(self):
        self.assertEqual(game_length(10, 19), 10)
        self.assertEqual(game_length(20, 19), 19)          # органов меньше - спросим про все
        self.assertEqual(game_length(0, 19), 19)           # 0 - «все»
        self.assertEqual(game_length(None, 4), 4)
        self.assertIn(0, LENGTHS)

    def test_count_picks_distinct_organs(self):
        keys = for_body("female")
        for count in (5, 10):
            s = QuizSession(keys, rng=random.Random(count), count=count)
            self.assertEqual(s.total, count)
            self.assertEqual(len(set(s.q)), count)         # органы не повторяются
            self.assertTrue(set(s.q) <= set(keys))
            while not s.finished:
                self.assertTrue(s.answer(s.current))
            self.assertEqual(len(s.results), count)

    def test_games_differ(self):
        keys = for_body("male")
        games = {tuple(QuizSession(keys, rng=random.Random(seed), count=10).q) for seed in range(10)}
        self.assertGreater(len(games), 8)
        picked = set().union(*games)
        self.assertGreater(len(picked), 15)                # в разных играх попадаются разные органы

    def test_all_by_default(self):
        self.assertCountEqual(QuizSession(list(ORGANS), rng=random.Random(0)).q, ORGANS)


class MixedTests(unittest.TestCase):
    """режим «Вперемешку»: у каждого вопроса свой тип"""

    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE

    def test_kinds_are_mixed(self):
        s = QuizSession(list(ORGANS), rng=random.Random(4), mode="mix")
        self.assertEqual(len(s.kinds), s.total)
        self.assertTrue(set(s.kinds) <= set(KINDS))
        self.assertGreaterEqual(len(set(s.kinds)), 4)
        self.assertEqual(QuizSession(list(NAMES), rng=random.Random(0), mode="name").kinds, ["name"] * 4)

    def test_mixed_game_can_be_finished(self):
        for seed in range(5):
            for level in LEVELS:
                s = QuizSession(for_body("female"), rng=random.Random(seed), mode="mix", level=level, count=10)
                while not s.finished:
                    if s.kind != "find":
                        opts = s.options()
                        self.assertIn(s.correct(), opts)
                        self.assertTrue(all(s.option_label(o) for o in opts))
                    if s.kind in ("facts", "where"):
                        self.assertTrue(s.prompt())
                    self.assertTrue(s.answer(s.correct()))
                self.assertEqual(s.first_try, 10)

    def test_system_question(self):
        s = QuizSession(["pancreas"], rng=random.Random(0), pool=list(ORGANS), mode="system", level="hard")
        self.assertEqual(s.correct(), "@digestive")
        opts = s.options()
        self.assertEqual(len(opts), 6)
        self.assertNotIn("@endocrine", opts)               # вторая система органа - не неверный вариант
        self.assertTrue({o[1:] for o in opts} <= set(SYSTEMS))
        self.assertEqual(s.option_label("@digestive"), "Пищеварительная")
        self.assertEqual(s.answer_text(0), "Пищеварительная")
        i18n.set_lang("en")
        self.assertEqual(s.option_label("@digestive"), "Digestive")
        self.assertFalse(s.answer("pancreas"))
        self.assertTrue(s.answer("@digestive"))

    def test_where_question(self):
        s = QuizSession(["bladder"], rng=random.Random(0), pool=list(ORGANS), mode="where")
        self.assertEqual(s.prompt(), i18n.organ("bladder", "location"))
        self.assertIn("bladder", s.options())
        self.assertIsNone(s.answer_text(0))                # ответ - сам орган
        self.assertTrue(s.answer("bladder"))

    def test_location_that_names_organ_is_not_asked(self):
        for key in ORGANS:
            self.assertEqual("where" in kinds_for(key), not location_leaks(key), key)
            if "where" in kinds_for(key):
                for lang in ("ru", "en"):
                    i18n.set_lang(lang)
                    self.assertFalse(leaks(i18n.organ(key, "location"), key), (lang, key))
        self.assertIn("system", kinds_for("heart"))
        self.assertNotIn("system", kinds_for("a"))         # у выдуманного органа системы нет


class CustomAnswerTests(unittest.TestCase):
    """вопросы со своими вариантами ответа (answer / wrong в questions/*.json)"""

    Q = [{"level": "easy", "text": {"ru": "Что качает сердце?", "en": "What does the heart pump?"},
          "answer": {"ru": "Кровь", "en": "Blood"},
          "wrong": {"ru": ["Лимфу", "Воду", "Желчь"], "en": ["Lymph", "Water", "Bile"]}},
         {"level": "easy", "text": {"ru": "Сколько камер?"}, "answer": {"ru": "4"}, "wrong": {"ru": ["2", "3"]}}]

    def setUp(self):
        self.old = questions._cache
        questions._cache = {"heart": self.Q}

    def tearDown(self):
        questions._cache = self.old
        i18n._current = i18n._previous = i18n.BASE

    def session(self, idx, level="medium", **kw):
        s = QuizSession(["heart"], rng=random.Random(0), pool=list(ORGANS), mode="facts", level=level, **kw)
        s.prompts = {"heart": idx}
        return s

    def test_options_are_own_answers(self):
        s = self.session(0)
        self.assertTrue(s.custom())
        opts = s.options()
        self.assertEqual(len(opts), 4)
        self.assertIn("#0", opts)
        self.assertEqual({s.option_label(o) for o in opts}, {"Кровь", "Лимфу", "Воду", "Желчь"})
        i18n.set_lang("en")
        self.assertEqual(s.option_label("#0"), "Blood")

    def test_not_more_options_than_answers(self):
        s = self.session(1, level="hard")
        self.assertEqual(sorted(s.option_label(o) for o in s.options()), ["2", "3", "4"])
        i18n.set_lang("en")                          # без перевода - по-русски (числа одинаковы)
        self.assertEqual(s.option_label("#0"), "4")

    def test_only_the_answer_is_right(self):
        s = self.session(0)
        self.assertFalse(s.answer("heart"))          # орган здесь не ответ
        self.assertFalse(s.answer("#2"))
        self.assertTrue(s.answer("#0"))
        self.assertTrue(s.finished)
        self.assertEqual((s.errors, s.missed, s.results), (2, ["heart"], {"heart": False}))

    def test_timeout(self):
        clock = Clock()
        s = self.session(0, timer=5, clock=clock)
        s.start_timer()
        clock.t += 5
        self.assertEqual(s.time_up(), "heart")
        self.assertEqual(s.results, {"heart": False})

    def test_prompts_may_name_the_organ(self):
        prompts = [fact_prompts(["heart"], "easy", random.Random(i))["heart"] for i in range(20)]
        self.assertEqual(set(prompts), {0, 1})


class NewKindTests(unittest.TestCase):
    """вопросы «Вперемешку» о болезни, по латинскому названию и «верно ли»"""

    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE

    def kind(self, key, kind, seed=0, level="medium"):
        return QuizSession([key], rng=random.Random(seed), pool=list(ORGANS), mode=kind, level=level)

    def test_disease(self):
        s = self.kind("kidneys", "disease", level="hard")
        self.assertIn(s.prompt(), [diseases.text(d, "name") for d in disease_choices("kidneys")])
        opts = s.options()
        self.assertEqual(len(opts), 6)
        self.assertIn("kidneys", opts)
        self.assertNotIn("bladder", opts)                  # та же система - похожие болезни, не предлагаем
        self.assertIsNone(s.answer_text(0))
        i18n.set_lang("en")
        self.assertIn(s.prompt(), [diseases.name_in("en", d) for d in diseases.ON_CARD["kidneys"]])
        self.assertTrue(s.answer("kidneys"))

    def test_disease_never_names_an_organ_or_repeats(self):
        for key in ORGANS:
            for d in disease_choices(key):
                for code in ("ru", "en"):
                    text = diseases.name_in(code, d)
                    self.assertFalse(any(leaks(text, k) for k in ORGANS), (key, code, text))
        self.assertEqual(disease_choices("appendix"), [])         # «аппендицит» называет орган
        self.assertNotIn("appendicitis", disease_choices("intestines"))      # записан и у аппендикса
        self.assertNotIn("cystic_fibrosis", disease_choices("pancreas"))  # VAGUE_DISEASES: муковисцидоз
        for key, ds in VAGUE_DISEASES.items():                    # ключи из списка есть в карточках
            self.assertTrue(set(ds) <= set(diseases.ON_CARD[key]), key)

    def test_latin(self):
        s = self.kind("liver", "latin")
        self.assertEqual(s.prompt(), "Hepar")
        self.assertEqual(s.option_label("liver"), "Печень")
        i18n.set_lang("la")                                  # в латинском режиме варианты - не по-латыни
        self.assertEqual(s.option_label("liver"), "Печень")
        self.assertTrue(s.answer("liver"))

    def test_latin_part(self):
        """по латыни спрашивают и о части 3D-модели: «Myocardium» - часть какого органа"""
        from organism_atlas.quiz import latin_parts
        seen = set()
        for seed in range(30):
            s = self.kind("heart", "latin", seed)
            group = s.latin_part()
            seen.add(group is not None)
            if group:
                self.assertIn(group, latin_parts("heart"))
                self.assertEqual(s.prompt(), i18n.section("la", "parts")["heart"][group])
            else:
                self.assertEqual(s.prompt(), "Cor")
            self.assertTrue(s.answer("heart"))
        self.assertEqual(seen, {True, False})
        self.assertNotIn("duodenum", latin_parts("pancreas"))          # сосед для ориентира, а не часть органа
        self.assertNotIn("kidney_dim", latin_parts("adrenals"))
        for key in ORGANS:                                              # латынь части не называет орган
            for g in latin_parts(key):
                self.assertFalse(any(leaks(i18n.section("la", "parts")[key][g], k) for k in ORGANS), (key, g))

    def test_latin_only_when_not_obvious(self):
        self.assertTrue(latin_ok("liver"))
        self.assertTrue(latin_ok("pancreas"))                # Pancreas и «Поджелудочная железа» - не похожи
        i18n.set_lang("en")
        self.assertFalse(latin_ok("pancreas"))               # Pancreas - Pancreas
        self.assertFalse(latin_ok("trachea"))
        self.assertNotIn("latin", kinds_for("trachea"))

    def test_truth(self):
        seen = set()
        for seed in range(40):
            s = self.kind("heart", "truth", seed)
            owner, fid = s.picks[0]
            self.assertEqual(s.options(), ["?1", "?0"])
            self.assertEqual(s.correct(), "?1" if owner == "heart" else "?0")
            self.assertEqual(s.prompt(), i18n.fact(owner, fid))
            self.assertIn(fid, truth_facts(owner))
            if owner != "heart":                             # чужой факт - из органа другой системы
                self.assertFalse(set(ORGANS[owner]["systems"]) & set(ORGANS["heart"]["systems"]))
            self.assertEqual(s.option_label("?1"), "Верно")
            self.assertIn(s.answer_text(0), ("Верно", "Неверно"))
            seen.add(owner == "heart")
        self.assertEqual(seen, {True, False})                # бывают и правда, и неправда

    def test_truth_facts_skip_shared_and_naming(self):
        for key, ids in SHARED_FACTS.items():
            self.assertTrue(set(ids) <= {fid for fid, _ in i18n.facts(key)}, key)   # ключи из списка есть
            self.assertFalse(set(ids) & set(truth_facts(key)), key)
        self.assertEqual(truth_facts("spleen"), [])
        self.assertNotIn("truth", kinds_for("spleen"))
        for key in ORGANS:
            for fid in truth_facts(key):
                self.assertFalse(any(leaks(i18n.fact(key, fid), k) for k in ORGANS), key)

    def test_mixed_game_has_new_kinds(self):
        kinds = set()
        for seed in range(10):
            s = QuizSession(for_body("female"), rng=random.Random(seed), mode="mix", level="hard")
            while not s.finished:
                kinds.add(s.kind)
                if s.kind in ("disease", "latin", "truth"):
                    self.assertTrue(s.prompt())
                    self.assertIn(s.correct(), s.options())
                    self.assertTrue(all(s.option_label(o) for o in s.options()))
                self.assertTrue(s.answer(s.correct()))
        self.assertTrue({"disease", "latin", "truth"} <= kinds)


if __name__ == "__main__":
    unittest.main()
