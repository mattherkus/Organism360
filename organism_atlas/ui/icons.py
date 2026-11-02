"""Значки кнопок, нарисованные QPainter: чёткие при любом масштабе и в цвет текста кнопки (меняются вместе
с темой и состоянием кнопки). Значок - функция (painter, квадрат QRectF, цвет QColor)."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPen


def _pen(c, w):
    pen = QPen(c, w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def stats(p, r, c):
    """статистика: три столбика растущей высоты на базовой линии и линия роста с точкой на конце"""
    s = r.width()
    w = max(1.0, s * 0.085)
    base = r.top() + s * 0.9
    bar = s * 0.2
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    for i, h in enumerate((0.34, 0.52, 0.72)):
        x = r.left() + s * (0.1 + i * 0.29)
        p.drawRoundedRect(QRectF(x, base - s * h, bar, s * h), bar * 0.3, bar * 0.3)
    p.setOpacity(0.55)
    p.drawRoundedRect(QRectF(r.left() + s * 0.04, base + w * 0.4, s * 0.92, w), w / 2, w / 2)     # база
    p.setOpacity(1.0)
    path = QPainterPath(QPointF(r.left() + s * 0.12, r.top() + s * 0.36))                         # линия роста
    path.lineTo(r.left() + s * 0.42, r.top() + s * 0.2)
    path.lineTo(r.left() + s * 0.62, r.top() + s * 0.28)
    path.lineTo(r.left() + s * 0.86, r.top() + s * 0.06)
    p.setPen(_pen(c, w))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(r.left() + s * 0.86, r.top() + s * 0.06), w * 1.15, w * 1.15)


def diseases(p, r, c):
    """справочник болезней: книга с медицинским крестом на обложке и закладкой"""
    s = r.width()
    w = max(1.0, s * 0.085)
    book = QRectF(r.left() + s * 0.14, r.top() + s * 0.04, s * 0.72, s * 0.92)
    p.setPen(_pen(c, w))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(book.adjusted(w / 2, w / 2, -w / 2, -w / 2), s * 0.1, s * 0.1)
    spine = book.left() + s * 0.17                                       # корешок
    p.drawLine(QPointF(spine, book.top() + w / 2), QPointF(spine, book.bottom() - w / 2))
    cx, cy = (spine + book.right()) / 2, book.top() + book.height() * 0.44
    arm, th = s * 0.2, s * 0.13                                          # крест: длина луча и толщина
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(cx - th / 2, cy - arm, th, arm * 2), th * 0.25, th * 0.25)
    p.drawRoundedRect(QRectF(cx - arm, cy - th / 2, arm * 2, th), th * 0.25, th * 0.25)
    p.setOpacity(0.6)                                                    # строка под крестом
    p.drawRoundedRect(QRectF(cx - arm, book.bottom() - s * 0.2, arm * 2, w), w / 2, w / 2)
    p.setOpacity(1.0)
