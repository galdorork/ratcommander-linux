"""Side view of the mouse with the 12 thumb keys, plus the per-button menu.

The geometry lives in :mod:`side_view_data` (traced from a reference photo of
the mouse; coordinates only, no image data or logos). Each thumb key is a
widget shaped exactly like its traced key face, so what you click is what you
see. The diamond perforation is a generic lattice generated in code.
"""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QFontMetricsF, QKeyEvent,
                           QLinearGradient,
                           QPainter, QPainterPath, QPalette, QPen, QPolygonF, QRegion,
                           QTransform)
from PySide6.QtWidgets import (QAbstractButton, QDialog, QDialogButtonBox, QLabel, QMenu,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import side_view_data as geo
from .kde_widgets import icon
from .keycapture import KEY_GROUPS
from . import top_view_data as top
from .profiles import (KEYS, MOUSE_BUTTONS, MOUSE_FUNCTIONS, THUMB_COUNT, TOP_BUTTONS,
                       ActionKind, Binding, accessible_name, factory_binding, is_thumb)

VIEW_X, VIEW_Y, DESIGN_W, DESIGN_H = geo.VIEW

TOP_CAPTIONS = {13: "Left button", 14: "Right button", 15: "Wheel", 16: "Tilt left",
                17: "Tilt right", 18: "CPI", 19: "Scroll up", 20: "Scroll down"}


def factory_label(label: int) -> str:
    return factory_binding(label).short_label()


def short_text(binding: Binding, label: int) -> str:
    """Compact text drawn on a key."""
    if binding.kind is ActionKind.DEFAULT:
        return f"Default ({factory_label(label)})"
    text = binding.short_label()
    if binding.kind is ActionKind.SHORTCUT:
        mods, _, key = text.rpartition("+")
        return f"{mods}+\n{key}"       # modifiers on one line, the key below
    return text


def _pts(points) -> list[QPointF]:
    return [QPointF(x, y) for x, y in points]


def _polygon_path(points, radius: float = 0.0) -> QPainterPath:
    pts = _pts(points)
    p = QPainterPath()
    if radius <= 0:
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
        return p
    n = len(pts)
    for i in range(n):
        prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % n]

        def toward(a: QPointF, b: QPointF) -> QPointF:
            d = b - a
            length = max(math.hypot(d.x(), d.y()), 1e-6)
            return a + d * (min(radius, length / 2) / length)

        start, end = toward(cur, prev), toward(cur, nxt)
        p.moveTo(start) if i == 0 else p.lineTo(start)
        p.quadTo(cur, end)
    p.closeSubpath()
    return p


def _spline_path(points, closed: bool = False) -> QPainterPath:
    """Smooth Catmull-Rom curve through the given points."""
    pts = _pts(points)
    p = QPainterPath(pts[0])
    n = len(pts)
    for i in range(n - 1 + (1 if closed else 0)):
        p0 = pts[i - 1] if (i > 0 or closed) else pts[i]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if (i + 2 < n or closed) else p2
        p.cubicTo(p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6, p2)
    if closed:
        p.closeSubpath()
    return p


def draw_front_hint(widget: QWidget, p: QPainter) -> None:
    """"◀ Front" in the widget's bottom-right corner, same place in every view."""
    p.resetTransform()
    p.setPen(widget.palette().color(QPalette.PlaceholderText))
    p.setFont(widget.font())
    p.drawText(QRectF(widget.rect()).adjusted(0, 0, -6, -4), Qt.AlignRight | Qt.AlignBottom,
               "◀ Front")


def key_polygon(label: int) -> QPolygonF:
    return QPolygonF(_pts(geo.KEYS[label]))


def _key_rect(label: int) -> QRectF:
    return key_polygon(label).boundingRect()


def diamond_lattice(region: QPainterPath, pitch: float, wall: float, margin: float
                    ) -> QPainterPath:
    """Diamond (45-degree square) perforation filling ``region``.

    Holes sit on a square grid turned 45 degrees: ``pitch`` is the distance
    between neighbouring hole centres along a row, rows are half a pitch apart
    and shifted by half a pitch. Only holes fully inside ``region`` (with
    ``margin`` to spare) are kept.
    """
    half = pitch / 2 - wall / math.sqrt(2)          # centre-to-corner of a hole
    box = region.boundingRect()
    out = QPainterPath()
    row = 0
    y = box.top()
    while y <= box.bottom():
        x = box.left() + (pitch / 2 if row % 2 else 0.0)
        while x <= box.right():
            hole = _polygon_path([(x, y - half), (x + half, y), (x, y + half), (x - half, y)],
                                 half * 0.18)
            if region.contains(hole.boundingRect().adjusted(-margin, -margin, margin, margin)):
                out.addPath(hole)
            x += pitch
        y += pitch / 2
        row += 1
    return out


