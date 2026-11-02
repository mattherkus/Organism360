"""Панель «Статистика»: сводка, точность по видам викторины и по системам органов, последние игры и слабые места.

Графики рисуются QPainter по правилам проекта: один ряд - один цвет (акцент темы), тонкие полосы со скруглённым
концом от общей базы, линия 2 px с точкой на конце, сетка - волосяные линии; значения подписаны у концов полос,
остальное - во всплывающей подсказке при наведении. Цвета уровней знания (карта знаний) - статусные и всегда
вместе со значком и подписью."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QToolTip, QWidget

from .. import i18n, progress, stats
from ..config import STATUS
from ..i18n import t
from .layers_panel import ScrollArea
from .overlay import Panel, top
from .scaling import px
from .widgets import color, flat_button, font, heading, hbox, label, put, rounded_card, spacer, vbox

WIDTH = 700                  # ширина панели при масштабе 100 %
BAR = 10                     # толщина полосы, px
ROW = 26                     # высота строки списка полос
ICONS = {"learned": "✓", "learning": "~", "weak": "!"}          # значок уровня знания рядом с цветом


def show_stats(host):
    p = top(host)
    if isinstance(p, StatsPanel):
        return p
    return StatsPanel(host)


class BarList(QWidget):
    """горизонтальные полосы «название - доля в %»: items - [(название, доля 0..100, подсказка)]"""

    def __init__(self, items, label_w):
        super().__init__()
        self.items, self.label_w = items, label_w
        self.setMouseTracking(True)
        self.setFixedHeight(px(ROW) * max(1, len(items)) + px(4))
        self.setMinimumWidth(label_w + px(120))

    def geometry_of(self, i):
        """прямоугольник полосы i и место подписи значения"""
        x0 = self.label_w + px(8)
        full = self.width() - x0 - px(48)                       # справа - место под «100 %»
        y = px(ROW) * i + (px(ROW) - px(BAR)) / 2
        return QRectF(x0, y, max(0.0, full * self.items[i][1] / 100), px(BAR)), x0, full

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(font(9))
        p.setFont(font(9))
        if not self.items:
            return
        _r, x0, full = self.geometry_of(0)
        p.setPen(QPen(color("border"), 1))                       # база - волосяная линия
        p.drawLine(QPointF(x0, 0), QPointF(x0, self.height()))
        for i, (name, value, _tip) in enumerate(self.items):
            r, _, _ = self.geometry_of(i)
            mid = px(ROW) * i + px(ROW) / 2
            p.setPen(color("text"))
            text = fm.elidedText(name, Qt.ElideRight, self.label_w)
            p.drawText(QRectF(0, mid - fm.height() / 2, self.label_w, fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                       text)
            if r.width() > 0:                                    # скругление только у конца, у базы - прямо
                rad = min(px(4), r.width(), r.height() / 2)
                path = QPainterPath()
                path.moveTo(r.left(), r.top())
                path.lineTo(r.right() - rad, r.top())
                path.quadTo(r.right(), r.top(), r.right(), r.top() + rad)
                path.lineTo(r.right(), r.bottom() - rad)
                path.quadTo(r.right(), r.bottom(), r.right() - rad, r.bottom())
                path.lineTo(r.left(), r.bottom())
                path.closeSubpath()
                p.fillPath(path, color("accent_fg"))
            p.setPen(color("muted"))
            p.drawText(QRectF(r.right() + px(6), mid - fm.height() / 2, px(48), fm.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, "%d %%" % round(value))

    def mouseMoveEvent(self, e):
        i = int(e.position().y() // px(ROW))
        if 0 <= i < len(self.items):
            QToolTip.showText(e.globalPosition().toPoint(), self.items[i][2], self)
        else:
            QToolTip.hideText()


class TrendChart(QWidget):
    """доля ответов с первой попытки в последних играх: points - [(подсказка, доля 0..100)], от старых к новым"""

    def __init__(self, points):
        super().__init__()
        self.points = points
        self.hover = None
        self.setMouseTracking(True)
        self.setFixedHeight(px(150))

    def area(self):
        left, right, topm, bottom = px(40), px(44), px(10), px(12)
        return QRectF(left, topm, self.width() - left - right, self.height() - topm - bottom)

    def xy(self, i, value):
        a = self.area()
        n = len(self.points)
        x = a.left() + (a.width() * i / (n - 1) if n > 1 else a.width() / 2)
        return QPointF(x, a.bottom() - a.height() * value / 100)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(font(8))
        fm = QFontMetrics(font(8))
        a = self.area()
        for v in (0, 50, 100):                                   # волосяная сетка и подписи оси
            y = a.bottom() - a.height() * v / 100
            p.setPen(QPen(color("border"), 1))
            p.drawLine(QPointF(a.left(), y), QPointF(a.right(), y))
            p.setPen(color("muted"))
            p.drawText(QRectF(0, y - fm.height() / 2, a.left() - px(6), fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                       "%d %%" % v)
        if not self.points:
            return
        if self.hover is not None:                               # перекрестье у точки под курсором
            pt = self.xy(self.hover, self.points[self.hover][1])
            p.setPen(QPen(color("muted"), 1))
            p.drawLine(QPointF(pt.x(), a.top()), QPointF(pt.x(), a.bottom()))
        pen = QPen(color("accent_fg"), px(2))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        path = QPainterPath(self.xy(0, self.points[0][1]))
        for i, (_tip, v) in enumerate(self.points[1:], 1):
            path.lineTo(self.xy(i, v))
        p.drawPath(path)
        for i in {len(self.points) - 1, self.hover} - {None}:     # точка на конце (и под курсором) с кольцом фона
            pt = self.xy(i, self.points[i][1])
            p.setPen(QPen(color("card"), px(2)))
            p.setBrush(color("accent_fg"))
            p.drawEllipse(pt, px(4) + px(1), px(4) + px(1))
        last = self.xy(len(self.points) - 1, self.points[-1][1])   # подпись - только у конца
        p.setPen(color("text"))
        p.setFont(font(9, bold=True))
        p.drawText(QRectF(last.x() + px(8), last.y() - px(9), px(44), px(18)), Qt.AlignLeft | Qt.AlignVCenter,
                   "%d %%" % self.points[-1][1])

    def mouseMoveEvent(self, e):
        if not self.points:
            return
        a = self.area()
        n = len(self.points)
        x = e.position().x()
        i = round((x - a.left()) / a.width() * (n - 1)) if n > 1 else 0
        i = max(0, min(n - 1, i))
        if i != self.hover:
            self.hover = i
            self.update()
        QToolTip.showText(e.globalPosition().toPoint(), self.points[i][0], self)

    def leaveEvent(self, _e):
        self.hover = None
        self.update()


def tile(title, value, hero=False, note=""):
    """плитка сводки: подпись, число (одно число на панели - крупное) и пояснение мелко"""
    card = rounded_card(radius=10)
    put(card.lay, label(title, "muted", 9), top=8, x=12)
    put(card.lay, label(value, "text", 22 if hero else 15, bold=True), bottom=0 if note else 8, x=12)
    if note:
        put(card.lay, label(note, "muted", 9), bottom=8, x=12)
    return card


def legend_row(level):
    """строка легенды карты знаний: цветной кружок со значком и подпись (цвет никогда не один)"""
    row = hbox(spacing=6)
    dot = label(ICONS[level], "on_mark", 9, bold=True, wrap=False, align=Qt.AlignCenter)
    dot.setFixedSize(px(18), px(18))
    dot.setStyleSheet("background: %s; border-radius: %dpx" % (STATUS[level], px(9)))
    row.addWidget(dot)
    row.addWidget(label(t("level_name_" + level), "text", 10), 1)
    return row


class StatsPanel(Panel):
    def __init__(self, host):
        super().__init__(host, t("stats_title"))
        data = progress.load()
        self.area = ScrollArea()
        self.area.setFixedWidth(px(WIDTH) + px(14))
        self.area.setFixedHeight(max(px(300), min(px(640), host.height() - px(120))))
        card = rounded_card(width=px(WIDTH))
        self.area.lay.addWidget(card)
        self.area.lay.addStretch(1)
        put(self.body, self.area, top=10, bottom=16)
        lay = card.lay
        s = stats.summary(data)
        if not s["games"]:
            put(lay, label(t("stats_empty"), "muted", 11), top=16, bottom=16)
            return
        tiles = QGridLayout()
        tiles.setContentsMargins(0, 0, 0, 0)
        tiles.setHorizontalSpacing(px(8))
        for i, (title, value, hero, note) in enumerate((
                (t("stats_percent"), "%d %%" % s["percent"] if s["percent"] is not None else "—", True, ""),
                (t("stats_games"), str(s["games"]), False, ""),
                (t("stats_questions"), str(s["questions"]), False, ""),
                (t("stats_streak"), str(s["streak"]), False, t("stats_streak_best", best=s["best_streak"])))):
            tiles.addWidget(tile(title, value, hero, note), 0, i)
            tiles.setColumnStretch(i, 1)
        put(lay, tiles, top=14)
        hours, minutes = divmod(s["minutes"], 60)
        put(lay, label(t("stats_time", h=hours, m=minutes), "muted", 9), top=6)

        cols = hbox(spacing=16)
        left, right = vbox(), vbox()
        modes = [(t("mode_" + m), 100 * ok / q, t("stats_mode_tip", mode=t("mode_" + m), games=g, questions=q,
                                                    percent=round(100 * ok / q)))
                 for m, g, q, ok in stats.by_mode(data)]
        left.addWidget(label(t("stats_by_mode").upper(), "muted", 9, bold=True))
        left.addSpacing(px(4))
        left.addWidget(BarList(modes, px(140)))
        left.addStretch(1)
        systems = [(t("system_" + name), 100 * ok / seen, t("stats_system_tip", system=t("system_" + name),
                                                             seen=seen, right=ok, percent=round(100 * ok / seen)))
                   for name, seen, ok in stats.by_system(data, host.organs())]
        right.addWidget(label(t("stats_by_system").upper(), "muted", 9, bold=True))
        right.addSpacing(px(4))
        right.addWidget(BarList(systems, px(160)) if systems else label(t("stats_no_organs"), "muted", 9))
        right.addStretch(1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        put(lay, cols, top=14)

        heading(lay, t("stats_trend", n=len(stats.trend(data))), top=14)
        points = [(t("stats_trend_tip", date=_date(iso), mode=t("mode_" + m) if m else "", percent=v), v)
                  for iso, m, v in stats.trend(data)]
        put(lay, TrendChart(points), top=4)

        heading(lay, t("stats_weak"), top=14)
        weak = stats.weakest(data, host.organs())
        if weak:
            for k, seen, ok in weak:
                put(lay, label(t("stats_weak_line", name=i18n.name(k), right=ok, seen=seen), "text", 10), top=2)
            put(lay, flat_button(t("stats_train"), lambda: self.train([k for k, *_ in weak]), bg="accent", pady=4),
                top=8, align="left")
        else:
            put(lay, label(t("stats_weak_none"), "muted", 10), top=2)

        heading(lay, t("knowledge_title"), top=14)
        put(lay, label(t("knowledge_hint"), "muted", 9), top=2)
        levels = stats.mastery(data)
        for level in stats.LEVELS[::-1]:
            n = sum(v == level for k, v in levels.items() if k in host.organs())
            row = legend_row(level)
            row.addWidget(label(str(n), "muted", 10, wrap=False))
            put(lay, row, top=4)
        on = getattr(host, "knowledge", False)
        put(lay, flat_button(t("knowledge_hide") if on else t("knowledge_show"), self.toggle_map, pady=4),
            top=8, align="left")
        spacer(lay, 14)

    def train(self, keys):
        """«Потренировать слабые места»: «Вперемешку» по этим органам"""
        self.close_panel()
        self.host.quiz.train(keys)

    def toggle_map(self):
        self.close_panel()
        self.host.set_knowledge(not self.host.knowledge)


def _date(iso):
    d = stats.day_label(iso)
    return d.strftime("%d.%m") if d else ""
