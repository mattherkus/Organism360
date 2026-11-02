"""Итоги викторины: карточка справа от схемы (на месте карточки органа). Наверху - крупная оценка (в «Экзамене»)
и кольцо: доля ответов с первой попытки; органы-ошибки окно в это время отмечает на схеме (Marks.show_missed в marks.py)."""

from PySide6.QtCore import Qt

from .. import i18n
from ..config import STATUS
from ..i18n import t
from ..quiz import format_time
from .widgets import Ring, bar, clear, flat_button, font, label, put, spacer


def ring_color(percent):
    """цвет кольца по доле верных с первой попытки - цвета уровней знания (выучено, учу, слабо)"""
    return STATUS["learned" if percent >= 80 else "learning" if percent >= 50 else "weak"]


def fill_results(card, session, on_again, on_retry=None, on_setup=None, due=0, streak=0, new=(),
                 on_achievements=None, name_of=i18n.name, grade=None, review=(), on_scheme=False):
    """session - завершённая QuizSession (или order.OrderSession); on_again - по кнопке «Сыграть ещё»,
    name_of(ключ) - название того, о чём спрашивали (орган, кость, маршрут); grade - оценка «Экзамена»
    (2-5), review - [(вопрос, верный ответ, ответ игрока)] для «Разбора ошибок»;
    on_retry - по кнопке «Повторить ошибки» (видна, если ошибки были), on_setup - вернуться к настройке игры;
    due - карточек на повторение сегодня; streak - дней подряд с игрой; new - ключи достижений,
    полученных этой игрой, on_achievements - по кнопке «Достижения» (видна, если что-то получено);
    on_scheme - ошибки отмечены на схеме (под списком ошибок - об этом строка)"""
    lay = card.lay
    clear(lay)
    bar(lay, "accent")
    center = Qt.AlignHCenter

    def line(text, fg="text", size=11, bold=False, top=0, bottom=0):
        return put(lay, label(text, fg, size, bold, align=center), top=top, bottom=bottom, x=20)

    line(t("results_heading"), size=17, bold=True, top=16, bottom=4).setFont(font(17, bold=True, serif=True))
    if grade is not None:
        line(t("results_grade", grade=grade, word=t("grade_%d" % grade)), "day_title", 26, True,
             bottom=4).setFont(font(26, bold=True, serif=True))
    ring = Ring(session.percent / 100, ring_color(session.percent), "%d%%" % session.percent, t("results_ring"), size=150)
    put(lay, ring, top=6, bottom=6, align="center")
    line(t("results_score", right=session.first_try, total=session.total), "accent_fg", 18,
         True).setFont(font(18, bold=True, serif=True))
    line(session.verdict, size=12, bold=True, top=10, bottom=4)
    line(t("results_errors", errors=session.errors))
    line(t("results_time", time=format_time(session.elapsed), level=t("level_" + session.level)), "muted")
    if session.gave_up:
        line(t("results_gave_up", n=session.total, total=session.planned), "muted")
    if session.timeouts:
        line(t("results_timeouts", n=session.timeouts), "muted")
    if session.missed:
        line(t("results_missed", names=", ".join(name_of(k) for k in session.missed)), "muted", top=6)
        if on_scheme:
            line(t("results_on_scheme"), "bad", 10, top=2)
    if due:
        line(t("results_due", n=due), "muted", 10, top=8)
    if streak > 1:
        line(t("results_streak", n=streak), "day_title", bold=True, top=8)
    for key in new:
        line("★  " + t("results_new_ach", name=t("ach_" + key)), "day_title", bold=True, top=6)
    if review:
        put(lay, label(t("review_title").upper(), "muted", 9, bold=True), top=14, x=20)
        for question, right, given in review:
            put(lay, label(question, size=10, bold=True), top=6, x=20)
            put(lay, label(t("review_line", answer=right, given=given or t("review_no_answer")), "muted", 9), x=20)
    # кнопки столбиком: в узкой карточке в строку они не помещаются
    buttons = [(t("results_again"), on_again, "accent")]
    if session.missed and on_retry:
        buttons.append((t("results_retry"), on_retry, "card"))
    if new and on_achievements:
        buttons.append((t("results_achievements"), on_achievements, "card"))
    if on_setup:
        buttons.append((t("results_setup"), on_setup, "card"))
    for i, (text, command, bg) in enumerate(buttons):
        put(lay, flat_button(text, command, bg=bg), top=16 if i == 0 else 6, x=20)
    spacer(lay, 16)