def _side_perforation() -> QPainterPath:
    """Diamonds on the top shell and the rear, clear of the side cover and nose."""
    region = BODY_PATH.subtracted(SIDE_COVER_PATH)
    front = QPainterPath()
    front.addRect(QRectF(0, 470, 560, 400))          # solid nose and lower front
    return diamond_lattice(region.subtracted(front), pitch=36.0, wall=6.0, margin=4.0)


BODY_PATH = _polygon_path(geo.OUTLINE)
def _side_cover_path() -> QPainterPath:
    p = _spline_path(geo.SIDE_COVER[1:])        # front edge, top and rear as one curve
    p.lineTo(QPointF(*geo.SIDE_COVER[0]))      # straight along the base
    p.closeSubpath()
    return p


SIDE_COVER_PATH = _side_cover_path()
PANEL_PATH = _polygon_path(geo.BEZEL, 10.0)
PERFORATION_PATH = _side_perforation()


class ThumbKey(QAbstractButton):
    """One thumb key, shaped like its traced key face."""

    menuRequested = Signal(int)

    def __init__(self, label: int, parent: QWidget):
        super().__init__(parent)
        self.label = label
        self.caption = str(label) if is_thumb(label) else TOP_CAPTIONS[label]
        self.mapping = ""
        self.changed = False
        self._shape = QPolygonF()
        self.text_px = 12.0
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(accessible_name(label))
        self.setCursor(Qt.PointingHandCursor)

    def set_shape(self, polygon: QPolygonF) -> None:
        """Polygon in this widget's own coordinates."""
        self._shape = polygon
        self.setMask(QRegion(polygon.toPolygon()))
        self.update()

    def hitButton(self, pos) -> bool:
        if self._shape.isEmpty():
            return super().hitButton(pos)
        return self._shape.containsPoint(QPointF(pos), Qt.OddEvenFill)

    def set_mapping(self, text: str, changed: bool) -> None:
        self.mapping, self.changed = text, changed
        self.setText(f"{self.label}\n{text}")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(80, 50)

    def contextMenuEvent(self, event) -> None:
        self.click()
        self.menuRequested.emit(self.label)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Menu or (event.key() == Qt.Key_F10
                                          and event.modifiers() & Qt.ShiftModifier):
            self.click()
            self.menuRequested.emit(self.label)
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        pal = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pts = [self._shape.at(i) for i in range(self._shape.count())]
        if not pts:
            return
        # Shrink slightly toward the centre so the outline stays inside the mask.
        c = sum(pts, QPointF()) / len(pts)
        inner = [c + (pt - c) * 0.94 for pt in pts]
        face = _polygon_path([(q.x(), q.y()) for q in inner], 5.0)
        if self.isChecked():
            fill, text = pal.color(QPalette.Highlight), pal.color(QPalette.HighlightedText)
        else:
            fill, text = pal.color(QPalette.Button), pal.color(QPalette.ButtonText)
            if self.underMouse():
                fill = fill.lighter(115) if fill.lightness() < 128 else fill.darker(106)
        focus = self.hasFocus()
        p.setPen(QPen(pal.color(QPalette.Highlight) if focus else pal.color(QPalette.Mid),
                      2.4 if focus else 1.1))
        p.setBrush(fill)
        p.drawPath(face)

        box = face.boundingRect()
        p.setPen(text)
        if not is_thumb(self.label) and box.height() < self.text_px * 3.2:
            # Small target (wheel, CPI, chips): one line, shrunk to fit; the
            # tooltip and the side panel carry the button's name.
            line = self.mapping.replace("\n", "")
            f = QFont(self.font())
            px = max(8, round(self.text_px))
            f.setPixelSize(px)
            while px > 8 and QFontMetricsF(f).horizontalAdvance(line) > box.width() * 0.88:
                px -= 1
                f.setPixelSize(px)
            p.setFont(f)
            p.drawText(box, Qt.AlignCenter,
                       QFontMetricsF(f).elidedText(line, Qt.ElideRight, box.width() * 0.9))
            self._draw_changed_dot(p, pal, box, inner)
            return
        num = QFont(self.font())
        num.setPixelSize(max(8, round(self.text_px * 0.85)))
        num.setBold(True)
        p.setFont(num)
        p.drawText(box.adjusted(box.width() * 0.16, box.height() * 0.08, 0, 0),
                   Qt.AlignLeft | Qt.AlignTop, self.caption)
        mapping = QFont(self.font())
        mapping.setPixelSize(max(8, round(self.text_px)))
        p.setFont(mapping)
        p.drawText(box.adjusted(box.width() * 0.1, box.height() * 0.32, -box.width() * 0.04, 0),
                   Qt.AlignCenter | Qt.TextWordWrap, self.mapping)
        self._draw_changed_dot(p, pal, box, inner)

    def _draw_changed_dot(self, p, pal, box, inner) -> None:
        if self.changed:
            # A dot marks a draft change; text elsewhere says the same.
            p.setPen(Qt.NoPen)
            p.setBrush(pal.color(QPalette.Link))
            d = min(box.height() * 0.14, self.text_px * 0.6)
            tr = inner[1]
            p.drawEllipse(QRectF(tr.x() - d * 2.4, tr.y() + d * 0.7, d, d))


