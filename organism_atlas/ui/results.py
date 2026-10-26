"""Итоги викторины (встроенная панель)."""

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..quiz import format_time
from .overlay import Panel
from .scaling import px
from .widgets import flat_button, frame, label, rounded_card


def show_results_dialog(root, session, on_again, on_retry=None, due=0):
    """session - завершённая QuizSession; on_again - по кнопке «Сыграть ещё»,
    on_retry - по кнопке «Повторить ошибки» (видна, если ошибки были); due - карточек на повторение сегодня"""
    total, pct = session.total, session.percent
    win = Panel(root, t("results_title"))
    box, card = rounded_card(win.body)
    box.pack(padx=px(16), pady=(px(10), px(16)))
    label(card, t("results_heading"), font=(FONT, 15, "bold")).pack(padx=px(40), pady=(px(20), px(4)))
    label(card, t("results_score", right=session.first_try, total=total), fg="accent_fg",
          font=(FONT, 36, "bold")).pack()
    label(card, t("results_first_try", percent=pct), fg="muted", font=(FONT, 11)).pack()
    label(card, session.verdict, font=(FONT, 12, "bold")).pack(pady=(px(12), px(4)))
    label(card, t("results_errors", errors=session.errors), font=(FONT, 11)).pack()
    label(card, t("results_time", time=format_time(session.elapsed), level=t("level_" + session.level)),
          fg="muted", font=(FONT, 11)).pack()
    if session.timeouts:
        label(card, t("results_timeouts", n=session.timeouts), fg="muted", font=(FONT, 11)).pack()
    if session.missed:
        label(card, t("results_missed", names=", ".join(i18n.name(k) for k in session.missed)), fg="muted",
              font=(FONT, 11), wraplength=px(300), justify="center").pack(padx=px(20), pady=(px(6), 0))
    if due:
        label(card, t("results_due", n=due), fg="muted", font=(FONT, 10), wraplength=px(300),
              justify="center").pack(padx=px(20), pady=(px(8), 0))
    row = frame(card)
    row.pack(padx=px(20), pady=(px(18), px(20)))

    def run(fn):
        win.destroy()
        fn()

    flat_button(row, t("results_again"), lambda: run(on_again), bg="accent").pack(side="left", padx=px(4))
    if session.missed and on_retry:
        flat_button(row, t("results_retry"), lambda: run(on_retry)).pack(side="left", padx=px(4))
    flat_button(row, t("results_close"), win.destroy).pack(side="left", padx=px(4))
    return win
