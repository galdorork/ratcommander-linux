"""Map a physical key press on the host keyboard to a profile key id.

Pure Python, no Qt. On Linux, Qt reports ``nativeScanCode()`` as the XKB
keycode, which is the evdev code plus 8 on both X11 and Wayland. Using the
physical code (not the produced character) keeps bindings layout-independent,
matching how the mouse stores HID key usages.
"""

from __future__ import annotations

from .profiles import KEYS

XKB_OFFSET = 8

# evdev code -> profile key id (only keys the profile model supports).
_EVDEV: dict[int, str] = {
    1: "KEY_ESCAPE",
    **{2 + i: f"KEY_{d}" for i, d in enumerate("1234567890")},
    12: "KEY_MINUS", 13: "KEY_EQUAL", 14: "KEY_BACKSPACE", 15: "KEY_TAB",
    **{16 + i: f"KEY_{c}" for i, c in enumerate("QWERTYUIOP")},
    26: "KEY_LEFTBRACKET", 27: "KEY_RIGHTBRACKET", 28: "KEY_ENTER", 43: "KEY_BACKSLASH",
    **{30 + i: f"KEY_{c}" for i, c in enumerate("ASDFGHJKL")},
    39: "KEY_SEMICOLON", 40: "KEY_APOSTROPHE", 41: "KEY_GRAVE",
    **{44 + i: f"KEY_{c}" for i, c in enumerate("ZXCVBNM")},
    51: "KEY_COMMA", 52: "KEY_DOT", 53: "KEY_SLASH", 57: "KEY_SPACE",
    **{59 + i: f"KEY_F{i + 1}" for i in range(10)},
    87: "KEY_F11", 88: "KEY_F12",
    102: "KEY_HOME", 103: "KEY_UP", 104: "KEY_PAGEUP", 105: "KEY_LEFT",
    106: "KEY_RIGHT", 107: "KEY_END", 108: "KEY_DOWN", 109: "KEY_PAGEDOWN",
    110: "KEY_INSERT", 111: "KEY_DELETE",
}

assert set(_EVDEV.values()) <= set(KEYS), set(_EVDEV.values()) - set(KEYS)

MODIFIER_EVDEV = {29, 42, 54, 56, 97, 100, 125, 126}  # ctrl, shift, alt, meta


def key_from_scan_code(native_scan_code: int) -> str | None:
    """Return the profile key id for an XKB keycode, or None if unsupported."""
    return _EVDEV.get(native_scan_code - XKB_OFFSET)


def is_modifier(native_scan_code: int) -> bool:
    return native_scan_code - XKB_OFFSET in MODIFIER_EVDEV


# Groups for the per-button menu, in display order.
KEY_GROUPS: list[tuple[str, list[str]]] = [
    ("Letters", [f"KEY_{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]),
    ("Numbers", [f"KEY_{d}" for d in "1234567890"]),
    ("Function keys", [f"KEY_F{n}" for n in range(1, 13)]),
    ("Navigation", ["KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT", "KEY_HOME", "KEY_END",
                    "KEY_PAGEUP", "KEY_PAGEDOWN", "KEY_INSERT", "KEY_DELETE"]),
    ("Editing and symbols", ["KEY_ENTER", "KEY_ESCAPE", "KEY_BACKSPACE", "KEY_TAB",
                             "KEY_SPACE", "KEY_MINUS", "KEY_EQUAL", "KEY_LEFTBRACKET",
                             "KEY_RIGHTBRACKET", "KEY_BACKSLASH", "KEY_SEMICOLON", "KEY_APOSTROPHE",
                             "KEY_GRAVE", "KEY_COMMA", "KEY_DOT", "KEY_SLASH"]),
]

assert sorted(k for _, ks in KEY_GROUPS for k in ks) == sorted(KEYS)
