import datetime
import os
import random
import tempfile
import unittest
from pathlib import Path

from organism_atlas import progress
from organism_atlas.quiz import QuizSession

DAY = datetime.date(2026, 10, 25)
NOW = datetime.datetime(2026, 10, 25, 14, 3)


def played(keys, wrong=(), mode="find", seed=0):
    """сыграть игру: на органах из wrong один раз ошибиться"""
    s = QuizSession(keys, rng=random.Random(seed), mode=mode)
    while not s.finished:
        if s.current in wrong and not s.slipped:
            s.answer(next(k for k in keys if k != s.current))
        s.answer(s.current)
    return s


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name, "sub", "progress.json")
        self.old = os.environ.get("ORGANISM_ATLAS_PROGRESS")
        os.environ["ORGANISM_ATLAS_PROGRESS"] = str(self.file)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("ORGANISM_ATLAS_PROGRESS", None)
        else:
            os.environ["ORGANISM_ATLAS_PROGRESS"] = self.old
        self.tmp.cleanup()

    def test_empty_and_broken_files(self):
        self.assertEqual(progress.load(), {"results": [], "cards": {}})
        self.file.parent.mkdir(parents=True)
        for text in ("{oops", "[1]", '{"results": 5, "cards": []}'):
            self.file.write_text(text, encoding="utf-8")
            self.assertEqual(progress.load(), {"results": [], "cards": {}}, text)

    def test_record_result(self):
        progress.record(played(["a", "b", "c"], wrong=["b"]), "all", today=DAY, now=NOW)
        r = progress.load()["results"][-1]
        self.assertEqual((r["date"], r["mode"], r["total"], r["first_try"], r["errors"], r["missed"]),
                         ("2026-10-25T14:03", "find", 3, 2, 1, ["b"]))
        self.assertEqual(progress.recent("find"), [r])
        self.assertEqual(progress.recent("name"), [])
        self.assertEqual(progress.last_missed("find", ["a", "b", "c"]), ["b"])
        self.assertEqual(progress.last_missed("find", ["a"]), [])        # органа больше нет в списке

    def test_leitner_intervals(self):
        keys = ["a", "b"]
        day = DAY
        for expected in (1, 2, 4, 8, 16, 16):                # верно каждый раз, когда подходит срок
            progress.record(played(keys), today=day)
            card = progress.load()["cards"]["find:a"]
            due = datetime.date.fromisoformat(card["due"])
            self.assertEqual((due - day).days, expected)
            self.assertEqual(progress.due("find", keys, today=due - datetime.timedelta(days=1)), [])
            self.assertEqual(progress.due("find", keys, today=due), keys)
            day = due

    def test_mistake_resets_card_and_is_due_today(self):
        keys = ["a", "b"]
        for _ in range(3):
            progress.record(played(keys), today=DAY)
        progress.record(played(keys, wrong=["a"]), today=DAY)
        cards = progress.load()["cards"]
        self.assertEqual((cards["find:a"]["box"], cards["find:a"]["wrong"], cards["find:a"]["seen"]), (1, 1, 4))
        self.assertEqual(cards["find:b"]["box"], 4)
        self.assertEqual(progress.due("find", keys, today=DAY), ["a"])
        self.assertEqual(progress.due("name", keys, today=DAY), [])     # у каждого режима свои карточки

    def test_most_overdue_first(self):
        keys = ["a", "b"]
        progress.record(played(["b"]), today=DAY)                      # b: срок через день
        progress.record(played(["a"]), today=DAY + datetime.timedelta(days=3))
        self.assertEqual(progress.due("find", keys, today=DAY + datetime.timedelta(days=10)), ["b", "a"])

    def test_history_is_trimmed(self):
        for i in range(progress.KEEP + 5):
            progress.record(played(["a"], seed=i), today=DAY)
        self.assertEqual(len(progress.load()["results"]), progress.KEEP)


if __name__ == "__main__":
    unittest.main()
