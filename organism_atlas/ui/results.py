"""Окно с результатами викторины."""

import tkinter as tk

from .. import i18n
from ..config import FONT
from ..i18n import t
from ..quiz import format_time
from ..theme import style
from . import titlebar
from .scaling import px
from .widgets import flat_button, frame, label, rounded_card


def show_results_dialog(root, session, on_again, on_retry=None, due=0):
    """session - завершённая QuizSession; on_again - по кнопке «Сыграть ещё»,
    on_retry - по кнопке «Повторить ошибки» (видна, если ошибки были); due - карточек на повторение сегодня"""
    total, pct = session.total, session.percent
    win = style(tk.Toplevel(root), bg="bg")
    titlebar.paint(win)
    win.title(t("results_title"))
    win.resizable(False, False)
    win.transient(root)
    box, card = rounded_card(win)
    box.pack(padx=20, pady=20)
    label(card, t("results_heading"), font=(FONT, 15, "bold")).pack(padx=40, pady=(20, 4))
    label(card, t("results_score", right=session.first_try, total=total), fg="accent_fg",
          font=(FONT, 36, "bold")).pack()
    label(card, t("results_first_try", percent=pct), fg="muted", font=(FONT, 11)).pack()
    label(card, session.verdict, font=(FONT, 12, "bold")).pack(pady=(12, 4))
    label(card, t("results_errors", errors=session.errors), font=(FONT, 11)).pack()
    label(card, t("results_time", time=format_time(session.elapsed), level=t("level_" + session.level)),
          fg="muted", font=(FONT, 11)).pack()
    if session.timeouts:
        label(card, t("results_timeouts", n=session.timeouts), fg="muted", font=(FONT, 11)).pack()
    if session.missed:
        label(card, t("results_missed", names=", ".join(i18n.name(k) for k in session.missed)), fg="muted",
              font=(FONT, 11), wraplength=px(300), justify="center").pack(padx=20, pady=(6, 0))
    if due:
        label(card, t("results_due", n=due), fg="muted", font=(FONT, 10), wraplength=px(300),
              justify="center").pack(padx=20, pady=(8, 0))
    row = frame(card)
    row.pack(pady=(18, 20))

    def run(fn):
        win.destroy()
        fn()

    flat_button(row, t("results_again"), lambda: run(on_again), bg="accent").pack(side="left", padx=4)
    if session.missed and on_retry:
        flat_button(row, t("results_retry"), lambda: run(on_retry)).pack(side="left", padx=4)
    flat_button(row, t("results_close"), win.destroy).pack(side="left", padx=4)
    win.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - win.winfo_width()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - win.winfo_height()) // 2
    win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
    win.grab_set()
