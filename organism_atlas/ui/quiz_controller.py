"""Викторина в окне: карточка настройки, вопросы, таймер, ответы кликом по схеме и кнопками, итоги.

QuizController ведёт игру (quiz.QuizSession) и всё, что к ней относится в интерфейсе: настройки игры,
кнопки-варианты, шапку с прогрессом и временем, отзыв о прошлом ответе, запись результата и итоги.
Окно (App) даёт ему режим, карточку справа, органы схемы и подсветку на схеме (flash, reveal, show_target)."""

import math
import traceback

from PySide6.QtCore import QTimer

from .. import achievements, i18n, notes, order, progress, settings, structures
from ..i18n import t
from ..organs import ORGANS, SYSTEMS, in_system
from ..quiz import (EXAM_SECONDS, LENGTHS, LEVELS, MODES, NO_CARDS, NOT_ORGANS, TIMERS, QuizSession, daily_session,
                    format_time, game_length)
from ..structures import STRUCTURES
from .achievements import button_text as achievements_text, show_achievements
from .cards import fill_card, fill_question, fill_setup, mark
from .results import fill_results
from .turntable import Frames, Turntable, frame_size
from .toast import toast
from .widgets import alive


NEXT_MS = 700                   # пауза после верного ответа перед следующим вопросом
ROUTE_MS = 1300                 # «Расставь по порядку»: сколько видна пройденная цепочка
QSETS = ("all", "missed", "due", "starred")   # наборы вопросов: все, ошибки прошлой игры, пора повторить, закладки


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
        self.custom = None                     # (qset, органы) игры по своему списку - для «Сыграть ещё»
        self.shown = None                      # номер вопроса на экране: другой - значит, вопрос новый
        self.choices = {}                      # {ключ варианта: кнопка} в вопросах с вариантами
        self.progress = None                   # шапка вопроса: «Вопрос N из M · Ошибок: K» и полоски
        self.feedback = None                   # (ключ текста, орган, цвет[, вопрос]) - отзыв о прошлом ответе
        self.wrong = set()                     # неверно выбранные варианты текущего вопроса
        self.new_achievements, self.streak = [], 0        # для итогов игры: новые достижения и серия дней
        self.frames = None                     # (номер вопроса, Frames) - кадры «Угадай по 3D»
        self.next_timer = timer(app, self.next_question, NEXT_MS)
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

    def exam(self):
        """идёт «Экзамен»: одна попытка, без подсказок и без отметок верно/ошибка до конца"""
        return self.session is not None and self.mode == "exam"

    def name_of(self, key):
        """название того, о чём вопрос: органа, кости или мышцы, а в «Расставь по порядку» - маршрута"""
        return order.title(key) if key in order.ROUTES else i18n.name(key)

    def stop(self):
        """прервать текущую игру: таймеры, подсветка, кнопки-варианты"""
        for tm in (self.next_timer, self.tick_timer, self.results_timer):
            tm.stop()
        if self.frames:
            self.frames[1].stop()
            self.frames = None
        self.app.marks.unreveal()
        self.app.marks.show_missed(())                        # отметки ошибок прошлой игры
        self.session = None
        self.shown = None
        self.choices = {}
        if self.app.atlas:
            self.app.on_leave()
            self.app.view.show_layer("target", None)

    # --- настройка викторины
    def mode_keys(self, mode=None, topic=None):
        """о чём спрашивает режим mode (по умолчанию текущий): органы схемы в системе topic, а в «Кости и мышцы» -
        кости и (или) мышцы (topic - bone, muscle или None)"""
        mode = mode or self.mode
        if mode in NOT_ORGANS:
            return structures.keys(topic)
        if mode == "order":
            return order.available(self.app.body)
        return in_system(self.app.organs(), topic if mode != "daily" else None)

    def body_topic(self):
        """тема «Кости и мышцы»: bone, muscle или None (обе); у других режимов - None"""
        return self.cfg["topic"] if self.mode in NOT_ORGANS and self.cfg["topic"] in structures.KINDS else None

    def chosen_set(self):
        """набор вопросов с карточки настройки; у «Экзамена» и «Испытания дня» строки набора нет - все органы
        (набор, выбранный в другом виде викторины, сюда не переходит)"""
        return self.cfg["set"] if self.mode not in NO_CARDS else "all"

    def question_keys(self, qset, data=None):
        """органы набора вопросов qset (all, missed, due, starred - закладки) в выбранной теме"""
        keys = self.mode_keys(topic=self.cfg["topic"])
        if qset == "missed":
            return progress.last_missed(self.mode, keys, data)
        if qset == "due":
            return progress.due(self.mode, keys, data)
        if qset == "starred":
            starred = set(notes.starred())
            return [k for k in keys if k in starred]
        return keys

    def topics(self):
        """темы викторины: [(система или None - все органы, сколько органов)]; системы из одного органа
        не предлагаются - по ним нечего спрашивать. В «Кости и мышцы» - кости, мышцы или всё вместе"""
        if self.mode in NOT_ORGANS:
            return [(None, len(structures.keys()))] + [(k, len(v)) for k, v in structures.KINDS.items()]
        if self.mode in ("order", "daily"):
            return [(None, len(self.mode_keys()))]
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
        counts = {q: len(self.question_keys(q, data)) for q in QSETS}
        if not counts.get(self.cfg["set"]):
            self.cfg["set"] = "all"
        n = counts[self.chosen_set()]
        length = self.cfg["length"] if 0 < self.cfg["length"] < n else 0     # длиннее набора - значит «все»
        mode = self.mode
        rows = [(t("setup_mode"), [(t("mode_" + m), m, True) for m in MODES], mode, self.app.set_mode, None, 2)]
        if mode != "daily":                             # у «Испытания дня» всё задано заранее
            level_hint = t(("order_level_hint_" if mode == "order" else "level_hint_") + self.cfg["level"])
            rows.append((t("setup_level"), [(t("level_" + v), v, True) for v in LEVELS], self.cfg["level"],
                         lambda v: self.set_cfg("level", v), level_hint, False))
            if mode != "exam":                          # у экзамена время общее
                rows.append((t("setup_timer"), [(t("timer_sec", sec=v) if v else t("timer_off"), v, True)
                                                for v in TIMERS],
                             self.cfg["timer"], lambda v: self.set_cfg("timer", v), None, False))
            rows.append((t("setup_length"), [(t("length_all", n=n) if not v else str(v), v, not v or v < n)
                                             for v in LENGTHS],
                         length, lambda v: self.set_cfg("length", v), None, False))
            if len(topics) > 1:
                rows.append((t("setup_topic"), [(self.topic_text(name, k), name, True) for name, k in topics],
                             self.cfg["topic"], lambda v: self.set_cfg("topic", v), None, 2))
            if mode not in NO_CARDS:
                rows.append((t("setup_set"), [(t("set_" + q, n=counts[q]), q, counts[q] > 0) for q in QSETS],
                             self.cfg["set"], lambda v: self.set_cfg("set", v), t("setup_set_hint"), True))
        history = [t("history_line", date=short_date(r.get("date")), level=t("level_" + r.get("level", "medium")),
                     right=r.get("first_try", 0), total=r.get("total", 0), time=format_time(r.get("seconds", 0)))
                   for r in progress.recent(self.mode, 3, data)
                   if r.get("level") in LEVELS] or [t("history_empty")]
        fill_setup(self.app.card, t("mode_" + mode), self.setup_desc(data, n, length), rows, t("setup_start"),
                   self.start, t("setup_history"), history)

    def setup_desc(self, data, n, length):
        """описание режима на карточке настройки; у экзамена - сколько на него времени, у испытания дня -
        сыграно ли оно сегодня и сколько дней подряд"""
        mode = self.mode
        desc = t("setup_desc_" + mode)
        if mode == "exam":
            count = game_length(length, n)
            return desc + "\n" + t("exam_time", time=format_time(count * EXAM_SECONDS), n=count)
        if mode == "daily":
            today = progress.today_results("daily", data)
            status = (t("daily_today", right=today[0].get("first_try", 0), total=today[0].get("total", 0)) if today
                      else t("daily_today_none"))
            streak = achievements.mode_streak(data, "daily")
            return desc + "\n\n" + status + ("\n" + t("daily_streak", n=streak) if streak > 1 else "")
        return desc

    def topic_text(self, name, n):
        if self.mode in NOT_ORGANS:
            return t("topic_body_all", n=n) if name is None else t("topic_body_" + name, n=n)
        return t("topic_all", n=n) if name is None else t("topic_system", system=t("system_" + name), n=n)

    def set_cfg(self, key, value):
        self.cfg[key] = value
        if key in ("level", "timer", "length"):
            settings.save(**{"quiz_" + key: value})
        if key == "topic" and self.mode in NOT_ORGANS:
            self.app.apply_view()                       # кости, мышцы или всё: на схеме - нужные слои
        self.app.set_card(self.render_setup)

    def review(self, mode):
        """кнопка «Повторить»: викторина mode по органам, которые пора повторить. Тема - до смены режима:
        по ней «Кости и мышцы» показывает слои (кости, мышцы или оба)"""
        self.cfg["topic"] = None
        self.cfg["set"] = "due"
        self.app.set_mode(mode)
        self.start("due")

    def train(self, keys, mode="mix"):
        """«Потренировать слабые места» (статистика): игра mode по органам keys"""
        self.app.set_mode(mode)
        self.start("weak", keys=keys)

    def start(self, qset=None, keys=None):
        """начать игру по текущим настройкам; qset - другой набор вопросов (кнопка «Повторить ошибки»),
        keys - свой список органов (тогда qset - только подпись набора в истории)"""
        custom = (qset, list(keys)) if keys else None
        qset = qset or self.chosen_set()
        keys = keys or self.question_keys(qset)
        if not keys:
            qset, keys = "all", self.question_keys("all")
        self.stop()
        self.qset, self.custom = qset, custom
        count = game_length(self.cfg["length"], len(keys))
        mode, level = self.mode, self.cfg["level"]
        if mode == "daily":
            self.qset = "all"
            self.session = daily_session(self.app.body)
        elif mode == "order":
            self.session = order.OrderSession(keys, body=self.app.body, level=level, timer=self.cfg["timer"],
                                              count=count)
        elif mode == "exam":
            self.session = QuizSession(keys, pool=self.app.organs(), mode=mode, level=level, count=count,
                                       single_try=True, total_time=count * EXAM_SECONDS)
        else:
            pool = structures.keys() if mode in NOT_ORGANS else self.app.organs()
            self.session = QuizSession(keys, pool=pool, mode=mode, level=level, timer=self.cfg["timer"], count=count)
        self.ask()

    # --- вопросы
    def progress_text(self):
        s = self.session
        if self.exam():                                 # ошибки экзамена видны только в итогах
            text = t("progress_exam", n=s.i + 1, total=s.total)
        elif s.mode == "order":
            text = t("progress_route", n=s.i + 1, total=s.total, errors=s.errors)
        else:
            text = t("progress", n=s.i + 1, total=s.total, errors=s.errors)
        rem = s.remaining()
        if rem is None:
            return text
        if s.total_time:
            return text + "  ·  " + t("progress_left", time=format_time(math.ceil(rem)))
        return text + "  ·  " + t("progress_timer", sec=math.ceil(rem))

    def progress_state(self):
        """(строка, доля пройденных вопросов, доля оставшегося времени или None) для шапки вопроса"""
        s = self.session
        rem = s.remaining()
        return self.progress_text(), s.i / max(1, s.total), None if rem is None else rem / s.time_limit

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
        new = s.i != self.shown
        self.shown = s.i
        if new:                                         # новый вопрос на экране - запускаем его время
            s.start_timer()
            self.tick_timer.stop()
            self.tick()
        self.feedback, self.wrong = feedback, set()
        self.app.set_status(lambda: t("quiz_status", mode=t("mode_" + self.mode)))
        self.app.set_card(self.render_question, fade=new)

    def render_question(self):
        s = self.session
        if s.finished:                                  # пауза после последнего ответа: следом - итоги
            return
        card = self.app.card
        fb = self.feedback and (self.feedback_text(*self.feedback), self.feedback[2])
        give_up = (t("exam_finish") if self.exam() else t("give_up"), self.give_up)
        if s.kind == "order":
            self.render_order(card, fb, give_up)
            return
        if s.kind in ("find", "body"):
            hint = t("find_hint") if s.kind == "find" else t("body_hint_" + structures.kind(s.current))
            self.progress, self.choices = fill_question(
                card, self.progress_state(), t("find_title", name=i18n.name(s.current)),
                hint, fb, give_up=give_up)
            self.app.marks.show_target()                      # во «Вперемешку» прячет подсветку прошлого вопроса
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
        elif s.kind == "latin" and s.latin_part():
            title, hint = t("latin_part_title", latin=s.prompt()), t("latin_part_hint", n=len(opts))
        elif s.kind == "latin":
            title, hint = s.prompt(), t("latin_question_hint", n=len(opts))
        elif s.kind == "truth":
            title, hint = "«%s»" % s.prompt(), t("truth_hint", name=i18n.name(s.current))
        elif s.kind == "model":
            title, hint = t("model_title"), t("model_hint", n=len(opts))
        else:
            title, hint = t("name_title"), t("name_hint", n=len(opts))
        self.progress, self.choices = fill_question(
            card, self.progress_state(), title, hint, fb, [(k, s.option_label(k)) for k in opts], self.pick,
            give_up=give_up, extra=self.turntable() if s.kind == "model" else None)
        for k in self.wrong & set(self.choices):
            mark(self.choices[k], "wrong_bg")
        self.app.marks.show_target()

    def turntable(self):
        """вращающаяся 3D-модель органа текущего вопроса «Угадай по 3D» (кадры считаются в фоне один раз)"""
        s = self.session
        w, h = frame_size(self.app.card.width() or 340)
        if self.frames is None or self.frames[0] != s.i:
            if self.frames:
                self.frames[1].stop()
            dpr = self.app.devicePixelRatioF()
            self.frames = (s.i, Frames(ORGANS[s.current]["parts"](), round(w * dpr), round(h * dpr)))
        return Turntable(self.frames[1], w, h, t("model_loading"))

    def render_order(self, card, fb, give_up):
        """вопрос «Расставь по порядку»: маршрут, уже названные органы цепочкой, кнопки органов"""
        s = self.session
        opts = s.options()
        chain = " → ".join([i18n.name(k) for k in s.placed] + ["?"])
        hint = t("order_hint", n=len(s.route())) + "\n" + chain
        labels = [(k, ("%d. " % (s.placed.index(k) + 1) if k in s.placed else "") + i18n.name(k)) for k in opts]
        self.progress, self.choices = fill_question(card, self.progress_state(),
                                                    t("order_title", route=order.title(s.current)),
                                                    hint, fb, labels, self.pick, give_up=give_up)
        for k in s.placed:
            mark(self.choices[k], "right_bg")
            self.choices[k].setEnabled(False)
        for k in s.wrong & set(self.choices):           # орган, названный щелчком по схеме, - не кнопка
            mark(self.choices[k], "wrong_bg")

    def feedback_text(self, key, organ, _color, i=None):
        """текст отзыва на текущем языке; i - номер вопроса, ответ на который не орган: назвать верный ответ"""
        if i is not None:
            return t(key, answer=self.session.answer_text(i))
        return t(key, name=self.name_of(organ) if organ is not None else "")

    def tick(self):
        """раз в четверть секунды: обновить остаток времени, а когда он вышел - показать ответ и идти дальше"""
        s = self.session
        if s is None or s.finished or s.remaining() is None:
            return
        if not self.next_timer.isActive():              # во время зелёной паузы после ответа не считаем
            i = s.i if s.answer_text(s.i) is not None else None      # ответ - не орган: назовём его
            route = s.current if s.kind == "order" else None
            key = s.time_up()
            if key:
                self.skipped(route or key, i, "time_up", s.level == "easy" and not route)
                return
            self.update_progress()
        self.tick_timer.start()

    def give_up(self):
        """кнопка «Сдаться»: показать верный ответ (ошибка засчитывается) и закончить игру - сразу итоги"""
        s = self.session
        if s is None or s.finished or self.next_timer.isActive():
            return
        if self.exam():                                 # «Завершить»: оставшиеся вопросы - без ответа
            self.finish(s.finish_all())
            return
        i = s.i if s.answer_text(s.i) is not None else None
        route = s.current if s.kind == "order" else None
        key = s.give_up()
        self.skipped(route or key, i, "gave_up", not route)

    def skipped(self, key, i, text, reveal):
        """вопрос пропущен (время вышло или «Сдаться»): показать, где был нужный орган, и задать следующий;
        i - номер вопроса, если ответ на него - не орган (тогда отзыв называет ответ словами);
        text - ключ отзыва (с «_answer» - для такого вопроса); reveal - ещё и подписать орган на схеме"""
        s = self.session
        self.app.marks.unreveal()
        if key in ORGANS or key in STRUCTURES:          # маршрут на схеме не подсвечивается
            if not self.exam():                         # в экзамене - без подсказок
                self.app.marks.flash(key, "ok")
            if reveal and not self.exam():
                self.app.marks.reveal(key)
        if s.finished:
            self.finish(key)
            return
        self.ask((text, key, "bad") if i is None else (text + "_answer", key, "bad", i))

    def hint_wrong(self):
        """после ошибки на лёгком уровне - подсказка, если ответ на вопрос - орган"""
        s = self.session
        if s is not None and not s.finished and s.level == "easy" and not self.exam() and (
                s.correct() in ORGANS or s.correct() in STRUCTURES):
            self.app.marks.reveal(s.correct())

    def answer(self, key):
        """клик по органу в режиме «Найди орган»"""
        s = self.session
        if s is None or s.finished or self.next_timer.isActive():
            return
        if s.kind == "order":                           # щелчок по органу - следующий шаг маршрута
            self.order_step(key)
            return
        if self.exam():
            s.answer(key)
            self.accepted(key)
            return
        right = s.answer(key)
        self.app.marks.flash(key, "ok" if right else "bad")
        if not right:
            self.ask(("answer_wrong", key, "bad"))
            self.hint_wrong()
            return
        self.app.marks.unreveal()
        if s.finished:
            self.finish(key)
            return
        self.ask(("answer_right", key, "ok"))

    def pick(self, key):
        """выбран вариант ответа (кнопкой или цифрой)"""
        s = self.session
        if s is None or s.finished or self.next_timer.isActive() or key not in self.choices:
            return
        if s.kind == "order":
            self.order_step(key)
            return
        if self.exam():
            s.answer(key)
            mark(self.choices[key], "accent")           # выбран - без отметки, верно или нет
            self.accepted(key)
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
        self.app.marks.unreveal()
        mark(btn, "right_bg")
        self.app.marks.flash(asked, "ok")
        self.wrong = set()                              # ошибки - того вопроса, а игра уже на следующем
        self.next_timer.start(NEXT_MS)

    def accepted(self, key):
        """«Экзамен»: ответ принят - без отметки верно/ошибка, через мгновение следующий вопрос"""
        self.choices = {}                               # больше не нажать
        if self.session.finished:
            self.finish(self.session.q[-1])
            return
        self.feedback = ("exam_accepted", None, "muted")
        self.next_timer.start(NEXT_MS // 2)

    def order_step(self, key):
        """«Расставь по порядку»: назван орган (кнопкой, цифрой или на схеме)"""
        s = self.session
        if key in s.placed:
            return
        route = s.current
        result = s.step(key)
        if key in ORGANS:
            self.app.marks.flash(key, "bad" if result == "wrong" else "ok")
        if result == "wrong":
            self.feedback = ("order_wrong", route, "bad")
            self.app.set_card(self.render_question)
            self.hint_wrong()
            return
        if result == "right":
            self.feedback = None
            self.app.set_card(self.render_question)
            return
        self.app.marks.unreveal()                             # маршрут пройден: показать его целиком, потом дальше
        self.feedback = ("order_done", route, "ok")
        self.app.set_card(lambda: self.render_done(route), fade=True)
        self.next_timer.start(ROUTE_MS)

    def render_done(self, route):
        """маршрут пройден: цепочка органов целиком"""
        chain = " → ".join(i18n.name(k) for k in order.steps(route, self.app.body))
        self.progress, self.choices = fill_question(self.app.card, self.progress_state(),
                                                    t("order_title", route=order.title(route)), chain,
                                                    (t("order_done", name=order.title(route)), "ok"))

    def next_question(self):
        self.next_timer.stop()
        s = self.session
        if s is None:
            return
        if s.finished:
            self.finish(s.q[-1])
            return
        self.ask(self.feedback if self.exam() else None)        # «Экзамен»: «Ответ принят» - над новым вопросом

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
        for key in self.new_achievements:               # новое достижение - плашкой внизу окна
            toast(app, t("ach_toast"), t("ach_" + key), lambda: show_achievements(app), t("ach_toast_hint"))
        self.ask()
        if last in ORGANS or last in STRUCTURES:        # сначала карточка последнего органа, следом итоги
            app.set_card(lambda: fill_card(app.card, last), fade=True)
            self.results_timer.start()
        else:                                           # маршрут или ответ экзамена - сразу итоги
            self.show_results()

    def on_key(self, keysym, char):
        """Enter на карточке настройки начинает игру, цифры выбирают вариант ответа"""
        if self.session is None:
            if keysym in ("Return", "KP_Enter"):
                self.start()
            return
        if self.kind() not in ("find", "body") and char.isdecimal():        # цифры - кнопки вариантов (не «²»)
            keys = list(self.choices)
            i = int(char) - 1
            if 0 <= i < len(keys):
                self.pick(keys[i])

    def show_results(self):
        s, mode, app = self.session, self.mode, self.app
        if s is None or app.mode != s.mode:             # пока ждали, пользователь ушёл в другой режим
            return

        def again(qset=None):
            if app.mode != mode:
                return
            if qset is None and self.custom:            # «Потренировать слабые места» - снова те же органы
                self.start(*self.custom)
            else:
                self.start(qset)

        due = len(progress.due(mode, self.mode_keys(mode))) if mode not in NO_CARDS else 0
        new, streak = self.new_achievements, self.streak
        grade = s.grade if mode == "exam" else None
        review = self.review_lines() if mode == "exam" else ()
        retry = (lambda: again("missed")) if mode not in NO_CARDS else None
        app.marks.show_missed(s.missed)                       # ошибки - красным на схеме, с подписями
        # итоги - в карточке справа, на месте карточки последнего органа
        app.set_card(lambda: fill_results(app.card, s, on_again=again, on_retry=retry,
                                          on_setup=lambda: app.set_mode(mode), due=due, streak=streak, new=new,
                                          on_achievements=lambda: show_achievements(app), name_of=self.name_of,
                                          grade=grade, review=review, on_scheme=bool(app.marks.missed)), fade=True)

    def review_lines(self):
        """разбор ошибок экзамена: [(вопрос, верный ответ, что ответили)]"""
        s = self.session
        out = []
        for i, key, given in s.mistakes():
            kind = s.kinds[i]
            if kind in ("find", "body"):
                question = t("find_title", name=i18n.name(key))
            elif kind == "name":
                question = t("review_name")
            elif kind == "system":
                question = t("system_title", name=i18n.name(key))
            elif kind == "latin" and s.picks.get(i):
                question = t("latin_part_title", latin=s.prompt_at(i))
            else:
                question = s.prompt_at(i) or t("review_name")
            right = s.answer_text(i) or i18n.name(key)
            out.append((question, right, s.given_text(i, given)))
        return out


def short_date(iso):
    """'2026-10-25T14:03' -> '25.10 14:03'"""
    try:
        d, hm = (iso or "").split("T")
        return "%s.%s %s" % (d[8:10], d[5:7], hm[:5])
    except ValueError:
        return iso or ""
