"""Download/upload chart drawn with QPainter (no QtCharts dependency)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .rates import RateTracker, human_rate, nice_ceiling


class TrafficGraph(QWidget):
    DOWN = QColor("#2b7de9")
    UP = QColor("#ff6c1a")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.tracker = RateTracker()

    def reset(self) -> None:
        self.tracker.reset()
        self.update()

    def add_sample(self, rx_total: int, tx_total: int) -> None:
        self.tracker.add(rx_total, tx_total)
        self.update()

    def rates(self) -> tuple[float, float]:
        return self.tracker.latest()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QPen(QColor("#e1e4ea"), 1))
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)

        left, right, top, bottom = 14, 14, 34, 12
        plot = QRectF(left, top, w - left - right, h - top - bottom)
        t = self.tracker
        peak = max([*t.down, *t.up, 1024.0])
        scale = nice_ceiling(peak * 1.1)

        p.setPen(QPen(QColor("#eceef3"), 1))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        self._series(p, plot, t.down, scale, self.DOWN)
        self._series(p, plot, t.up, scale, self.UP)

        font = p.font()
        font.setPointSize(10)
        p.setFont(font)
        down, up = self.rates()
        text_down, text_up = f"↓ {human_rate(down)}", f"↑ {human_rate(up)}"
        p.setPen(self.DOWN)
        p.drawText(QPointF(left, 22), text_down)
        p.setPen(self.UP)
        p.drawText(QPointF(left + p.fontMetrics().horizontalAdvance(text_down) + 24, 22), text_up)
        p.setPen(QColor("#6b7488"))
        p.drawText(QRectF(0, 8, w - right, 20),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"scale: {human_rate(scale)}")
        p.end()

    def _series(self, p: QPainter, plot: QRectF, series, scale: float, color: QColor) -> None:
        if len(series) < 2:
            return
        step = plot.width() / (self.tracker.window - 1)
        x0 = plot.right() - step * (len(series) - 1)   # newest sample sits against the right edge
        pts = [QPointF(x0 + i * step, plot.bottom() - (v / scale) * plot.height())
               for i, v in enumerate(series)]
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        area = QPainterPath(line)
        area.lineTo(pts[-1].x(), plot.bottom())
        area.lineTo(pts[0].x(), plot.bottom())
        area.closeSubpath()
        fill = QColor(color)
        fill.setAlpha(50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(area)
        p.setPen(QPen(color, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)
