"""Icons generated in code (a padlock coloured by state) - no image files needed."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

COLORS = {"idle": "#7a8194", "busy": "#ff9f1a", "connected": "#1e8e3e"}
_cache: dict[str, QIcon] = {}


def make_icon(kind: str) -> QIcon:
    if kind in _cache:
        return _cache[kind]
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(COLORS[kind]))
    p.drawEllipse(2, 2, 60, 60)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(20, 30, 24, 18, 3, 3)
    p.setPen(QPen(QColor("white"), 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(23, 14, 18, 28, 0, 180 * 16)
    p.end()
    _cache[kind] = QIcon(pm)
    return _cache[kind]
