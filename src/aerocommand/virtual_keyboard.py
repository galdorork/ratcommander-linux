"""On-screen keyboard for choosing a key or a shortcut for one thumb button.

Click a modifier (Ctrl, Shift, Alt, Super, AltGr) to latch it; it stays held
until clicked again. Click any other key to finish: the button gets that key,
together with the latched modifiers as a shortcut. The mouse stores at most
two modifiers per button (seen in its button table), so a third is refused.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from .kde_widgets import InlineMessage, MessageType, heading, secondary
from .profiles import KEYS, MODIFIERS, ActionKind, Binding

MAX_MODIFIERS = 2
UNIT = 46  # pixels per key unit

# (key id or modifier id or None for an unsupported key, legend, width in units)
# A row item of ("gap", "", w) leaves a blank space.
_MAIN = [
    [("KEY_ESCAPE", "Esc", 1), ("gap", "", 1),
     *[(f"KEY_F{n}", f"F{n}", 1) for n in range(1, 5)], ("gap", "", 0.5),
     *[(f"KEY_F{n}", f"F{n}", 1) for n in range(5, 9)], ("gap", "", 0.5),
     *[(f"KEY_F{n}", f"F{n}", 1) for n in range(9, 13)]],
    [("KEY_GRAVE", "`", 1), *[(f"KEY_{d}", d, 1) for d in "1234567890"],
     ("KEY_MINUS", "-", 1), ("KEY_EQUAL", "=", 1), ("KEY_BACKSPACE", "Backspace", 2)],
    [("KEY_TAB", "Tab", 1.5), *[(f"KEY_{c}", c, 1) for c in "QWERTYUIOP"],
     ("KEY_LEFTBRACKET", "[", 1), ("KEY_RIGHTBRACKET", "]", 1), ("KEY_BACKSLASH", "\\", 1.5)],
    [(None, "Caps Lock", 1.75), *[(f"KEY_{c}", c, 1) for c in "ASDFGHJKL"],
     ("KEY_SEMICOLON", ";", 1), ("KEY_APOSTROPHE", "'", 1), ("KEY_ENTER", "Enter", 2.25)],
    [("MOD_LSHIFT", "Shift", 2.25), *[(f"KEY_{c}", c, 1) for c in "ZXCVBNM"],
     ("KEY_COMMA", ",", 1), ("KEY_DOT", ".", 1), ("KEY_SLASH", "/", 1),
     ("MOD_RSHIFT", "Shift", 2.75)],
    [("MOD_LCTRL", "Ctrl", 1.25), ("MOD_LMETA", "Super", 1.25), ("MOD_LALT", "Alt", 1.25),
     ("KEY_SPACE", "Space", 6.25), ("MOD_RALT", "AltGr", 1.25), ("MOD_RMETA", "Super", 1.25),
     (None, "Menu", 1.25), ("MOD_RCTRL", "Ctrl", 1.25)],
]
_NAV = [
    [(None, "PrtSc", 1), (None, "ScrLk", 1), (None, "Pause", 1)],
    [("KEY_INSERT", "Ins", 1), ("KEY_HOME", "Home", 1), ("KEY_PAGEUP", "PgUp", 1)],
    [("KEY_DELETE", "Del", 1), ("KEY_END", "End", 1), ("KEY_PAGEDOWN", "PgDn", 1)],
    [],
    [("gap", "", 1), ("KEY_UP", "↑", 1), ("gap", "", 1)],
    [("KEY_LEFT", "←", 1), ("KEY_DOWN", "↓", 1), ("KEY_RIGHT", "→", 1)],
]


class VirtualKeyboardDialog(QDialog):
    def __init__(self, label: int, current: Binding, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Choose a key for button {label}")
        self.binding: Binding | None = None
        self.label = label
        self.modifier_buttons: dict[str, QToolButton] = {}
        self.key_buttons: dict[str, QToolButton] = {}

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(heading(f"Button {label}", 1))
        self.preview = heading("", 2)
        lay.addWidget(self.preview)
        lay.addWidget(secondary("Click Ctrl, Shift, Alt or Super to hold it (up to two), "
                                "then click a key. A single click on a key picks it on its own."))
        self.warning = InlineMessage("", MessageType.WARNING)
        self.warning.hide()
        lay.addWidget(self.warning)

        board = QHBoxLayout()
        board.setSpacing(UNIT // 3)
        board.addLayout(self._block(_MAIN))
        board.addLayout(self._block(_NAV))
        lay.addLayout(board)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        buttons.button(QDialogButtonBox.Cancel).setFocus()

        # Start from the current mapping: its modifiers held, its key marked.
        if current.kind is ActionKind.SHORTCUT:
            *mods, key = current.code.split("+")
            for m in mods:
                self.modifier_buttons[m].setChecked(True)
        else:
            key = current.code if current.kind is ActionKind.KEY else None
        if key in self.key_buttons:
            b = self.key_buttons[key]
            f = b.font()
            f.setBold(True)
            f.setUnderline(True)
            b.setFont(f)
            b.setToolTip("Current mapping")
        self._update_preview()

    # -- building --------------------------------------------------------
    def _block(self, rows) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(4)
        for i, row in enumerate(rows):
            line = QHBoxLayout()
            line.setSpacing(4)
            for kid, legend, width in row:
                w = int(width * UNIT + (width - 1) * 4)
                if kid == "gap":
                    line.addSpacing(w)
                    continue
                line.addWidget(self._key(kid, legend, w))
            line.addStretch(1)
            col.addLayout(line)
            if i == 0:
                col.addSpacing(UNIT // 4)
        return col

    def _key(self, kid: str | None, legend: str, width: int) -> QToolButton:
        b = QToolButton()
        b.setText(legend)
        b.setFixedSize(QSize(width, UNIT))
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        b.setFocusPolicy(Qt.TabFocus)
        if kid is None:
            b.setEnabled(False)
            b.setToolTip("Not available as a mapping")
        elif kid in MODIFIERS:
            b.setCheckable(True)
            # Held modifiers light up in the accent colour, like a latched key.
            b.setStyleSheet("QToolButton:checked { background: palette(highlight); "
                            "color: palette(highlighted-text); border: 1px solid "
                            "palette(highlight); border-radius: 3px; font-weight: 600; }")
            b.setAccessibleName(f"{MODIFIERS[kid][0]} modifier")
            b.setToolTip(f"Hold {MODIFIERS[kid][0]}")
            b.toggled.connect(lambda on, m=kid: self._modifier_toggled(m, on))
            self.modifier_buttons[kid] = b
        else:
            b.setAccessibleName(f"Key {KEYS[kid][0]}")
            b.clicked.connect(lambda _=False, k=kid: self.pick(k))
            self.key_buttons[kid] = b
        return b

    # -- behaviour -------------------------------------------------------
    def held(self) -> list[str]:
        """Latched modifiers in canonical order."""
        return [m for m in MODIFIERS if m in self.modifier_buttons
                and self.modifier_buttons[m].isChecked()]

    def _modifier_toggled(self, mod: str, on: bool) -> None:
        if on and len(self.held()) > MAX_MODIFIERS:
            button = self.modifier_buttons[mod]
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
            self.warning.setText(f"The mouse stores at most {MAX_MODIFIERS} modifiers per "
                                 "button. Release one first.")
            self.warning.show()
        else:
            self.warning.hide()
        self._update_preview()

    def _update_preview(self) -> None:
        names = [MODIFIERS[m][0] for m in self.held()]
        self.preview.setText(" + ".join([*names, "…"]) if names else "Pick a key")

    def pick(self, key: str) -> None:
        mods = self.held()
        self.binding = Binding.shortcut(mods, key) if mods else Binding.key(key)
        self.accept()
