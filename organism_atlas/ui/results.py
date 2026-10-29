"""Итоги викторины: карточка справа от схемы (на месте карточки органа)."""

from PySide6.QtCore import Qt

from .. import i18n
from ..i18n import t
from ..quiz import format_time
from .widgets import bar, clear, flat_button, label, put, spacer


def fill_results(card, session, on_again, on_retry=None, on_setup=None, due=0, streak=0, new=(),
                 on_achievements=None):
    """session - завершённая QuizSession; on_again - по кнопке «Сыграть ещё»,
    on_retry - по кнопке «Повторить ошибки» (видна, если ошибки были), on_setup - вернуться к настройке игры;
    due - карточек на повторение сегодня; streak - дней подряд с игрой; new - ключи достижений,
    полученных этой игрой, on_achievements - по кнопке «Достижения» (видна, если что-то получено)"""
    lay = card.lay
    clear(lay)
    bar(lay, "accent")
    center = Qt.AlignHCenter

    def line(text, fg="text", size=11, bold=False, top=0, bottom=0):
        return put(lay, label(text, fg, size, bold, align=center), top=top, bottom=bottom, x=20)

    line(t("results_heading"), size=15, bold=True, top=16, bottom=4)
    line(t("results_score", right=session.first_try, total=session.total), "accent_fg", 32, True)
    line(t("results_first_try", percent=session.percent), "muted")
    line(session.verdict, size=12, bold=True, top=12, bottom=4)
    line(t("results_errors", errors=session.errors))
    line(t("results_time", time=format_time(session.elapsed), level=t("level_" + session.level)), "muted")
    if session.timeouts:
        line(t("results_timeouts", n=session.timeouts), "muted")
    if session.missed:
        line(t("results_missed", names=", ".join(i18n.name(k) for k in session.missed)), "muted", top=6)
    if due:
        line(t("results_due", n=due), "muted", 10, top=8)
    if streak > 1:
        line(t("results_streak", n=streak), "day_title", bold=True, top=8)
    for key in new:
        line("★  " + t("results_new_ach", name=t("ach_" + key)), "day_title", bold=True, top=6)
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
