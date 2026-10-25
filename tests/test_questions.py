import json
import tempfile
import unittest
from pathlib import Path

from organism_atlas import i18n, questions
from organism_atlas.organs import ORGANS
from organism_atlas.quiz import leaks


class QuestionFilesTests(unittest.TestCase):
    """проверки, которые ловят ошибки при ручной правке questions/*.json"""

    def test_files_are_valid_and_named_after_organs(self):
        data = questions.load_all(questions.DIR, known=list(ORGANS))
        self.assertEqual(set(data), set(ORGANS))

    def test_every_level_has_questions(self):
        for key in ORGANS:
            levels = {q["level"] for q in questions.for_organ(key)}
            for level, pool in questions.POOL.items():
                self.assertTrue(levels & set(pool), (key, level))

    def test_no_question_names_its_organ(self):
        for key in ORGANS:
            for n, q in enumerate(questions.for_organ(key), 1):
                if "answer" in q:                    # свои варианты: ответ - не орган, называть его можно
                    continue
                for lang, text in q["text"].items():
                    self.assertFalse(leaks(text, key), "questions/%s.json, вопрос %d (%s): %s" % (key, n, lang, text))

    def test_checker_reports_nothing_wrong(self):
        self.assertFalse([line for line in questions.check() if "!" in line])


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        i18n._current = i18n._previous = i18n.BASE
        self.tmp.cleanup()

    def write(self, name, content):
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        (self.dir / name).write_text(text, encoding="utf-8")

    def error(self):
        with self.assertRaises(ValueError) as cm:
            questions.load_all(self.dir, known=["heart"])
        return str(cm.exception)

    def test_reads_questions_and_ignores_comments(self):
        self.write("heart.json", {"_comment": "x", "questions": [
            {"level": "hard", "ru": " Вопрос ", "en": "Question", "_note": "для себя"}]})
        self.assertEqual(questions.load_all(self.dir, known=["heart"]),
                         {"heart": [{"level": "hard", "text": {"ru": "Вопрос", "en": "Question"}}]})

    def test_broken_json_names_file_and_line(self):
        self.write("heart.json", '{"questions": [\n  {"level": "easy" "ru": "x"}\n]}')
        msg = self.error()
        self.assertIn("questions/heart.json", msg)
        self.assertIn("строка 2", msg)

    def test_bad_level(self):
        self.write("heart.json", {"questions": [{"level": "easy", "ru": "a"}, {"level": "medum", "ru": "b"}]})
        msg = self.error()
        self.assertIn("вопрос 2", msg)
        self.assertIn("medum", msg)

    def test_russian_text_required(self):
        self.write("heart.json", {"questions": [{"level": "easy", "en": "only English"}]})
        self.assertIn("нет текста на русском", self.error())

    def test_empty_text(self):
        self.write("heart.json", {"questions": [{"level": "easy", "ru": "a", "en": "  "}]})
        self.assertIn("«en» пустой", self.error())

    def test_wrong_shape(self):
        self.write("heart.json", [1, 2])
        self.assertIn("questions", self.error())

    def test_unknown_organ_file(self):
        self.write("hart.json", {"questions": []})
        self.assertIn("нет органа «hart»", self.error())

    def test_custom_answers_same_in_all_languages(self):
        self.write("heart.json", {"questions": [
            {"level": "medium", "ru": "Сколько камер?", "answer": "4", "wrong": ["2", "3"]}]})
        q = questions.load_all(self.dir, known=["heart"])["heart"][0]
        self.assertEqual((q["answer"], q["wrong"]), ({"ru": "4"}, {"ru": ["2", "3"]}))

    def test_custom_answers_per_language(self):
        self.write("heart.json", {"questions": [
            {"level": "easy", "ru": "Что?", "answer": {"ru": "Кровь", "en": "Blood"},
             "wrong": {"ru": ["Вода"], "en": ["Water"]}}]})
        q = questions.load_all(self.dir, known=["heart"])["heart"][0]
        self.assertEqual(q["wrong"]["en"], ["Water"])

    def test_custom_answer_errors(self):
        cases = [
            ({"answer": "4"}, "оба поля"),
            ({"wrong": ["2"]}, "оба поля"),
            ({"answer": {"en": "4"}, "wrong": ["2"]}, "на русском"),
            ({"answer": "4", "wrong": []}, "непустой список"),
            ({"answer": "4", "wrong": "2"}, "непустой список"),
            ({"answer": " ", "wrong": ["2"]}, "answer «ru» пустой"),
            ({"answer": "4", "wrong": ["2", "4"]}, "есть и среди неверных"),
            ({"answer": {"ru": "а", "en": "a"}, "wrong": {"ru": ["б", "в"], "en": ["b"]}}, "разное число"),
        ]
        for extra, expected in cases:
            self.write("heart.json", {"questions": [{"level": "easy", "ru": "Вопрос?", **extra}]})
            self.assertIn(expected, self.error(), extra)

    def test_text_falls_back_to_russian(self):
        q = [{"level": "easy", "text": {"ru": "по-русски"}}, {"level": "easy", "text": {"ru": "р", "en": "e"}}]
        old = questions._cache
        questions._cache = {"heart": q}
        try:
            i18n.set_lang("en")
            self.assertEqual((questions.text("heart", 0), questions.text("heart", 1)), ("по-русски", "e"))
        finally:
            questions._cache = old


if __name__ == "__main__":
    unittest.main()
