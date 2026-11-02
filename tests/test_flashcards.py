"""Флеш-карточки: колоды, порядок карточек в подходе и коробки Лейтнера (без Qt)."""

import datetime
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from organism_atlas import flashcards, i18n, progress, questions, stats
from organism_atlas.organs import ORGANS, for_body
from organism_atlas.quiz import leaks
from organism_atlas.structures import STRUCTURES

DAY = datetime.date(2026, 11, 3)


class FlashcardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"ORGANISM_ATLAS_PROGRESS": str(Path(self.tmp.name, "p.json"))})
        env.start()
        self.addCleanup(env.stop)
        i18n.load_all()
        questions.load_all(known=list(ORGANS))

    def test_decks(self):
        for deck in flashcards.DECKS:
            keys = flashcards.items(deck, "female")
            self.assertTrue(keys, deck)
            self.assertEqual(len(keys), len(set(keys)), deck)
            for key in keys:
                c = flashcards.card(deck, key, "female")
                self.assertTrue(c["title"] and c["prompt"] and c["answer"], (deck, key))
        self.assertEqual(set(flashcards.items("organs", "male")), set(for_body("male")))
        self.assertIn("femur", flashcards.items("latin", "male"))                # кости и мышцы - тоже
        self.assertEqual(flashcards.card("latin", "femur", "male")["answer"], "Femur")
        self.assertNotIn("pcos", flashcards.items("diseases", "male"))           # болезни органов другого пола - нет
        self.assertIn("pcos", flashcards.items("diseases", "female"))

    def test_fact_cards_do_not_give_the_answer_away(self):
        """вопрос без своих вариантов не называет орган, а подсветка органа - только вместе с ответом"""
        for item in flashcards.items("facts", "female"):
            key, _, idx = item.partition("#")
            c = flashcards.card("facts", item, "female")
            self.assertFalse(c["spot_first"])
            if not questions.has_answers(key, int(idx)):
                self.assertFalse(leaks(c["prompt"], key), item)
                self.assertEqual(c["answer"], i18n.name(key))

    def test_latin_mode_swaps_sides(self):
        """с латинскими названиями лицевая сторона - всё равно название на языке интерфейса"""
        i18n.set_latin(True)
        self.addCleanup(i18n.set_latin, False)
        c = flashcards.card("latin", "heart", "female")
        self.assertEqual((c["title"], c["answer"]), ("Сердце", "Cor"))

    def test_session_order_and_boxes(self):
        """сначала - то, что пора повторить, потом новые; «помню» двигает коробку, «не помню» - в первую"""
        keys = flashcards.items("organs", "female")
        s = flashcards.start("organs", "female", size=5, rng=random.Random(1), today=DAY)
        self.assertEqual(len(s.keys), 5)
        self.assertTrue(set(s.keys) <= set(keys))
        first, second = s.keys[:2]
        s.reveal()
        s.answer(True, today=DAY)
        s.reveal()
        s.answer(False, today=DAY)
        cards = progress.load()["cards"]
        self.assertEqual(cards["flash_organs:" + first]["box"], 1)
        self.assertEqual(cards["flash_organs:" + first]["due"], (DAY + datetime.timedelta(days=1)).isoformat())
        self.assertEqual(cards["flash_organs:" + second]["box"], 1)
        self.assertEqual(cards["flash_organs:" + second]["due"], DAY.isoformat())   # не вспомнили - снова сегодня
        self.assertEqual(flashcards.due_count("organs", "female", today=DAY), 1)
        nxt = flashcards.start("organs", "female", size=len(keys), rng=random.Random(2), today=DAY)
        self.assertIn(second, nxt.keys)
        later = flashcards.start("organs", "female", size=1, rng=random.Random(3), today=DAY)
        self.assertEqual(later.keys, [second])                   # пора повторить - раньше новых
        while not s.finished:
            s.reveal()
            s.answer(True, today=DAY)
        self.assertEqual(len(s.knew), 5)
        self.assertIsNone(s.current)
        self.assertIn(first, stats.mastery(progress.load()))      # карточки органов идут в карту знаний

    def test_structures_are_known(self):
        self.assertTrue(set(flashcards.items("latin", "female")) & set(STRUCTURES))


if __name__ == "__main__":
    unittest.main()
