"""История просмотренных карточек органов в режиме «Изучать»: «назад», «вперёд» и «крошки». Без Qt."""


class CardHistory:
    """items - ключи просмотренных карточек по порядку, pos - какая из них открыта (-1 - ни одной)"""

    def __init__(self, items=(), pos=-1):
        self.items, self.pos = list(items), pos

    def clear(self):
        self.items, self.pos = [], -1

    @property
    def current(self):
        return self.items[self.pos] if 0 <= self.pos < len(self.items) else None

    def record(self, key):
        """открыта карточка key: ушли в сторону от середины истории - «вперёд» больше нет"""
        if self.current != key:
            self.items = self.items[:self.pos + 1] + [key]
            self.pos = len(self.items) - 1

    def can_go(self, step):
        return bool(step) and 0 <= self.pos + step < len(self.items)

    def go(self, step):
        """на step карточек назад (step < 0) или вперёд; возвращает ключ карточки или None, если некуда"""
        if not self.can_go(step):
            return None
        self.pos += step
        return self.items[self.pos]

    def crumbs(self, n):
        """[(номер, ключ)] - до n карточек перед открытой: «крошки» над карточкой органа"""
        return [(j, k) for j, k in enumerate(self.items[:self.pos]) if j >= self.pos - n]

    def upto_current(self):
        """копия истории до открытой карточки (пересобранное окно продолжает с неё)"""
        return CardHistory(self.items[:self.pos + 1], self.pos)
