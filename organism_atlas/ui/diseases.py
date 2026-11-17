"""Страница «Справочник болезней» (вкладка «Болезни»): слева - все болезни из карточек органов по системам,
с поиском, справа - статья о выбранной (что это, признаки, причины, лечение); список и статья - во всю высоту.

Оформление - как у карточки органа: над статьёй полоска цвета системы, строка с системой органов, заголовок
и текст шрифтом с засечками, внизу - источники на подложке. В списке болезни - строки (под курсором подложка,
выбранная - подложка цвета акцента с чертой слева), над каждой системой - её значок и сколько в ней найдено;
стрелки ↑ ↓ в строке поиска листают найденное.

Всё связано ссылками: в статье органы ведут на карточку органа в главном окне (страница закрывается),
а другие болезни - на свои статьи; в карточке органа заболевания ведут сюда."""

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import diseases
from ..diseases import ORGANS_OF
from ..i18n import name as organ_name, t
from ..organs import ORGANS, SYSTEM_COLORS
from ..structures import STRUCTURES
from ..theme import C
from .cards import TITLE
from .overlay import Panel, top
from .scaling import px
from .layers_panel import ScrollArea, SearchBox
from .widgets import (Dot, _hex, _mix, alive, bar, clear, color, font, hbox, heading, joined, kicker, label, linked,
                      put, rich_label, rounded_card, spaced, spacer)

LIST_W, CARD_W = 290, 540          # ширина списка и статьи при масштабе 100 %
MIN_CARD_W = 400                   # статья в узком окне - не уже


def show_diseases(host, key=None):
    """открыть справочник на болезни key (None - на первой); открытый - поднять и перейти к ней"""
    p = top(host)
    if not isinstance(p, DiseasesPanel):
        p = DiseasesPanel(host)
    p.select(key or p.key)
    return p


def refresh_diseases(host):
    """перерисовать открытый справочник (смена языка)"""
    for p in getattr(host, "panels", []):
        if isinstance(p, DiseasesPanel):
            p.refresh()


def close_diseases(host):
    for p in list(getattr(host, "panels", [])):
        if isinstance(p, DiseasesPanel):
            p.close_panel()


def open_url(url):
    """внешняя ссылка (источник) - в браузере"""
    QDesktopServices.openUrl(QUrl(url))


def fill_disease(card, key, on_link, organ_links=True):
    """статья о болезни: органы и упоминания в тексте - ссылки, внизу - другие болезни тех же органов,
    источники статьи (или сайты «Где узнать больше») и проверил ли её врач. organ_links=False - органы
    без ссылок (идёт викторина: карточка органа встала бы на место её вопроса), болезни - по-прежнему ссылки"""
    lay = card.lay
    clear(lay)
    organs = ORGANS_OF[key]
    systems = list(dict.fromkeys(ORGANS[o]["systems"][0] for o in organs))
    bar(lay, SYSTEM_COLORS[systems[0]])                     # полоска цвета системы, как у карточки органа
    kicker(lay, [(SYSTEM_COLORS[s], t("system_" + s)) for s in systems], top=14)
    name = diseases.text(key, "name")
    put(lay, label(name, size=TITLE + 3, bold=True, serif=True), top=4)
    sub = diseases.subtitle(key)
    if sub and sub != name:
        put(lay, label(sub, "muted", 11, italic=True, serif=True))
    seen = {key, *organs}                                   # органы уже ссылки в заголовке - в тексте не повторять
    if not organ_links:
        seen |= ORGANS.keys() | STRUCTURES.keys()           # ни один орган, кость или мышца - не ссылка
    put(lay, Rule(), top=14)
    heading(lay, t("disease_organs"), top=12)
    put(lay, rich_label(joined([(organ_name(o), o if organ_links else None) for o in organs], "  ·  "), on_link,
                        serif=True))
    for field in ("desc", "symptoms", "causes", "treatment"):
        heading(lay, t("disease_" + ("what" if field == "desc" else field)), top=14)
        put(lay, linked(diseases.text(key, field), on_link, seen, serif=True))
    others = diseases.related(key)
    if others:
        heading(lay, t("disease_related"), top=14)
        put(lay, rich_label(joined([(diseases.text(d, "name"), d) for d in others], "  ·  "), on_link, serif=True))
    # источники статьи, а под ними - авторитетные сайты «Где узнать больше» (по-русски там и клинические
    # рекомендации), проверил ли статью врач и оговорка - на подложке цвета страницы, мельче статьи
    foot = rounded_card(fill="bg", border="border", radius=10)
    first = True
    for title, items in ((t("disease_sources"), diseases.sources(key)), (t("disease_more"), diseases.general_sources())):
        if not items:
            continue
        heading(foot.lay, title, top=10 if first else 12, x=12)
        first = False
        for name, url in items:
            put(foot.lay, rich_label([("•  ", None), (name, url)], open_url, size=9.5), top=2, x=12)
    ok = diseases.reviewed(key)
    row = hbox(spacing=7)
    row.addWidget(Dot("ok" if ok else "day_title", 7), 0, Qt.AlignVCenter)
    row.addWidget(label(t("disease_reviewed") if ok else t("disease_unreviewed"), "muted", 9, bold=True), 1)
    put(foot.lay, row, top=14, x=12)
    put(foot.lay, label(t("disease_note"), "muted", 9), top=4, bottom=10, x=12)
    put(lay, foot, top=20)
    spacer(lay, 12)


