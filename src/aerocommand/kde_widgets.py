"""Small widgets that follow KDE Plasma / Kirigami conventions in plain Qt Widgets.

Everything takes its colours from the active palette, so the app follows the
user's colour scheme (Breeze, Breeze Dark or any other) and its accent colour.
Icons come from the desktop icon theme with neutral fallbacks.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QStyle, QToolButton,
                               QVBoxLayout, QWidget)

# Breeze's semantic colours (KColorScheme neutral / negative / positive text).
_BREEZE = {"warning": "#f67400", "error": "#da4453", "positive": "#27ae60"}


def icon(name: str, fallback: QStyle.StandardPixmap | None = None, widget: QWidget | None = None
         ) -> QIcon:
    themed = QIcon.fromTheme(name)
    if themed.isNull() and fallback is not None and widget is not None:
        return widget.style().standardIcon(fallback)
    return themed


def heading(text: str = "", level: int = 1) -> QLabel:
    """Kirigami-style heading: level 1 is the page title, level 2 a section title."""
    label = QLabel(text)
    f = QFont(label.font())
    f.setPointSizeF(f.pointSizeF() * (1.45 if level == 1 else 1.15))
    f.setWeight(QFont.DemiBold if level == 1 else QFont.Medium)
    label.setFont(f)
    label.setWordWrap(True)
    return label


def secondary(text: str = "") -> QLabel:
    """Dimmed explanatory text."""
    label = QLabel(text)
    label.setWordWrap(True)
    pal = label.palette()
    pal.setColor(QPalette.WindowText, pal.color(QPalette.PlaceholderText))
    label.setPalette(pal)
    return label


class MessageType(str, Enum):
    INFORMATION = "information"
    POSITIVE = "positive"
    WARNING = "warning"
    ERROR = "error"


class InlineMessage(QFrame):
    """Look-alike of KMessageWidget / Kirigami.InlineMessage."""

    _ICONS = {
        MessageType.INFORMATION: ("dialog-information", QStyle.SP_MessageBoxInformation),
        MessageType.POSITIVE: ("dialog-positive", QStyle.SP_DialogApplyButton),
        MessageType.WARNING: ("dialog-warning", QStyle.SP_MessageBoxWarning),
        MessageType.ERROR: ("dialog-error", QStyle.SP_MessageBoxCritical),
    }

    def __init__(self, text: str = "", kind: MessageType = MessageType.INFORMATION,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = kind
        lay = QHBoxLayout(self)
        self._lay = lay
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(10)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignTop)
        lay.addWidget(self._icon)
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self._text, 1)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.set_kind(kind)

    def text(self) -> str:
        return self._text.text()

    def add_below(self, widget: QWidget) -> None:
        """Put a widget (a checkbox, a button) under the message text."""
        col = QVBoxLayout()
        col.setSpacing(4)
        self._lay.removeWidget(self._text)
        col.addWidget(self._text)
        col.addWidget(widget)
        self._lay.addLayout(col, 1)

    def setText(self, text: str) -> None:
        self._text.setText(text)

    def set_kind(self, kind: MessageType) -> None:
        self.kind = kind
        name, fallback = self._ICONS[kind]
        self._icon.setPixmap(icon(name, fallback, self).pixmap(QSize(22, 22)))
        self.update()

    def _colour(self) -> QColor:
        if self.kind is MessageType.INFORMATION:
            return self.palette().color(QPalette.Highlight)
        return QColor(_BREEZE[self.kind.value])

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self._colour()
        fill = QColor(c)
        fill.setAlphaF(0.18)
        p.setBrush(fill)
        p.setPen(QPen(c, 1.0))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)


class Card(QFrame):
    """Rounded, slightly raised surface, like a Kirigami card."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:
        pal = self.palette()
        base = pal.color(QPalette.Base)
        window = pal.color(QPalette.Window)
        # Blend toward the view background so the card sits gently on the window.
        fill = QColor((base.red() + window.red() * 2) // 3,
                      (base.green() + window.green() * 2) // 3,
                      (base.blue() + window.blue() * 2) // 3)
        border = QColor(pal.color(QPalette.WindowText))
        border.setAlphaF(0.14)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(border, 1.0))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)


class Chip(QLabel):
    """Pill-shaped tag tinted with the accent colour."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setContentsMargins(10, 3, 10, 3)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self.palette().color(QPalette.Highlight))
        fill = QColor(c)
        fill.setAlphaF(0.22)
        p.setPen(QPen(c, 1.0))
        p.setBrush(fill)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.end()
        super().paintEvent(event)


def tool_button(text: str, icon_name: str, fallback=None, parent: QWidget | None = None
                ) -> QToolButton:
    b = QToolButton(parent)
    b.setText(text)
    b.setIcon(icon(icon_name, fallback, b))
    b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.setAutoRaise(True)
    return b


def card_layout(card: QWidget, margins: int = 14) -> QVBoxLayout:
    lay = QVBoxLayout(card)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(8)
    return lay
