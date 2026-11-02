"""Новые виды викторины без окна: «Расставь по порядку», «Экзамен», «Испытание дня», «Угадай по 3D»."""

import datetime
import os
import random
import tempfile
import unittest
from pathlib import Path

from organism_atlas import achievements, i18n, order, progress
from organism_atlas.organs import ORGANS, for_body
from organism_atlas.quiz import EXAM_GRADES, MODES, QuizSession, daily_session

DAY = datetime.date(2026, 11, 2)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class OrderTests(unittest.TestCase):
    def test_routes(self):
        for route, keys in order.ROUTES.items():
            self.assertTrue(set(keys) <= set(ORGANS), route)
            for code in ("ru", "en"):
                self.assertTrue(i18n._load(code)["ui"].get("route_" + route), (code, route))
        self.assertEqual(order.steps("urine", "female"), ["kidneys", "bladder"])
        self.assertEqual(order.steps("urine", "male"), ["kidneys", "bladder", "prostate"])
        for body in ("female", "male"):
            self.assertEqual(order.available(body), list(order.ROUTES))

    def test_play_in_order(self):
        s = order.OrderSession(["food"], body="male", rng=random.Random(0), level="hard")
        self.assertEqual(len(s.options()), len(order.ROUTES["food"]) + order.DISTRACTORS["hard"])
        self.assertEqual(s.correct(), "esophagus")
        self.assertEqual(s.step("rectum"), "wrong")                 # не по порядку - ошибка, маршрут тот же
        self.assertEqual((s.errors, s.missed, s.placed), (1, ["food"], []))
        for k in ("esophagus", "stomach", "intestines"):
            self.assertEqual(s.step(k), "right")
        self.assertEqual(s.step("rectum"), "done")
        self.assertTrue(s.finished)
        self.assertEqual((s.first_try, s.results), (0, {"food": False}))   # с ошибкой - не с первой попытки

    def test_clean_route_and_time(self):
        clock = Clock()
        s = order.OrderSession(["bile", "stress"], body="female", rng=random.Random(1), timer=10, clock=clock,
                               level="easy")
        self.assertEqual(set(s.options()), set(s.route()))         # на лёгком - без лишних органов
        for k in s.route():
            s.step(k)
        self.assertEqual(s.first_try, 1)
        s.start_timer()
        clock.now = 11
        self.assertIsNotNone(s.time_up())
        self.assertTrue(s.finished)
        self.assertEqual((s.timeouts, s.percent), (1, 50))

    def test_recorded_like_quiz(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("ORGANISM_ATLAS_PROGRESS")
            os.environ["ORGANISM_ATLAS_PROGRESS"] = str(Path(tmp, "p.json"))
            try:
                s = order.OrderSession(["food"], rng=random.Random(0))
                for k in s.route():
                    s.step(k)
                data = progress.record(s, today=DAY)
                self.assertEqual(data["results"][-1]["mode"], "order")
                self.assertIsNone(data["results"][-1]["organs"])     # не «Марафон»
                self.assertIn("order:food", data["cards"])
            finally:
                if old is None:
                    os.environ.pop("ORGANISM_ATLAS_PROGRESS")
                else:
                    os.environ["ORGANISM_ATLAS_PROGRESS"] = old


class ExamTests(unittest.TestCase):
    def exam(self, n=6, seed=3):
        clock = Clock()
        keys = for_body("male")
        return QuizSession(keys, rng=random.Random(seed), pool=keys, mode="exam", count=n, single_try=True,
                           total_time=n * 30, clock=clock), clock

    def test_one_try_and_grade(self):
        s, _ = self.exam()
        s.start_timer()
        wrong = next(o for o in s.options() if o != s.correct()) if s.kind not in ("find",) else "nothing"
        self.assertFalse(s.answer(wrong))
        self.assertEqual((s.i, s.errors), (1, 1))                   # ошибка - сразу следующий вопрос
        while not s.finished:
            s.answer(s.correct())
        self.assertEqual((s.first_try, s.total), (5, 6))
        self.assertEqual(s.grade, 4)                                 # 83 %
        (i, key, given), = s.mistakes()
        self.assertEqual((i, given), (0, wrong))
        self.assertTrue(s.prompt_at(0) or s.kinds[0] in ("find", "name", "system"))
        self.assertEqual([g for _, g in EXAM_GRADES][0], 5)

    def test_shared_time_and_finish(self):
        s, clock = self.exam()
        s.start_timer()
        s.answer(s.correct())
        self.assertAlmostEqual(s.remaining(), 180)                 # время общее, не сбрасывается на вопрос
        clock.now = 181
        s.time_up()
        self.assertTrue(s.finished)
        self.assertEqual((s.first_try, s.timeouts, s.total), (1, 5, 6))
        s2, _ = self.exam()
        s2.answer(s2.correct())
        s2.finish_all()                                              # «Завершить»: остальные - без ответа
        self.assertEqual((s2.total, s2.first_try, s2.grade), (6, 1, 2))
        self.assertIsNone(s2.given_text(5, None))

    def test_exams_and_daily_do_not_move_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("ORGANISM_ATLAS_PROGRESS")
            os.environ["ORGANISM_ATLAS_PROGRESS"] = str(Path(tmp, "p.json"))
            try:
                s, _ = self.exam(n=10)                            # «Отличник» - экзамен из 10 вопросов и больше
                while not s.finished:
                    s.answer(s.correct())
                data = progress.record(s, today=DAY)
                self.assertEqual(data["cards"], {})
                self.assertIn("exam5", data["earned"])
            finally:
                if old is None:
                    os.environ.pop("ORGANISM_ATLAS_PROGRESS")
                else:
                    os.environ["ORGANISM_ATLAS_PROGRESS"] = old


class DailyTests(unittest.TestCase):
    def test_same_questions_for_everyone_today(self):
        a, b = daily_session("male", DAY), daily_session("male", DAY)
        self.assertEqual((a.q, a.kinds), (b.q, b.kinds))
        self.assertEqual(a.options(), b.options())
        self.assertEqual(a.total, 10)
        other = daily_session("male", DAY + datetime.timedelta(days=1))
        self.assertNotEqual(a.q, other.q)
        self.assertTrue(set(daily_session("female", DAY).q) <= set(for_body("female")))

    def test_daily_streak_achievement(self):
        game = lambda d, mode="daily": {"date": d.isoformat() + "T10:00", "mode": mode, "total": 10, "first_try": 5}
        data = {"results": [game(DAY - datetime.timedelta(days=i)) for i in range(4)], "cards": {}}
        self.assertEqual(achievements.mode_streak(data, "daily", DAY), 4)
        self.assertNotIn("daily", achievements.earned(data))
        data["results"].append(game(DAY - datetime.timedelta(days=4)))
        self.assertIn("daily", achievements.earned(data))
        self.assertEqual(progress.today_results("daily", data, DAY), [data["results"][0]])


class ModelTests(unittest.TestCase):
    def test_model_kind(self):
        keys = for_body("female")
        s = QuizSession(keys, rng=random.Random(0), pool=keys, mode="model")
        self.assertEqual(set(s.kinds), {"model"})
        self.assertIn(s.current, s.options())
        self.assertEqual(s.option_label(s.current), i18n.name(s.current))
        self.assertTrue(s.answer(s.current))

    def test_all_modes_have_texts(self):
        for code in ("ru", "en"):
            ui = i18n._load(code)["ui"]
            for m in MODES:
                self.assertTrue(ui.get("mode_" + m) and ui.get("setup_desc_" + m), (code, m))


if __name__ == "__main__":
    unittest.main()
