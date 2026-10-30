"""Панель «Справочник болезней»: слева - все болезни из карточек органов по системам, с поиском,
справа - статья о выбранной (что это, признаки, причины, лечение).

Всё связано ссылками: в статье органы ведут на карточку органа в главном окне (панель закрывается),
а другие болезни - на свои статьи; в карточке органа заболевания ведут сюда."""

from PySide6.QtCore import Qt, QTimer

from .. import diseases
from ..diseases import ORGANS_OF
from ..i18n import name as organ_name, t
from ..organs import ORGANS
from .overlay import Panel, top
from .scaling import px
from .layers_panel import ScrollArea, SearchBox
from .widgets import alive, bar, clear, hbox, heading, joined, label, linked, put, rich_label, rounded_card, spacer

LIST_W, CARD_W = 270, 470          # ширина списка и статьи при масштабе 100 %


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


def fill_disease(card, key, on_link):
    """статья о болезни: органы и упоминания в тексте - ссылки, внизу - другие болезни тех же органов"""
    lay = card.lay
    clear(lay)
    organs = ORGANS_OF[key]
    bar(lay, ORGANS[organs[0]]["color"])
    put(lay, label(diseases.text(key, "name"), size=15, bold=True), top=12)
    put(lay, label(", ".join(t("system_" + s) for s in dict.fromkeys(ORGANS[o]["systems"][0] for o in organs)),
                   "muted", italic=True), bottom=4)
    seen = {key, *organs}                                   # органы уже ссылки в заголовке - в тексте не повторять
    heading(lay, t("disease_organs"))
    put(lay, rich_label(joined([(organ_name(o), o) for o in organs], ", "), on_link))
    for field in ("desc", "symptoms", "causes", "treatment"):
        heading(lay, t("disease_" + ("what" if field == "desc" else field)))
        put(lay, linked(diseases.text(key, field), on_link, seen))
    others = diseases.related(key)
    if others:
        heading(lay, t("disease_related"))
        put(lay, rich_label(joined([(diseases.text(d, "name"), d) for d in others], "  ·  "), on_link))
    put(lay, label(t("disease_note"), "muted", 9), top=12)
    spacer(lay, 14)


class DiseasesPanel(Panel):
    def __init__(self, host):
        super().__init__(host, t("diseases_title"))
        self.key = diseases.KEYS[0]
        self.query = ""
        h = max(px(320), min(px(600), host.height() - px(140)))
        row = hbox(spacing=12)
        left = rounded_card(width=px(LIST_W))
        self.search = SearchBox(t("diseases_search"), "", self.on_search, self.on_enter)
        put(left.lay, self.search, top=12, bottom=6, x=12)
        self.list = ScrollArea()
        self.list.setFixedHeight(h - px(60))
        put(left.lay, self.list, bottom=10, x=(12, 4))
        row.addWidget(left, 0, Qt.AlignTop)
        self.area = ScrollArea()
        self.area.setFixedSize(px(CARD_W) + px(12), h)
        self.card = rounded_card(width=px(CARD_W))
        self.area.lay.addWidget(self.card)
        self.area.lay.addStretch(1)
        row.addWidget(self.area, 0, Qt.AlignTop)
        put(self.body, row, top=10, bottom=16)          # список и статью заполняет select()

    def fill_list(self):
        """список найденных болезней по системам: выбранная - жирным, остальные - ссылки"""
        lay = self.list.lay
        clear(lay)
        self.items = {}
        system = None
        for d in diseases.search(self.query):
            if diseases.system(d) != system:
                if system is not None:
                    lay.addSpacing(px(6))
                system = diseases.system(d)
                lay.addWidget(label(t("system_" + system).upper(), "muted", 8, bold=True))
            name = diseases.text(d, "name")
            w = label(name, "accent_fg", 10, bold=True) if d == self.key else rich_label([(name, d)], self.select, size=10)
            lay.addWidget(w)
            lay.addSpacing(px(2))
            self.items[d] = w
        if not self.items:
            lay.addWidget(label(t("diseases_nothing"), "muted", 9))
        lay.addStretch(1)

    def on_search(self, text):
        self.query = text
        self.fill_list()
        self.list.verticalScrollBar().setValue(0)

    def on_enter(self, text):
        found = diseases.search(text)
        if found:
            self.select(found[0])

    def select(self, key):
        """показать статью: болезнь - здесь же, орган - карточкой в главном окне (справочник закрывается)"""
        if key in ORGANS:
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
        fill_disease(self.card, key, self.select)
        self.area.verticalScrollBar().setValue(0)
        w = self.items[key]                                 # прокрутить список к ней, когда он разложится
        QTimer.singleShot(0, lambda: alive(w) and self.list.ensureWidgetVisible(w))
        self.raise_panel()

    def refresh(self):
        self.title(t("diseases_title"))
        self.search.setPlaceholderText(t("diseases_search"))
        self.select(self.key)
