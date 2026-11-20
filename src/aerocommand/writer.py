"""Encode a layout and settings into the mouse's output reports. No Qt, no I/O.

The button table uses Rivalcfg PR #243's write: command 0x2A, 20 fields of 5
bytes, sent as three packets prefixed with their index (6, 6 and 8 fields).
Field encoding mirrors what the mouse reports (see readback.py), so a table
read from the mouse encodes back to the same bytes. Settings use the commands
from Rivalcfg's profile for this mouse. Every report starts with report id 0.

Over the 2.4 GHz receiver a write only takes effect with 0x40 added to the
command byte (Rivalcfg's ``_patch_command``); the plain command is accepted
and ignored. Reads work in their plain form on both transports.
"""

from __future__ import annotations

from .cpi_table import CPI_TO_CODE
from .profiles import KEYS, MODIFIERS, ActionKind, Binding, Layout
from .readback import FIELD_LEN, PAGE_FIELDS, SLOT_OF_BUTTON
from .settings import REACTIVE_OFF, DeviceSettings

WRITE_TABLE = 0x2A
SAVE = bytes([0x00, 0x11, 0x00])
MAX_MODIFIERS = 2
RECEIVER_FLAG = 0x40

_MOUSE_ID = {"BTN_LEFT": 1, "BTN_RIGHT": 2, "BTN_MIDDLE": 3, "BTN_BACK": 4, "BTN_FORWARD": 5}
_FUNCTION = {"CPI_CYCLE": 0x30, "SCROLL_UP": 0x31, "SCROLL_DOWN": 0x32,
             "TILT_LEFT": 0x33, "TILT_RIGHT": 0x34}
_POLLING = {1000: 0x00, 500: 0x01, 250: 0x02, 125: 0x03}
_STARTUP = {"off": (0, 0), "reactive": (0, 1), "rainbow": (1, 0), "reactive-rainbow": (1, 1)}


class EncodeError(ValueError):
    pass


def encode_field(binding: Binding) -> bytes:
    kind = binding.kind
    if kind is ActionKind.DISABLED:
        body = [0x00]
    elif kind is ActionKind.MOUSE_BUTTON:
        body = [_MOUSE_ID[binding.code]]
    elif kind is ActionKind.FUNCTION:
        body = [_FUNCTION[binding.code]]
    elif kind is ActionKind.KEY:
        body = [0x51, KEYS[binding.code][1]]
    elif kind is ActionKind.SHORTCUT:
        *mods, key = binding.code.split("+")
        if len(mods) > MAX_MODIFIERS:
            raise EncodeError(f"{binding.label()}: at most {MAX_MODIFIERS} modifiers")
        body = [0x51, *(MODIFIERS[m][1] for m in mods), KEYS[key][1]]
    else:
        raise EncodeError(f"cannot encode {binding!r}; resolve defaults first")
    return bytes(body).ljust(FIELD_LEN, b"\x00")


def encode_table(layout: Layout) -> bytes:
    """The 100-byte table, in the mouse's slot order."""
    resolved = layout.resolved()
    slots = [b""] * sum(PAGE_FIELDS)
    for button, slot in SLOT_OF_BUTTON.items():
        slots[slot] = encode_field(resolved.binding(button))
    return b"".join(slots)


def for_receiver(report: bytes) -> bytes:
    """The receiver form of a write report: the command byte with 0x40 added."""
    return bytes([report[0], report[1] | RECEIVER_FLAG]) + report[2:]


def table_reports(layout: Layout) -> list[bytes]:
    return _table_packets(encode_table(layout))


def single_button_reports(pages: list[bytes], button: int, binding: Binding) -> list[bytes]:
    """Patch one field in validated live read replies, retaining every other byte."""
    table = bytearray().join(page[1:1 + count * FIELD_LEN]
                             for page, count in zip(pages, PAGE_FIELDS, strict=True))
    start = SLOT_OF_BUTTON[button] * FIELD_LEN
    table[start:start + FIELD_LEN] = encode_field(binding)
    return _table_packets(table)


def _table_packets(table: bytes | bytearray) -> list[bytes]:
    reports, start = [], 0
    for index, count in enumerate(PAGE_FIELDS):
        end = start + count * FIELD_LEN
        reports.append(bytes([0x00, WRITE_TABLE, index]) + table[start:end])
        start = end
    return reports


def settings_reports(settings: DeviceSettings, active_cpi: int | None = None) -> list[bytes]:
    """Reports for the fields this profile sets; unset fields send nothing."""
    out: list[bytes] = []
    s = settings
    if s.cpi_presets is not None:
        count = len(s.cpi_presets)
        selected = (active_cpi - 1) if active_cpi and active_cpi <= count else 0
        out.append(bytes([0x00, 0x2D, count, selected,
                          *(CPI_TO_CODE[v] for v in s.cpi_presets)]))
    if s.polling_hz is not None:
        out.append(bytes([0x00, 0x2B, _POLLING[s.polling_hz]]))
    if s.zone_colors is not None:
        for zone, color in enumerate(s.zone_colors):
            out.append(bytes([0x00, 0x21, 0x01, zone, *_rgb(color)]))
    if s.reactive_color is not None:
        body = [0, 0, 0, 0, 0] if s.reactive_color == REACTIVE_OFF else [1, 0, *_rgb(s.reactive_color)]
        out.append(bytes([0x00, 0x26, *body]))
    if s.dim_timer_s is not None:
        out.append(bytes([0x00, 0x23, 0x0F, 0x01, 0x00, 0x00])
                   + (s.dim_timer_s * 1000).to_bytes(3, "little"))
    if s.startup_effect is not None:
        out.append(bytes([0x00, 0x27, *_STARTUP[s.startup_effect]]))
    return out


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
