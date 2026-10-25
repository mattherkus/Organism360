import random
import unittest

from organism_atlas import i18n, questions
from organism_atlas.organs import ORGANS
from organism_atlas.quiz import (LEVELS, OPTIONS, QuizSession, fact_prompts, format_time, leaks,
                                 prompt_text)

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


if __name__ == "__main__":
    unittest.main()