class Rule(QWidget):
    """тонкая черта цвета рамки: отделяет заголовок статьи от текста"""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(max(1, px(1)))

    def paintEvent(self, _e):
        QPainter(self).fillRect(self.rect(), color("border"))


class Badge(QWidget):
    """кружок цвета c с восклицательным знаком цвета fg - значок предупреждения. Рисуется сам: не зависит
    от того, есть ли в шрифте знак ⚠"""

    def __init__(self, c="day_title", fg="day_bg", size=18):
        super().__init__()
        self.c, self.fg = c, fg
        self.setFixedSize(px(size), px(size))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(color(self.c))
        p.drawEllipse(QRectF(self.rect()))
        p.setPen(color(self.fg))
        p.setFont(font(9, bold=True))
        p.drawText(self.rect(), Qt.AlignCenter, "!")


class Row(QWidget):
    """строка списка болезней: щелчок открывает статью (on_click(ключ)); под курсором - лёгкая подложка,
    выбранная - подложка цвета акцента с чертой слева, название жирное цвета акцента"""

    def __init__(self, text, key, on_click, selected=False):
        super().__init__()
        self.key, self.on_click, self.selected, self.hover = key, on_click, selected, False
        lay = hbox()
        self.setLayout(lay)
        lay.setContentsMargins(px(12), px(4), px(8), px(4))
        self.label = label(text, "accent_fg" if selected else "text", 10, bold=selected)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.label)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def text(self):
        return self.label.text()

    def enterEvent(self, e):
        self.hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.hover = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            # список пересобирается после щелчка, а не внутри него: строка ещё обрабатывает мышь
            QTimer.singleShot(0, lambda: self.on_click(self.key))
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        if not (self.selected or self.hover):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_hex(_mix(C["card"], C["accent"], 0.15 if self.selected else 0.07))))
        r = QRectF(self.rect())
        p.drawRoundedRect(r, px(6), px(6))
        if self.selected:                                   # черта акцента слева
            w = max(2, px(3))
            p.setBrush(color("accent"))
            p.drawRoundedRect(QRectF(px(3), px(6), w, r.height() - 2 * px(6)), w / 2, w / 2)


class Search(SearchBox):
    """строка поиска справочника, покрупнее строки панели слоёв: стрелки ↑ ↓ выбирают предыдущую
    и следующую найденную болезнь (on_step(±1))"""

    def __init__(self, placeholder, on_change, on_enter, on_step):
        super().__init__(placeholder, "", on_change, on_enter)
        self.on_step = on_step
        self.setFont(font(10))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Up, Qt.Key_Down):
            self.on_step(1 if e.key() == Qt.Key_Down else -1)
            e.accept()
            return
        super().keyPressEvent(e)

    def retheme(self):
        super().retheme()
        self.setStyleSheet(self.styleSheet().replace("padding: %dpx %dpx" % (px(3), px(6)),
                                                     "padding: %dpx %dpx" % (px(6), px(10))))


