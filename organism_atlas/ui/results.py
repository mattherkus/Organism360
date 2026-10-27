"""Итоги викторины (встроенная панель)."""

from PySide6.QtCore import Qt

from .. import i18n
from ..i18n import t
from ..quiz import format_time
from .overlay import Panel
from .scaling import px
from .widgets import flat_button, hbox, label, put, rounded_card, spacer


def show_results_dialog(host, session, on_again, on_retry=None, due=0, streak=0, new=(), on_achievements=None):
    """session - завершённая QuizSession; on_again - по кнопке «Сыграть ещё»,
    on_retry - по кнопке «Повторить ошибки» (видна, если ошибки были); due - карточек на повторение сегодня;
    streak - дней подряд с игрой; new - ключи достижений, полученных этой игрой,
    on_achievements - по кнопке «Все достижения» (видна, если что-то получено)"""
    total, pct = session.total, session.percent
    win = Panel(host, t("results_title"))
    card = rounded_card(width=px(420))
    put(win.body, card, top=10, bottom=16)
    lay = card.lay
    center = Qt.AlignHCenter

    def line(text, fg="text", size=11, bold=False, top=0, bottom=0):
        return put(lay, label(text, fg, size, bold, align=center), top=top, bottom=bottom, x=20)

    line(t("results_heading"), size=15, bold=True, top=20, bottom=4)
    line(t("results_score", right=session.first_try, total=total), "accent_fg", 36, True)
    line(t("results_first_try", percent=pct), "muted")
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
    row = hbox(spacing=8)
    row.addStretch(1)

    def run(fn):
        win.close_panel()
        fn()

    row.addWidget(flat_button(t("results_again"), lambda: run(on_again), bg="accent"))
    if session.missed and on_retry:
        row.addWidget(flat_button(t("results_retry"), lambda: run(on_retry)))
    if new and on_achievements:
        row.addWidget(flat_button(t("results_achievements"), lambda: run(on_achievements)))
    row.addWidget(flat_button(t("results_close"), win.close_panel))
    row.addStretch(1)
    put(lay, row, top=18, x=20)
    spacer(lay, 20)
    return win
