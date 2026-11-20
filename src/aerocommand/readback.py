"""Decode the button table that the mouse reports. No Qt, no hardware.

Confirmed on the owner's mouse over USB cable (2026-11-18): sending output
report ``[0x00, 0xAA, page]`` for pages 0, 1 and 2 returns ``0xAA`` followed
by that page's 5-byte button fields. That is 6, 6 and 8 fields, the same
layout and order the Rivalcfg PR #243 write uses (command ``0x2A``).

Field encoding (first byte):
    0x51  keyboard: up to two modifier usages (0xE0-0xE7), then the key usage
    0x01-0x05  mouse button (1 left, 2 right, 3 middle, 4 back, 5 forward)
    0x30  CPI cycle, 0x31/0x32 scroll up/down, 0x33/0x34 wheel tilt (likely)
    0x00  disabled
Bytes after a non-keyboard code are not cleared by the firmware; ignore them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profiles import BUTTON_COUNT, KEYS, MODIFIERS, Binding, Layout

READ_COMMAND = 0xAA
PAGE_FIELDS = (6, 6, 8)
FIELD_LEN = 5
FIELD_COUNT = sum(PAGE_FIELDS)

# Table slot -> app button id (thumb labels 1-12, top buttons 13-20).
THUMB_SLOTS = {6: 3, 7: 6, 8: 9, 9: 12, 10: 2, 11: 5, 12: 8, 13: 11, 14: 1, 15: 4, 16: 7, 17: 10}
TOP_SLOTS = {0: 13, 1: 14, 2: 15, 3: 16, 4: 17, 5: 18, 18: 19, 19: 20}
SLOT_OF_BUTTON = {b: s for s, b in {**THUMB_SLOTS, **TOP_SLOTS}.items()}
OTHER_SLOTS = {0: "Left button", 1: "Right button", 2: "Wheel click", 3: "Wheel tilt left",
               4: "Wheel tilt right", 5: "CPI button", 18: "Scroll up", 19: "Scroll down"}

_KEY_BY_USAGE = {usage: kid for kid, (_label, usage) in KEYS.items()}
_MOD_BY_USAGE = {usage: mid for mid, (_label, usage) in MODIFIERS.items()}
_MOUSE_BY_ID = {1: "BTN_LEFT", 2: "BTN_RIGHT", 3: "BTN_MIDDLE", 4: "BTN_BACK", 5: "BTN_FORWARD"}
_FUNCTION_BY_CODE = {0x30: "CPI_CYCLE", 0x31: "SCROLL_UP", 0x32: "SCROLL_DOWN",
                     0x33: "TILT_LEFT", 0x34: "TILT_RIGHT"}


class ReadbackError(ValueError):
    """The reply does not look like a button table."""


@dataclass(frozen=True)
class Field:
    raw: bytes

    def binding(self) -> Binding | None:
        """The thumb binding this field holds, or None if the app can't show it."""
        code = self.raw[0]
        if code == 0x00:
            return Binding.disabled()
        if code in _MOUSE_BY_ID:
            return Binding.mouse(_MOUSE_BY_ID[code])
        if code in _FUNCTION_BY_CODE:
            return Binding.function(_FUNCTION_BY_CODE[code])
        if code == 0x51:
            usages = [b for b in self.raw[1:] if b]
            if not usages or usages[-1] not in _KEY_BY_USAGE:
                return None
            mods = usages[:-1]
            if not all(m in _MOD_BY_USAGE for m in mods):
                return None
            key = _KEY_BY_USAGE[usages[-1]]
            if not mods:
                return Binding.key(key)
            return Binding.shortcut([_MOD_BY_USAGE[m] for m in mods], key)
        return None

    def describe(self) -> str:
        b = self.binding()
        if b is not None:
            return b.label()
        return f"Unknown ({self.raw.hex(' ')})"