class DiseasesPanel(Panel):
    kind = "diseases"                              # вкладка «Болезни» в шапке окна

    def __init__(self, host):
        super().__init__(host, t("diseases_title"), page=True)
        self.key = diseases.KEYS[0]
        self.query = ""
        # предупреждение - над списком и статьёй, на виду
        warn = rounded_card(fill="day_bg", border="day_title", radius=10)
        line = hbox(spacing=10)
        line.addWidget(Badge(), 0, Qt.AlignTop)
        self.warn = label(t("diseases_disclaimer"), "text", 10)
        line.addWidget(self.warn, 1)
        put(warn.lay, line, top=9, bottom=9, x=(12, 14))
        put(self.body, warn, top=12, x=0)
        row = hbox(spacing=14)
        left = rounded_card(width=px(LIST_W))
        self.search = Search(t("diseases_search"), self.on_search, self.on_enter, self.step)
        put(left.lay, self.search, top=12, bottom=8, x=12)
        self.list = ScrollArea()
        self.list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)     # до низа страницы
        put(left.lay, self.list, bottom=10, x=(6, 2))
        row.addWidget(left)
        self.area = ScrollArea()                        # статья - до CARD_W, в узком окне - уже
        self.area.setMinimumWidth(px(MIN_CARD_W) + px(12))
        self.area.setMaximumWidth(px(CARD_W) + px(12))
        self.area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.area.sizeHint = lambda: QSize(px(CARD_W) + px(12), self.area.inner.sizeHint().height())
        self.card = rounded_card()
        self.area.lay.addWidget(self.card)
        self.area.lay.addStretch(1)
        row.addWidget(self.area)
        put(self.body, row, top=12, x=0)                # список и статью заполняет select()

    def fill_list(self):
        """список найденных болезней по системам: над системой - её значок и число найденных,
        выбранная болезнь - подсвечена"""
        lay = self.list.lay
        clear(lay)
        self.items = {}
        groups = {}
        for d in diseases.search(self.query):
            groups.setdefault(diseases.system(d), []).append(d)
        for i, (system, keys) in enumerate(groups.items()):
            head = hbox(spacing=7)
            head.setContentsMargins(px(12), px(12 if i else 2), px(10), px(4))
            head.addWidget(Dot(SYSTEM_COLORS[system], 8), 0, Qt.AlignVCenter)
            head.addWidget(spaced(label(t("system_" + system).upper(), "muted", 8, bold=True, wrap=False)), 1)
            head.addWidget(label(str(len(keys)), "muted", 8, bold=True, wrap=False))
            lay.addLayout(head)
            for d in keys:
                w = Row(diseases.text(d, "name"), d, self.select, d == self.key)
                lay.addWidget(w)
                self.items[d] = w
        if not self.items:
            put(lay, label(t("diseases_nothing"), "muted", 10, italic=True), top=8, x=12)
        lay.addStretch(1)

    def on_search(self, text):
        self.query = text
        self.fill_list()
        self.list.verticalScrollBar().setValue(0)

    def on_enter(self, text):
        found = diseases.search(text)
        if found:
            self.select(found[0])

    def step(self, delta):
        """↑ ↓ в строке поиска: соседняя найденная болезнь (у края списка - остаться на месте)"""
        found = diseases.search(self.query)
        if not found:
            return
        i = found.index(self.key) if self.key in found else (-1 if delta > 0 else len(found))
        key = found[max(0, min(len(found) - 1, i + delta))]
        if key != self.key:
            self.select(key)

    def select(self, key):
        """показать статью: болезнь - здесь же, орган - карточкой в главном окне (страница закрывается)"""
        if key in ORGANS or key in STRUCTURES:            # орган, кость или мышца - карточкой в главном окне
            self.close_panel()
            self.host.open_link(key)
            return
        self.key = key
        if key not in diseases.search(self.query):
            self.query = ""                                 # перешли по ссылке к болезни вне поиска
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.fill_list()
        fill_disease(self.card, key, self.select, organ_links=self.host.mode == "study")
        self.area.verticalScrollBar().setValue(0)
        w = self.items[key]                                 # прокрутить список к ней, когда он разложится
        QTimer.singleShot(0, lambda: alive(w) and self.list.ensureWidgetVisible(w, 0, px(24)))
        self.raise_panel()

    def refresh(self):
        self.title(t("diseases_title"))
        self.search.setPlaceholderText(t("diseases_search"))
        self.warn.setText(t("diseases_disclaimer"))
        self.select(self.key)
