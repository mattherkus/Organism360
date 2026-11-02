"""Викторина в окне: карточка настройки, вопросы, таймер, ответы кликом по схеме и кнопками, итоги.

QuizController ведёт игру (quiz.QuizSession) и всё, что к ней относится в интерфейсе: настройки игры,
кнопки-варианты, шапку с прогрессом и временем, отзыв о прошлом ответе, запись результата и итоги.
Окно (App) даёт ему режим, карточку справа, органы схемы и подсветку на схеме (flash, reveal, show_target)."""

import math
import traceback

from PySide6.QtCore import QTimer

from .. import achievements, i18n, progress, settings
from ..i18n import t
from ..organs import ORGANS, SYSTEMS, in_system
from ..quiz import LENGTHS, LEVELS, MODES, TIMERS, QuizSession, format_time, game_length
from .achievements import button_text as achievements_text, show_achievements
from .cards import fill_card, fill_question, fill_setup, mark
from .results import fill_results
from .widgets import alive


def timer(parent, fn, ms=None):
    """однократный таймер: start(мс) - вызвать fn через столько-то, stop() - отменить, isActive() - ждёт ли"""
    tm = QTimer(parent)
    tm.setSingleShot(True)
    tm.timeout.connect(fn)
    if ms is not None:
        tm.setInterval(ms)
    return tm


