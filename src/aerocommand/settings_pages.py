"""CPI and Lighting tabs. Presentation only: values live in the controller's draft."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFormLayout,
                               QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider,
                               QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import top_view_data as top
from .kde_widgets import Card, InlineMessage, MessageType, card_layout, heading, icon, secondary
from .settings import (CPI_MAX, CPI_MIN, CPI_STEP, DIM_TIMER_MAX, MAX_CPI_PRESETS,
                       POLLING_RATES, REACTIVE_OFF, STARTUP_EFFECTS, ZONE_NAMES)
from .side_view import _polygon_path, diamond_lattice

NOT_READ = ("Not read from the mouse, so the factory values are shown. Change any of them to "
            "include them in this profile; untouched values are left as they are on the mouse.")


# -- CPI -------------------------------------------------------------------
class CpiRow(QWidget):
    def __init__(self, page: "CpiPage", index: int):
        super().__init__()
        self.page, self.index = page, index
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.badge = QLabel(str(index + 1))
        self.badge.setFixedWidth(22)
        self.badge.setAlignment(Qt.AlignCenter)
        f = self.badge.font()
        f.setBold(True)
        self.badge.setFont(f)
        lay.addWidget(self.badge)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(CPI_MIN // CPI_STEP, CPI_MAX // CPI_STEP)
        self.slider.setPageStep(4)
        self.slider.setAccessibleName(f"CPI preset {index + 1}")
        lay.addWidget(self.slider, 1)
        self.spin = QSpinBox()
        self.spin.setRange(CPI_MIN, CPI_MAX)
        self.spin.setSingleStep(CPI_STEP)
        self.spin.setSuffix(" CPI")
        self.spin.setAccelerated(True)
        self.spin.setFixedWidth(120)
        self.spin.setAccessibleName(f"CPI preset {index + 1} value")
        lay.addWidget(self.spin)
        self.remove = QToolButton()
        self.remove.setIcon(icon("list-remove"))
        self.remove.setAutoRaise(True)
        self.remove.setToolTip("Remove this preset")
        lay.addWidget(self.remove)
        self.slider.valueChanged.connect(self._slider_moved)
        self.slider.sliderReleased.connect(lambda: self.page.commit(self.index,
                                                                    self.spin.value()))
        self.spin.valueChanged.connect(self._spin_changed)
        self.remove.clicked.connect(lambda: self.page.remove(self.index))

    def show_value(self, value: int) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
        self.slider.setValue(value // CPI_STEP)
        self.spin.setValue(value)
        for w in (self.slider, self.spin):
            w.blockSignals(False)

    def _slider_moved(self, steps: int) -> None:
        value = steps * CPI_STEP
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        if not self.slider.isSliderDown():
            self.page.commit(self.index, value)

    def _spin_changed(self, value: int) -> None:
        value = round(value / CPI_STEP) * CPI_STEP
        self.page.commit(self.index, value)


class CpiPage(QWidget):
    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.c = controller
        self.rows: list[CpiRow] = []
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = Card()
        lay = card_layout(card, 16)
        lay.addWidget(heading("CPI presets", 1))
        lay.addWidget(secondary("The CPI button steps through these presets in order. "
                                f"Up to {MAX_CPI_PRESETS}, from {CPI_MIN} to {CPI_MAX} in "
                                f"steps of {CPI_STEP}."))
        self.cpi_unset = InlineMessage(NOT_READ, MessageType.INFORMATION)
        lay.addWidget(self.cpi_unset)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        lay.addLayout(self.rows_box)
        add_row = QHBoxLayout()
        self.add_btn = QPushButton(icon("list-add"), "&Add Preset")
        self.add_btn.clicked.connect(self.add)
        add_row.addWidget(self.add_btn)
        add_row.addStretch(1)
        lay.addLayout(add_row)
        lay.addSpacing(10)

        lay.addWidget(heading("Polling rate", 2))
        lay.addWidget(secondary("How often the mouse reports to the computer. Higher is "
                                "smoother and uses a little more battery."))
        self.polling_unset = InlineMessage(NOT_READ, MessageType.INFORMATION)
        lay.addWidget(self.polling_unset)
        rates = QHBoxLayout()
        rates.setSpacing(0)
        self.rate_group = QButtonGroup(self)
        self.rate_group.setExclusive(True)
        self.rate_buttons: dict[int, QPushButton] = {}
        for hz in POLLING_RATES:
            b = QPushButton(f"{hz} Hz")
            b.setCheckable(True)
            b.setMinimumWidth(90)
            self.rate_group.addButton(b, hz)
            self.rate_buttons[hz] = b
            rates.addWidget(b)
        rates.addStretch(1)
        self.rate_group.idClicked.connect(lambda hz: self._guard(polling_hz=hz))
        lay.addLayout(rates)
        lay.addStretch(1)
        outer.addWidget(card, 1)

    # -- edits -----------------------------------------------------------
    def _presets(self) -> list[int]:
        return list(self.c.draft.settings.effective().cpi_presets)

    def _guard(self, **changes) -> None:
        if not self.c.writing:
            self.c.set_settings(**changes)

    def commit(self, index: int, value: int) -> None:
        presets = self._presets()
        if index < len(presets) and presets[index] != value:
            presets[index] = value
            self._guard(cpi_presets=tuple(presets))

    def add(self) -> None:
        presets = self._presets()
        if len(presets) < MAX_CPI_PRESETS:
            presets.append(min(CPI_MAX, presets[-1] + 400))
            self._guard(cpi_presets=tuple(presets))

    def remove(self, index: int) -> None:
        presets = self._presets()
        if len(presets) > 1:
            del presets[index]
            self._guard(cpi_presets=tuple(presets))

    # -- rendering -------------------------------------------------------
    def render(self) -> None:
        s = self.c.draft.settings
        eff = s.effective()
        presets = eff.cpi_presets
        while len(self.rows) < len(presets):
            row = CpiRow(self, len(self.rows))
            self.rows.append(row)
            self.rows_box.addWidget(row)
        while len(self.rows) > len(presets):
            row = self.rows.pop()
            row.setParent(None)
            row.deleteLater()
        busy = self.c.writing
        rr = self.c.read_result
        active = int(rr.other_buttons.get("Active CPI preset", 0)) if rr else 0
        accent = self.palette().color(QPalette.Highlight)
        for i, (row, value) in enumerate(zip(self.rows, presets)):
            row.show_value(value)
            is_active = active == i + 1
            pal = row.badge.palette()
            pal.setColor(QPalette.WindowText, accent if is_active
                         else self.palette().color(QPalette.WindowText))
            row.badge.setPalette(pal)
            row.badge.setText(f"● {i + 1}" if is_active else str(i + 1))
            row.badge.setFixedWidth(40)
            row.badge.setToolTip("Active on the mouse when it was read" if is_active else "")
            row.setEnabled(not busy)
            row.remove.setVisible(len(presets) > 1)
        self.add_btn.setEnabled(not busy and len(presets) < MAX_CPI_PRESETS)
        self.cpi_unset.setVisible(not s.is_set("cpi_presets"))
        self.polling_unset.setVisible(not s.is_set("polling_hz"))
        self.rate_buttons[eff.polling_hz].setChecked(True)
        for b in self.rate_buttons.values():
            b.setEnabled(not busy)


# -- Lighting --------------------------------------------------------------
class ColorButton(QPushButton):
    def __init__(self, title: str, on_pick, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self.on_pick = on_pick
        self.color = QColor("#000000")
        self.setMinimumWidth(130)
        self.clicked.connect(self._pick)

    def set_color(self, hex_color: str) -> None:
        self.color = QColor(hex_color)
        pix = QPixmap(QSize(28, 16))
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.palette().color(QPalette.Mid), 1))
        p.setBrush(self.color)
        p.drawRoundedRect(QRectF(0.5, 0.5, 27, 15), 4, 4)
        p.end()
        self.setIcon(QIcon(pix))
        self.setIconSize(pix.size())
        self.setText(hex_color.upper())
        self.setAccessibleName(f"{self.title}: {hex_color}")

    def _pick(self) -> None:
        color = QColorDialog.getColor(self.color, self, f"Choose {self.title.lower()}")
        if color.isValid():
            self.on_pick(color.name())


class LightingPreview(QWidget):
    """Top view with the shell's holes lit in the zone colours (front to rear)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Lighting preview")
        self.colors = [QColor("#ff0000"), QColor("#00ff00"), QColor("#0000ff")]
        self.rainbow = False
        self._hue = 0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)
        self._body = _polygon_path(top.OUTLINE)
        region = QPainterPath(self._body)
        cut = QPainterPath()
        cut.addRect(QRectF(0, 0, 425, 1100))
        self._holes = diamond_lattice(region.subtracted(cut), pitch=46.0, wall=8.0, margin=7.0)
        self._buttons = [_polygon_path(top.LEFT_BUTTON), _polygon_path(top.RIGHT_BUTTON)]

    def set_state(self, colors: list[str], rainbow: bool) -> None:
        self.colors = [QColor(c) for c in colors]
        self.rainbow = rainbow
        if rainbow and not self._timer.isActive():
            self._timer.start()
        elif not rainbow:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._hue = (self._hue + 4) % 360
        self.update()

    def paintEvent(self, event) -> None:
        vx, vy, w, h = 20.0, 230.0, 960.0, 560.0
        s = min(self.width() / w, self.height() / h)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate((self.width() - w * s) / 2 - vx * s, (self.height() - h * s) / 2 - vy * s)
        p.scale(s, s)
        pal = self.palette()
        window = pal.color(QPalette.Window)
        dark = window.lightness() < 128
        shell = window.lighter(150) if dark else window.darker(118)
        line = pal.color(QPalette.Mid) if not dark else window.lighter(220)

        p.setPen(QPen(line, 2.4))
        p.setBrush(shell)
        p.drawPath(self._body)
        p.setBrush(shell.darker(115))
        for b in self._buttons:
            p.drawPath(b)

        # glow along the shell, front to rear: top, middle, bottom zone
        x0, x1 = 430.0, 960.0
        grad = QLinearGradient(x0, 0, x1, 0)
        if self.rainbow:
            for i in range(7):
                grad.setColorAt(i / 6, QColor.fromHsv((self._hue + i * 50) % 360, 230, 255))
        else:
            for i, c in enumerate(self.colors):
                grad.setColorAt(i / 2, c)
        glow = QPainterPath(self._holes)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(glow)
        p.setOpacity(0.18)
        p.drawPath(self._body.subtracted(self._buttons[0]).subtracted(self._buttons[1]))
        p.setOpacity(1.0)