class MouseSideView(QWidget):
    """Draws the side of the mouse and places the 12 thumb keys on it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAccessibleName("Side view of the mouse")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(520, 200)
        self.keys: dict[int, ThumbKey] = {n: ThumbKey(n, self) for n in range(1, THUMB_COUNT + 1)}
        for a in range(1, THUMB_COUNT):
            QWidget.setTabOrder(self.keys[a], self.keys[a + 1])

    def sizeHint(self) -> QSize:
        return QSize(820, int(820 * DESIGN_H / DESIGN_W))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return int(w * DESIGN_H / DESIGN_W)

    def _transform(self) -> QTransform:
        s = min(self.width() / DESIGN_W, self.height() / DESIGN_H)
        ox = (self.width() - DESIGN_W * s) / 2 - VIEW_X * s
        oy = (self.height() - DESIGN_H * s) / 2 - VIEW_Y * s
        return QTransform(s, 0, 0, s, ox, oy)

    def resizeEvent(self, event) -> None:
        t = self._transform()
        for label, key in self.keys.items():
            poly = t.map(key_polygon(label))
            rect = poly.boundingRect().toAlignedRect().adjusted(-1, -1, 1, 1)
            key.setGeometry(rect)
            key.text_px = 15.0 * t.m11()
            key.set_shape(poly.translated(-rect.x(), -rect.y()))
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        pal = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setTransform(self._transform())

        window = pal.color(QPalette.Window)
        dark = window.lightness() < 128
        shell = window.lighter(150) if dark else window.darker(118)
        cover = shell.darker(106) if not dark else shell.lighter(106)
        accent = shell.darker(125) if not dark else shell.darker(150)
        hole = window.darker(170) if dark else shell.darker(165)
        line = pal.color(QPalette.Mid) if not dark else window.lighter(220)

        # floor shadow
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawEllipse(QRectF(470, geo.BASE_Y - 10, 1110, 26))

        # shell with a soft top light, then the perforation
        grad = QLinearGradient(0, 320, 0, geo.BASE_Y)
        grad.setColorAt(0.0, shell.lighter(112))
        grad.setColorAt(1.0, shell.darker(108))
        p.setPen(QPen(line, 2.4))
        p.setBrush(grad)
        p.drawPath(BODY_PATH)
        p.setPen(Qt.NoPen)
        p.setBrush(hole)
        p.drawPath(PERFORATION_PATH)

        # scroll wheel
        p.setPen(QPen(line, 1.6))
        p.setBrush(accent)
        p.save()
        p.translate(*geo.WHEEL_CENTRE)
        p.rotate(geo.WHEEL_ANGLE)
        w, h = geo.WHEEL_SIZE
        p.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), h / 2, h / 2)
        p.restore()

        # side cover and seams
        p.setPen(QPen(line, 1.8))
        p.setBrush(cover)
        p.drawPath(SIDE_COVER_PATH)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(line, 1.6))
        for seam in geo.SEAMS:
            p.drawPath(_spline_path(seam))

        # bezel around the keys
        p.setBrush(accent)
        p.setPen(QPen(line, 1.4))
        p.drawPath(PANEL_PATH)

        draw_front_hint(self, p)


class MouseTopView(QWidget):
    """Top-down view, front to the left, with the main buttons, wheel and CPI button.

    The wheel's scroll and tilt functions are labelled chips with leader lines.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAccessibleName("Top view of the mouse")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(420, 300)
        self.keys: dict[int, ThumbKey] = {n: ThumbKey(n, self) for n in TOP_BUTTONS}
        order = [13, 15, 14, 18, 19, 17, 20, 16]
        for a, b in zip(order, order[1:]):
            QWidget.setTabOrder(self.keys[a], self.keys[b])
        self._vx, self._vy, self._w, self._h = top.VIEW
        self._body = _polygon_path(top.OUTLINE)
        self._perforation = self._make_perforation()

    def _make_perforation(self) -> QPainterPath:
        region = QPainterPath(self._body)
        cut = QPainterPath()
        cut.addRect(QRectF(0, 0, 425, 1100))                  # main buttons and wheel area
        return diamond_lattice(region.subtracted(cut), pitch=46.0, wall=8.0, margin=7.0)

    def sizeHint(self) -> QSize:
        return QSize(820, int(820 * self._h / self._w))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return int(w * self._h / self._w)

    def _transform(self) -> QTransform:
        s = min(self.width() / self._w, self.height() / self._h)
        ox = (self.width() - self._w * s) / 2 - self._vx * s
        oy = (self.height() - self._h * s) / 2 - self._vy * s
        return QTransform(s, 0, 0, s, ox, oy)

    def resizeEvent(self, event) -> None:
        t = self._transform()
        for label, key in self.keys.items():
            poly = t.map(QPolygonF(_pts(top.HOTSPOTS[label])))
            rect = poly.boundingRect().toAlignedRect().adjusted(-1, -1, 1, 1)
            key.setGeometry(rect)
            key.text_px = 22.0 * t.m11()
            key.set_shape(poly.translated(-rect.x(), -rect.y()))
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        pal = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setTransform(self._transform())
        window = pal.color(QPalette.Window)
        dark = window.lightness() < 128
        shell = window.lighter(150) if dark else window.darker(118)
        hole = window.darker(170) if dark else shell.darker(165)
        line = pal.color(QPalette.Mid) if not dark else window.lighter(220)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawPath(_polygon_path([(x + 10, y + 12) for x, y in top.OUTLINE]))
        grad = QLinearGradient(0, 270, 0, 760)
        grad.setColorAt(0.0, shell.lighter(108))
        grad.setColorAt(1.0, shell.darker(110))
        p.setPen(QPen(line, 2.4))
        p.setBrush(grad)
        p.drawPath(self._body)
        p.setPen(Qt.NoPen)
        p.setBrush(hole)
        p.drawPath(self._perforation)
        p.setPen(QPen(line, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(_spline_path(top.PALM_SEAM))

        # leader lines from the wheel-function chips to the wheel
        lead = QPen(pal.color(QPalette.PlaceholderText), 1.6, Qt.DashLine)
        p.setPen(lead)
        for rect, anchor in top.CHIPS.values():
            r = QPolygonF(_pts(rect)).boundingRect()
            start = QPointF(r.center().x(), r.bottom() if anchor[1] > r.bottom() else r.top())
            p.drawLine(start, QPointF(*anchor))
            p.setBrush(pal.color(QPalette.PlaceholderText))
            p.drawEllipse(QPointF(*anchor), 4, 4)
            p.setBrush(Qt.NoBrush)

        draw_front_hint(self, p)


def build_binding_menu(parent: QWidget, label: int, current: Binding,
                       supports: Callable[[Binding], bool],
                       pick: Callable[[Binding], None],
                       keyboard: Callable[[], None] | None = None) -> QMenu:
    """Menu of simple mappings for one thumb button. The current one is checked."""
    menu = QMenu(parent)
    menu.setToolTipsVisible(True)
    menu.setAccessibleName(f"Mapping for {accessible_name(label)}")
    menu.addSection(f"Button {label}: {current.label()}")
    group = QActionGroup(menu)

    def add(target: QMenu, text: str, binding: Binding) -> QAction:
        act = QAction(text, target)
        target.addAction(act)
        act.setCheckable(True)
        act.setChecked(binding == current)
        act.setEnabled(supports(binding))
        act.setActionGroup(group)
        act.triggered.connect(lambda _=False, b=binding: pick(b))
        return act

    add(menu, f"Default ({factory_binding(label).label()})", Binding.default())
    if keyboard is not None:
        menu.addAction(icon("input-keyboard-virtual"), "Virtual Keyboard…", keyboard)
    menu.addSeparator()
    for title, ids in KEY_GROUPS:
        sub = QMenu(title, menu)
        menu.addMenu(sub)
        for kid in ids:
            add(sub, KEYS[kid][0], Binding.key(kid))
    sub = QMenu("Mouse button", menu)
    menu.addMenu(sub)
    for bid, text in MOUSE_BUTTONS.items():
        add(sub, text, Binding.mouse(bid))
    sub = QMenu("Mouse function", menu)
    menu.addMenu(sub)
    for fid, text in MOUSE_FUNCTIONS.items():
        add(sub, text, Binding.function(fid))
    return menu