class QuizController:
    def __init__(self, app):
        self.app = app
        saved = settings.load()
        # настройки викторины: сложность, таймер и длина переживают перезапуск, тема и набор вопросов - нет
        self.cfg = {"level": settings.get(saved, "quiz_level"), "timer": settings.get(saved, "quiz_timer"),
                    "length": settings.get(saved, "quiz_length"), "topic": None, "set": "all"}
        self.session = None                    # QuizSession во время игры (None - на карточке настройки)
        self.qset = "all"                      # набор вопросов текущей игры (для истории)
        self.choices = {}                      # {ключ варианта: кнопка} в вопросах с вариантами
        self.progress = None                   # шапка вопроса: «Вопрос N из M · Ошибок: K» и полоски
        self.feedback = None                   # (ключ текста, орган, цвет[, вопрос]) - отзыв о прошлом ответе
        self.wrong = set()                     # неверно выбранные варианты текущего вопроса
        self.new_achievements, self.streak = [], 0        # для итогов игры: новые достижения и серия дней
        self.next_timer = timer(app, self.next_question, 700)
        self.tick_timer = timer(app, self.tick, 100)
        self.results_timer = timer(app, self.show_results, 600)

    @property
    def mode(self):
        return self.app.mode

    def kind(self):
        """тип текущего вопроса (quiz.KINDS); None - игры нет или она закончена"""
        s = self.session
        return s.kind if s is not None and not s.finished else None

    def target(self):
        """орган, подсвеченный на схеме как вопрос («Угадай название»), или None"""
        s = self.session
        return s.current if s is not None and s.kind == "name" else None

    def stop(self):
        """прервать текущую игру: таймеры, подсветка, кнопки-варианты"""
        for tm in (self.next_timer, self.tick_timer, self.results_timer):
            tm.stop()
        self.app.unreveal()
        self.session = None
        self.choices = {}
        if self.app.atlas:
            self.app.on_leave()
            self.app.view.show_layer("target", None)

    # --- настройка викторины
    def question_keys(self, qset, data=None):
        """органы набора вопросов qset (all, missed, due) в выбранной теме"""
        keys = in_system(self.app.organs(), self.cfg["topic"])
        if qset == "missed":
            return progress.last_missed(self.mode, keys, data)
        if qset == "due":
            return progress.due(self.mode, keys, data)
        return keys

    def topics(self):
        """темы викторины: [(система или None - все органы, сколько органов)]; системы из одного органа
        не предлагаются - по ним нечего спрашивать"""
        organs = self.app.organs()
        out = [(None, len(organs))]
        for name in SYSTEMS:
            n = len(in_system(organs, name))
            if n >= 2:
                out.append((name, n))
        return out

    def render_setup(self):
        data = progress.load()
        topics = self.topics()
        if self.cfg["topic"] not in dict(topics):
            self.cfg["topic"] = None
        counts = {q: len(self.question_keys(q, data)) for q in ("all", "missed", "due")}
        if not counts.get(self.cfg["set"]):
            self.cfg["set"] = "all"
        n = counts[self.cfg["set"]]
        length = self.cfg["length"] if 0 < self.cfg["length"] < n else 0     # длиннее набора - значит «все»
        rows = [
            (t("setup_mode"), [(t("mode_" + m), m, True) for m in MODES], self.mode, self.app.set_mode, None, 2),
            (t("setup_level"), [(t("level_" + v), v, True) for v in LEVELS], self.cfg["level"],
             lambda v: self.set_cfg("level", v), t("level_hint_" + self.cfg["level"]), False),
            (t("setup_timer"), [(t("timer_sec", sec=v) if v else t("timer_off"), v, True) for v in TIMERS],
             self.cfg["timer"], lambda v: self.set_cfg("timer", v), None, False),
            (t("setup_length"), [(t("length_all", n=n) if not v else str(v), v, not v or v < n) for v in LENGTHS],
             length, lambda v: self.set_cfg("length", v), None, False),
            (t("setup_topic"), [(t("topic_all", n=k) if name is None else
                                 t("topic_system", system=t("system_" + name), n=k), name, True) for name, k in topics],
             self.cfg["topic"], lambda v: self.set_cfg("topic", v), None, 2),
            (t("setup_set"), [(t("set_" + q, n=counts[q]), q, counts[q] > 0) for q in ("all", "missed", "due")],
             self.cfg["set"], lambda v: self.set_cfg("set", v), t("setup_set_hint"), True),
        ]
        history = [t("history_line", date=short_date(r.get("date")), level=t("level_" + r.get("level", "medium")),
                     right=r.get("first_try", 0), total=r.get("total", 0), time=format_time(r.get("seconds", 0)))
                   for r in progress.recent(self.mode, 3, data)
                   if r.get("level") in LEVELS] or [t("history_empty")]
        fill_setup(self.app.card, t("mode_" + self.mode), t("setup_desc_" + self.mode), rows, t("setup_start"),
                   self.start, t("setup_history"), history)

    def set_cfg(self, key, value):
        self.cfg[key] = value
        if key in ("level", "timer", "length"):
            settings.save(**{"quiz_" + key: value})
        self.app.set_card(self.render_setup)

    def review(self, mode):
        """кнопка «Повторить»: викторина mode по органам, которые пора повторить"""
        self.app.set_mode(mode)
        self.cfg["topic"] = None
        self.cfg["set"] = "due"
        self.start("due")

    def start(self, qset=None):
        """начать игру по текущим настройкам; qset - другой набор вопросов (кнопка «Повторить ошибки»)"""
        qset = qset or self.cfg["set"]
        keys = self.question_keys(qset)
        if not keys:
            qset, keys = "all", self.question_keys("all")
        self.stop()
        self.qset = qset
        self.session = QuizSession(keys, pool=self.app.organs(), mode=self.mode, level=self.cfg["level"],
                                   timer=self.cfg["timer"], count=game_length(self.cfg["length"], len(keys)))
        self.ask()

    # --- вопросы
    def progress_text(self):
        s = self.session
        text = t("progress", n=s.i + 1, total=s.total, errors=s.errors)
        rem = s.remaining()
        return text + "  ·  " + t("progress_timer", sec=math.ceil(rem)) if rem is not None else text

    def progress_state(self):
        """(строка, доля пройденных вопросов, доля оставшегося времени или None) для шапки вопроса"""
        s = self.session
        rem = s.remaining()
        return self.progress_text(), s.i / max(1, s.total), None if rem is None else rem / s.timer

    def update_progress(self):
        if alive(self.progress):
            self.progress.set(*self.progress_state())

    def ask(self, feedback=None):
        """показать текущий вопрос в карточке справа;
        feedback - (ключ текста, орган, цвет[, номер вопроса со своими вариантами]): отзыв о прошлом ответе"""
        s = self.session
        if s.finished:
            self.app.set_status(lambda: "")            # итоги - в карточке справа, строка статуса не нужна
            return
        if s.deadline is None:                          # новый вопрос на экране - запускаем его время
            s.start_timer()
            self.tick_timer.stop()
            self.tick()
        self.feedback, self.wrong = feedback, set()
        self.app.set_status(lambda: t("quiz_status", mode=t("mode_" + self.mode)))
        self.app.set_card(self.render_question)

    def render_question(self):
        s = self.session
        card = self.app.card
        fb = self.feedback and (self.feedback_text(*self.feedback), self.feedback[2])
        if s.kind == "find":
            self.progress, self.choices = fill_question(
                card, self.progress_state(), t("find_title", name=i18n.name(s.current)),
                t("find_hint"), fb, give_up=(t("give_up"), self.give_up))
            self.app.show_target()                      # во «Вперемешку» прячет подсветку прошлого вопроса
            return
        opts = s.options()
        if s.kind == "facts" and s.custom():             # вопрос со своими вариантами ответа
            title, hint = s.prompt(), t("custom_hint", n=len(opts))
        elif s.kind == "facts":
            title, hint = "«%s»" % s.prompt(), t("facts_hint", n=len(opts))
        elif s.kind == "where":
            title, hint = "«%s»" % s.prompt(), t("where_hint", n=len(opts))
        elif s.kind == "system":
            title, hint = t("system_title", name=i18n.name(s.current)), t("custom_hint", n=len(opts))
        elif s.kind == "disease":
            title, hint = "«%s»" % s.prompt(), t("disease_hint", n=len(opts))
        elif s.kind == "latin":
            title, hint = s.prompt(), t("latin_hint", n=len(opts))
        elif s.kind == "truth":
            title, hint = "«%s»" % s.prompt(), t("truth_hint", name=i18n.name(s.current))
        else:
            title, hint = t("name_title"), t("name_hint", n=len(opts))
        self.progress, self.choices = fill_question(
            card, self.progress_state(), title, hint, fb, [(k, s.option_label(k)) for k in opts], self.pick,
            give_up=(t("give_up"), self.give_up))
        for k in self.wrong:
            mark(self.choices[k], "wrong_bg")
        self.app.show_target()

    def feedback_text(self, key, organ, _color, i=None):
        """текст отзыва на текущем языке; i - номер вопроса, ответ на который не орган: назвать верный ответ"""
        if i is not None:
            return t(key, answer=self.session.answer_text(i))
        return t(key, name=i18n.name(organ))

    def tick(self):
        """раз в четверть секунды: обновить остаток времени, а когда он вышел - показать ответ и идти дальше"""
        s = self.session
        if s is None or s.finished or s.remaining() is None:
            return
        if not self.next_timer.isActive():              # во время зелёной паузы после ответа не считаем
            i = s.i if s.answer_text(s.i) is not None else None      # ответ - не орган: назовём его
            key = s.time_up()
            if key:
                self.skipped(key, i, "time_up", s.level == "easy")
                return
            self.update_progress()
        self.tick_timer.start()

    def give_up(self):
        """кнопка «Сдаться»: показать верный ответ (ошибка засчитывается) и закончить игру - сразу итоги"""
        s = self.session
        if s is None or s.finished or self.next_timer.isActive():
            return
        i = s.i if s.answer_text(s.i) is not None else None
        self.skipped(s.give_up(), i, "gave_up", True)

    def skipped(self, key, i, text, reveal):
        """вопрос пропущен (время вышло или «Сдаться»): показать, где был нужный орган, и задать следующий;
        i - номер вопроса, если ответ на него - не орган (тогда отзыв называет ответ словами);
        text - ключ отзыва (с «_answer» - для такого вопроса); reveal - ещё и подписать орган на схеме"""
        s = self.session
        self.app.unreveal()
        self.app.flash(key, "ok")
        if reveal:
            self.app.reveal(key)
        if s.finished:
            self.finish(key)
            return
        self.ask((text, key, "bad") if i is None else (text + "_answer", key, "bad", i))

    def hint_wrong(self):
        """после ошибки на лёгком уровне - подсказка, если ответ на вопрос - орган"""
        s = self.session
        if s is not None and not s.finished and s.level == "easy" and s.correct() in ORGANS:
            self.app.reveal(s.correct())

    def answer(self, key):
        """клик по органу в режиме «Найди орган»"""
        s = self.session
        if s is None or s.finished:
            return
        right = s.answer(key)
        self.app.flash(key, "ok" if right else "bad")
        if not right:
            self.ask(("answer_wrong", key, "bad"))
            self.hint_wrong()
            return
        self.app.unreveal()
        if s.finished:
            self.finish(key)
            return
        self.ask(("answer_right", key, "ok"))

    def pick(self, key):
        """выбран вариант ответа (кнопкой или цифрой)"""
        s = self.session
        if s is None or s.finished or self.next_timer.isActive() or key not in self.choices:
            return
        asked = s.current
        right = s.answer(key)
        btn = self.choices[key]
        if not right:
            self.wrong.add(key)
            mark(btn, "wrong_bg")
            self.update_progress()
            self.hint_wrong()
            return
        self.app.unreveal()
        mark(btn, "right_bg")
        self.app.flash(asked, "ok")
        self.next_timer.start()

    def next_question(self):
        self.next_timer.stop()
        s = self.session
        if s is None:
            return
        if s.finished:
            self.finish(s.q[-1])
            return
        self.ask()

    def finish(self, last):
        """игра закончена: сохранить результат, показать карточку последнего органа, а следом - итоги"""
        s = self.session
        app = self.app
        self.choices = {}
        app.view.show_layer("target", None)
        self.new_achievements, self.streak = [], 0
        try:
            before = progress.load()
            after = progress.record(s, self.qset)
            self.new_achievements = achievements.new_ones(before, after)
            self.streak = achievements.streak(after)
            app.ach_button.setText(achievements_text(after))
        except Exception:                               # история - не повод сорвать конец игры
            traceback.print_exc()
        app.set_card(lambda: fill_card(app.card, last))
        self.ask()
        self.results_timer.start()

    def on_key(self, keysym, char):
        """Enter на карточке настройки начинает игру, цифры выбирают вариант ответа"""
        if self.session is None:
            if keysym in ("Return", "KP_Enter"):
                self.start()
            return
        if self.kind() != "find" and char.isdigit():
            keys = list(self.choices)
            i = int(char) - 1
            if 0 <= i < len(keys):
                self.pick(keys[i])

    def show_results(self):
        s, mode, app = self.session, self.mode, self.app
        if s is None or app.mode != s.mode:             # пока ждали, пользователь ушёл в другой режим
            return

        def again(qset=None):
            if app.mode == mode:
                self.start(qset)

        due = len(progress.due(mode, app.organs()))
        new, streak = self.new_achievements, self.streak
        # итоги - в карточке справа, на месте карточки последнего органа
        app.set_card(lambda: fill_results(app.card, s, on_again=again, on_retry=lambda: again("missed"),
                                          on_setup=lambda: app.set_mode(mode), due=due, streak=streak, new=new,
                                          on_achievements=lambda: show_achievements(app)))


def short_date(iso):
    """'2026-10-25T14:03' -> '25.10 14:03'"""
    try:
        d, hm = (iso or "").split("T")
        return "%s.%s %s" % (d[8:10], d[5:7], hm[:5])
    except ValueError:
        return iso or ""