@dataclass(frozen=True)
class ButtonTable:
    fields: tuple[Field, ...]

    def layout(self) -> Layout:
        """All 20 bindings. Unknown codes raise, so nothing is guessed."""
        bindings: list[Binding | None] = [None] * BUTTON_COUNT
        for button, slot in SLOT_OF_BUTTON.items():
            b = self.fields[slot].binding()
            if b is None:
                raise ReadbackError(f"button {button} holds an action this app can't show "
                                    f"yet ({self.fields[slot].describe()})")
            bindings[button - 1] = b
        return Layout(tuple(bindings))

    thumb_layout = layout

    def other_buttons(self) -> dict[str, str]:
        return {name: self.fields[slot].describe() for slot, name in OTHER_SLOTS.items()}


def read_request(page: int) -> bytes:
    """Output report (report id 0) asking for one page of the table."""
    if page not in range(len(PAGE_FIELDS)):
        raise ValueError(page)
    return bytes([0x00, READ_COMMAND, page])


def parse_pages(replies: list[bytes]) -> ButtonTable:
    if len(replies) != len(PAGE_FIELDS):
        raise ReadbackError("expected three replies")
    fields: list[Field] = []
    for page, (reply, count) in enumerate(zip(replies, PAGE_FIELDS)):
        reply = bytes(reply)
        need = 1 + count * FIELD_LEN
        if len(reply) < need or reply[0] != READ_COMMAND:
            raise ReadbackError(f"page {page}: unexpected reply {reply[:8].hex(' ')}")
        for i in range(count):
            start = 1 + i * FIELD_LEN
            fields.append(Field(reply[start:start + FIELD_LEN]))
    return ButtonTable(tuple(fields))


# -- CPI, polling and lighting -------------------------------------------------
# Confirmed on the owner's wired mouse (2026-11-18): the "read" variant (top bit
# set) of each Rivalcfg setting command returns the stored value in the same
# format the write uses. Zone colours (0xA1) do not answer.
SETTINGS_REQUESTS = {
    "cpi": 0xAD,          # -> AD count active codes...
    "polling": 0xAB,      # -> AB code
    "reactive": 0xA6,     # -> A6 on 00 r g b
    "dim": 0xA3,          # -> A3 0F 01 xx 00 ms(3 bytes, little endian)
    "startup": 0xA7,      # -> A7 rainbow reactive
}
_POLLING = {0x00: 1000, 0x01: 500, 0x02: 250, 0x03: 125}
_STARTUP = {(0, 0): "off", (0, 1): "reactive", (1, 0): "rainbow", (1, 1): "reactive-rainbow"}


def settings_request(name: str) -> bytes:
    return bytes([0x00, SETTINGS_REQUESTS[name]])


def parse_settings(replies: dict[str, bytes]):
    """Decode whichever replies make sense; anything else stays unset (None).

    Returns (DeviceSettings, active CPI preset number or None).
    """
    from .cpi_table import CODE_TO_CPI
    from .settings import DeviceSettings

    values: dict = {}
    active = None

    def ok(name: str, length: int) -> bytes | None:
        r = bytes(replies.get(name) or b"")
        return r if len(r) >= length and r[0] == SETTINGS_REQUESTS[name] else None

    if (r := ok("cpi", 3)) and 1 <= r[1] <= 5 and len(r) >= 3 + r[1]:
        codes = r[3:3 + r[1]]
        if all(c in CODE_TO_CPI for c in codes):
            values["cpi_presets"] = tuple(CODE_TO_CPI[c] for c in codes)
            if r[2] < r[1]:
                active = r[2] + 1
    if (r := ok("polling", 2)) and r[1] in _POLLING:
        values["polling_hz"] = _POLLING[r[1]]
    if (r := ok("reactive", 6)) and r[1] in (0, 1):
        values["reactive_color"] = ("#%02x%02x%02x" % tuple(r[3:6])) if r[1] else "off"
    if (r := ok("dim", 8)) and r[1] == 0x0F:
        ms = int.from_bytes(r[5:8], "little")
        if ms % 1000 == 0 and ms // 1000 <= 1200:
            values["dim_timer_s"] = ms // 1000
    if (r := ok("startup", 3)) and (r[1], r[2]) in _STARTUP:
        values["startup_effect"] = _STARTUP[(r[1], r[2])]
    return DeviceSettings(**values), active