class LightingPage(QWidget):
    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.c = controller
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        view = Card()
        vlay = card_layout(view, 16)
        vlay.addWidget(heading("Preview", 2))
        self.preview = LightingPreview()
        vlay.addWidget(self.preview, 1)
        vlay.addWidget(secondary("Colours run from the top zone at the front of the shell to "
                                 "the bottom zone at the rear. The preview is approximate."))
        outer.addWidget(view, 1)

        panel = Card()
        panel.setFixedWidth(360)
        lay = card_layout(panel, 16)
        lay.addWidget(heading("Lighting", 1))
        self.unset = InlineMessage(NOT_READ, MessageType.INFORMATION)
        lay.addWidget(self.unset)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.effect = QComboBox()
        for key, text in STARTUP_EFFECTS.items():
            self.effect.addItem(text, key)
        self.effect.activated.connect(
            lambda i: self._set(startup_effect=self.effect.itemData(i)))
        form.addRow("Startup effect:", self.effect)
        self.zone_buttons: list[ColorButton] = []
        for i, name in enumerate(ZONE_NAMES):
            b = ColorButton(name, lambda c, i=i: self._zone(i, c))
            self.zone_buttons.append(b)
            form.addRow(f"{name}:", b)
        self.reactive_on = QCheckBox("Flash on click")
        self.reactive_on.toggled.connect(self._reactive_toggled)
        self.reactive_btn = ColorButton("Reactive colour",
                                        lambda c: self._set(reactive_color=c))
        react = QHBoxLayout()
        react.addWidget(self.reactive_on)
        react.addWidget(self.reactive_btn)
        form.addRow("Reactive:", react)
        self.dim = QSpinBox()
        self.dim.setRange(0, DIM_TIMER_MAX)
        self.dim.setSuffix(" s")
        self.dim.setSpecialValueText("Never")
        self.dim.valueChanged.connect(lambda v: self._set(dim_timer_s=v))
        form.addRow("Dim after:", self.dim)
        lay.addLayout(form)
        self.zones_unset = InlineMessage(
            "The mouse doesn't report its zone colours, so the factory colours are shown. "
            "Pick a colour to set all three.", MessageType.INFORMATION)
        self.zones_hide = QCheckBox("Don't show this message again")
        self.zones_hide.toggled.connect(self._hide_zone_notice)
        self.zones_unset.add_below(self.zones_hide)
        lay.addWidget(self.zones_unset)
        lay.addSpacing(6)
        lay.addWidget(secondary("Picking a zone colour switches the startup effect to static "
                                "colours."))
        lay.addStretch(1)
        outer.addWidget(panel)
        self._updating = False

    def _prefs(self) -> QSettings:
        return QSettings(str(self.c.store.dir / "ui.ini"), QSettings.IniFormat)

    def _hide_zone_notice(self, hide: bool) -> None:
        if hide:
            self._prefs().setValue("hide_zone_colour_notice", True)
            self.zones_unset.hide()

    def _set(self, **changes) -> None:
        if not self._updating and not self.c.writing:
            self.c.set_settings(**changes)

    def _zone(self, index: int, color: str) -> None:
        eff = self.c.draft.settings.effective()
        colors = list(eff.zone_colors)
        colors[index] = color
        effect = eff.startup_effect
        if "rainbow" in effect:
            effect = "reactive" if effect == "reactive-rainbow" else "off"
        self._set(zone_colors=tuple(colors), startup_effect=effect)

    def _reactive_toggled(self, on: bool) -> None:
        eff = self.c.draft.settings.effective()
        if on:
            current = eff.reactive_color
            self._set(reactive_color=current if current != REACTIVE_OFF else "#ffffff")
        else:
            self._set(reactive_color=REACTIVE_OFF)

    def render(self) -> None:
        self._updating = True
        try:
            s = self.c.draft.settings
            eff = s.effective()
            self.unset.setVisible(not any(s.is_set(n) for n in (
                "zone_colors", "reactive_color", "startup_effect", "dim_timer_s")))
            self.effect.setCurrentIndex(self.effect.findData(eff.startup_effect))
            for b, c in zip(self.zone_buttons, eff.zone_colors):
                b.set_color(c)
            hidden = self._prefs().value("hide_zone_colour_notice", False, type=bool)
            self.zones_unset.setVisible(not hidden and not s.is_set("zone_colors")
                                        and self.unset.isHidden())
            on = eff.reactive_color != REACTIVE_OFF
            self.reactive_on.setChecked(on)
            self.reactive_btn.set_color(eff.reactive_color if on else "#ffffff")
            self.reactive_btn.setEnabled(on)
            self.dim.setValue(eff.dim_timer_s)
            self.preview.set_state(list(eff.zone_colors), "rainbow" in eff.startup_effect)
            for w in (self.effect, self.reactive_on, self.dim, *self.zone_buttons):
                w.setEnabled(not self.c.writing)
        finally:
            self._updating = False
