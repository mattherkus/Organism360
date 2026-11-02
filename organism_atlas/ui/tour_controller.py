"""Экскурсии в режиме «Изучать»: шаги маршрута в карточке справа и подсветка органа шага на схеме.

TourController хранит, какая экскурсия идёт и на каком она шаге, и прерванную экскурсию, к которой
можно вернуться; окно (App) даёт ему карточку, подсветку органа (set_spot) и схему тела."""

from .. import i18n, tours
from ..i18n import t
from ..organs import ORGANS
from ..structures import STRUCTURES
from .cards import fill_tour
from .viewer3d import show_3d


class TourController:
    def __init__(self, app):
        self.app = app
        self.tour = None                       # (экскурсия, шаг): 0 - вступление, 1..n - органы, n + 1 - конец
        self.paused = None                     # экскурсия, прерванная щелчком по органу: к ней можно вернуться

    def reset(self):
        """смена режима или схемы тела: маршрут мог измениться - экскурсии больше нет"""
        self.tour = self.paused = None

    def keys(self, name):
        return tours.steps(name, self.app.body)

    def spot_of(self, name, i):
        keys = self.keys(name)
        return keys[i - 1] if 1 <= i <= len(keys) else None

    def start(self, name):
        self.tour, self.paused = (name, 0), None
        self.app.set_spot(None)
        self.app.set_card(self.card, fade=True)

    def go(self, step):
        """на step шагов вперёд или назад; после последнего органа - карточка «экскурсия пройдена»"""
        name, i = self.tour
        i = max(0, min(len(self.keys(name)) + 1, i + step))
        if i == self.tour[1]:
            return
        self.tour = (name, i)
        self.app.set_spot(self.spot_of(name, i))
        self.app.set_card(self.card, fade=True)

    def end(self):
        """закончить экскурсию и показать список экскурсий"""
        self.tour = self.paused = None
        self.app.set_spot(None)
        self.app.set_card(self.app.empty_card, fade=True)

    def pause(self):
        """прервать экскурсию (щелчок по органу, поиск): запомнить шаг, чтобы к нему вернуться"""
        if self.tour is not None:
            self.paused, self.tour = self.tour, None

    def resume(self):
        """вернуться к прерванной экскурсии на тот же шаг"""
        if self.paused is None:
            return
        name, i = self.tour = self.paused
        self.paused = None
        self.app.set_spot(self.spot_of(name, i))
        self.app.set_card(self.card, fade=True)

    def back_button(self):
        """кнопка под карточкой органа: вернуться к прерванной экскурсии или к списку экскурсий"""
        if self.paused is not None:
            return t("tour_resume", title=tours.title(self.paused[0])), self.resume
        return t("tours_back"), self.end

    def quiz(self, topic):
        """викторина «Вперемешку» по системе органов экскурсии: карточка настройки с выбранной темой"""
        self.app.set_mode("mix")
        self.app.quiz.set_cfg("topic", topic)

    def on_key(self, keysym):
        """стрелки и Enter листают экскурсию; True - клавиша обработана"""
        if self.tour is not None and keysym in ("Right", "Left", "Return", "KP_Enter"):
            self.go(-1 if keysym == "Left" else 1)
            return True
        return False

    def card(self):
        app = self.app
        if self.tour is None:                           # экскурсию закончили, пока карточка перерисовывалась
            app.empty_card()
            return
        name, i = self.tour
        keys = self.keys(name)
        n = len(keys)
        back = (t("tour_back"), lambda: self.go(-1), "card", i > 0)
        if i == 0:
            route = " → ".join(i18n.name(k) for k in keys)
            fill_tour(app.card, t("tour_label"), tours.title(name), None,
                      tours.intro(name) + "\n\n" + t("tour_route", route=route), "accent",
                      [(t("tour_start"), lambda: self.go(1), "accent", True)],
                      [(t("tour_exit"), self.end)], t("tour_keys"))
        elif i > n:
            topic = tours.TOPICS.get(name)
            extra = [(t("tour_quiz"), lambda: self.quiz(topic))] if topic in dict(app.quiz.topics()) else []
            fill_tour(app.card, tours.title(name), t("tour_done"), None, t("tour_done_text", n=n), "accent",
                      [back, (t("tour_finish"), self.end, "accent", True)], extra)
        else:
            key = keys[i - 1]
            extra = [(t("card_3d"), lambda: show_3d(app, key))] if key in ORGANS else []   # у костей и мышц 3D нет
            fill_tour(app.card, t("tour_progress", title=tours.title(name), n=i, total=n), i18n.name(key),
                      i18n.subtitle(key), tours.story(name, key), (ORGANS.get(key) or STRUCTURES[key])["color"],
                      [back, (t("tour_next") if i < n else t("tour_last"), lambda: self.go(1), "accent", True)],
                      extra + [(t("tour_exit"), self.end)])
