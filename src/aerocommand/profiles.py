"""Thumb-button bindings, layouts and the local profile catalog.

This module has no Qt or hardware dependencies.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .settings import FACTORY_SETTINGS, UNSET, DeviceSettings, SettingsError

THUMB_COUNT = 12
# Buttons 13-20 are the ones on top of the mouse (see TOP_BUTTONS).
BUTTON_COUNT = 20
SCHEMA_VERSION = 1
FACTORY_PROFILE_ID = "factory"
FACTORY_PROFILE_NAME = "Factory thumb layout"
DEVICE_PROFILE_ID = "on-mouse"


class ActionKind(str, Enum):
    DEFAULT = "default"
    KEY = "key"
    MOUSE_BUTTON = "mouse_button"
    SHORTCUT = "shortcut"   # modifiers + key, e.g. "MOD_LCTRL+MOD_LSHIFT+KEY_F6"
    DISABLED = "disabled"   # button sends nothing
    FUNCTION = "function"   # a mouse function: CPI cycle, scroll, wheel tilt


# Physical key usages, named by their US-QWERTY legend. The id is stable and
# stored in profiles; the HID usage is what a backend sends to the mouse.
# The character a key produces on screen depends on the host keyboard layout.
_KEY_TABLE: list[tuple[str, str, int]] = (
    [(f"KEY_{c}", c, 0x04 + i) for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")]
    + [(f"KEY_{d}", d, 0x1E + i) for i, d in enumerate("123456789")]
    + [("KEY_0", "0", 0x27)]
    + [
        ("KEY_ENTER", "Enter", 0x28),
        ("KEY_ESCAPE", "Escape", 0x29),
        ("KEY_BACKSPACE", "Backspace", 0x2A),
        ("KEY_TAB", "Tab", 0x2B),
        ("KEY_SPACE", "Space", 0x2C),
        ("KEY_MINUS", "-", 0x2D),
        ("KEY_EQUAL", "=", 0x2E),
        ("KEY_LEFTBRACKET", "[", 0x2F),
        ("KEY_RIGHTBRACKET", "]", 0x30),
        ("KEY_BACKSLASH", "\\", 0x31),
        ("KEY_SEMICOLON", ";", 0x33),
        ("KEY_APOSTROPHE", "'", 0x34),
        ("KEY_GRAVE", "`", 0x35),
        ("KEY_COMMA", ",", 0x36),
        ("KEY_DOT", ".", 0x37),
        ("KEY_SLASH", "/", 0x38),
    ]
    + [(f"KEY_F{n}", f"F{n}", 0x3A + n - 1) for n in range(1, 13)]
    + [
        ("KEY_INSERT", "Insert", 0x49),
        ("KEY_HOME", "Home", 0x4A),
        ("KEY_PAGEUP", "Page Up", 0x4B),
        ("KEY_DELETE", "Delete", 0x4C),
        ("KEY_END", "End", 0x4D),
        ("KEY_PAGEDOWN", "Page Down", 0x4E),
        ("KEY_RIGHT", "Right", 0x4F),
        ("KEY_LEFT", "Left", 0x50),
        ("KEY_DOWN", "Down", 0x51),
        ("KEY_UP", "Up", 0x52),
    ]
)

KEYS: dict[str, tuple[str, int]] = {kid: (label, usage) for kid, label, usage in _KEY_TABLE}

# Modifier keys by id: (display name, HID usage).
MODIFIERS: dict[str, tuple[str, int]] = {
    "MOD_LCTRL": ("Ctrl", 0xE0),
    "MOD_LSHIFT": ("Shift", 0xE1),
    "MOD_LALT": ("Alt", 0xE2),
    "MOD_LMETA": ("Super", 0xE3),
    "MOD_RCTRL": ("Right Ctrl", 0xE4),
    "MOD_RSHIFT": ("Right Shift", 0xE5),
    "MOD_RALT": ("AltGr", 0xE6),
    "MOD_RMETA": ("Right Super", 0xE7),
}

MOUSE_BUTTONS: dict[str, str] = {
    "BTN_LEFT": "Left click",
    "BTN_RIGHT": "Right click",
    "BTN_MIDDLE": "Middle click",
    "BTN_BACK": "Back",
    "BTN_FORWARD": "Forward",
}

MOUSE_FUNCTIONS: dict[str, str] = {
    "CPI_CYCLE": "CPI cycle",
    "SCROLL_UP": "Scroll up",
    "SCROLL_DOWN": "Scroll down",
    "TILT_LEFT": "Wheel tilt left",
    "TILT_RIGHT": "Wheel tilt right",
}

FACTORY_KEY_CODES = (
    "KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6",
    "KEY_7", "KEY_8", "KEY_9", "KEY_0", "KEY_MINUS", "KEY_EQUAL",
)

# Printed label -> (row name, row index from top, column index from left).
_ROWS = ("top", "middle", "bottom")
_ORDINALS = ("first", "second", "third", "fourth")


def grid_position(label: int) -> tuple[int, int]:
    """Return (row, column) in the physical grid for a printed label 1-12.

    Columns hold three labels each, numbered bottom to top: column 1 is 1, 2, 3.
    """
    if not 1 <= label <= THUMB_COUNT:
        raise ValueError(f"no thumb button {label}")
    column, from_bottom = divmod(label - 1, 3)
    return 2 - from_bottom, column


# Buttons on top of the mouse: id -> (name, factory binding as (kind, code)).
TOP_BUTTONS: dict[int, tuple[str, tuple[str, str]]] = {
    13: ("Left button", ("mouse_button", "BTN_LEFT")),
    14: ("Right button", ("mouse_button", "BTN_RIGHT")),
    15: ("Wheel click", ("mouse_button", "BTN_MIDDLE")),
    16: ("Wheel tilt left", ("function", "TILT_LEFT")),
    17: ("Wheel tilt right", ("function", "TILT_RIGHT")),
    18: ("CPI button", ("function", "CPI_CYCLE")),
    19: ("Scroll up", ("function", "SCROLL_UP")),
    20: ("Scroll down", ("function", "SCROLL_DOWN")),
}


def is_thumb(label: int) -> bool:
    return 1 <= label <= THUMB_COUNT


def button_title(label: int) -> str:
    """Short heading: "Button 7" for thumb keys, the name for the others."""
    return f"Button {label}" if is_thumb(label) else TOP_BUTTONS[label][0]


def accessible_name(label: int) -> str:
    if not is_thumb(label):
        return TOP_BUTTONS[label][0]
    row, column = grid_position(label)
    return f"Thumb {label}, {_ROWS[row]} row, {_ORDINALS[column]} column"


def button_position(label: int) -> str:
    if not is_thumb(label):
        return "Top of the mouse"
    row, column = grid_position(label)
    return f"{_ROWS[row].capitalize()} row, {_ORDINALS[column]} column"


class ProfileError(ValueError):
    """A binding, layout or profile document is invalid."""


@dataclass(frozen=True)
class Binding:
    kind: ActionKind
    code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ActionKind):
            raise ProfileError(f"unknown action kind {self.kind!r}")
        if self.kind in (ActionKind.DEFAULT, ActionKind.DISABLED):
            if self.code is not None:
                raise ProfileError(f"a {self.kind.value} binding has no code")
        elif self.kind is ActionKind.SHORTCUT:
            parts = self.code.split("+") if isinstance(self.code, str) else []
            if (len(parts) < 2 or parts[-1] not in KEYS
                    or not all(m in MODIFIERS for m in parts[:-1])):
                raise ProfileError(f"invalid shortcut {self.code!r}")
        elif self.kind is ActionKind.KEY:
            if self.code not in KEYS:
                raise ProfileError(f"unknown key {self.code!r}")
        elif self.kind is ActionKind.MOUSE_BUTTON:
            if self.code not in MOUSE_BUTTONS:
                raise ProfileError(f"unknown mouse button {self.code!r}")
        elif self.kind is ActionKind.FUNCTION:
            if self.code not in MOUSE_FUNCTIONS:
                raise ProfileError(f"unknown mouse function {self.code!r}")

    @classmethod
    def default(cls) -> "Binding":
        return cls(ActionKind.DEFAULT)

    @classmethod
    def key(cls, code: str) -> "Binding":
        return cls(ActionKind.KEY, code)

    @classmethod
    def mouse(cls, code: str) -> "Binding":
        return cls(ActionKind.MOUSE_BUTTON, code)

    @classmethod
    def function(cls, code: str) -> "Binding":
        return cls(ActionKind.FUNCTION, code)

    @classmethod
    def disabled(cls) -> "Binding":
        return cls(ActionKind.DISABLED)

    @classmethod
    def shortcut(cls, modifiers: list[str], key: str) -> "Binding":
        return cls(ActionKind.SHORTCUT, "+".join([*modifiers, key]))

    def short_label(self) -> str:
        """Without the "Key" prefix, for compact displays."""
        if self.kind is ActionKind.KEY:
            return KEYS[self.code][0]
        return self.label()

    def label(self) -> str:
        if self.kind is ActionKind.DEFAULT:
            return "Default"
        if self.kind is ActionKind.DISABLED:
            return "Disabled"
        if self.kind is ActionKind.FUNCTION:
            return MOUSE_FUNCTIONS[self.code]
        if self.kind is ActionKind.SHORTCUT:
            *mods, key = self.code.split("+")
            return "+".join([*(MODIFIERS[m][0] for m in mods), KEYS[key][0]])
        if self.kind is ActionKind.KEY:
            return f"Key {KEYS[self.code][0]}"
        return MOUSE_BUTTONS[self.code]

    def to_json(self) -> dict:
        data = {"kind": self.kind.value}
        if self.code is not None:
            data["code"] = self.code
        return data

    @classmethod
    def from_json(cls, data: object) -> "Binding":
        if not isinstance(data, dict) or set(data) - {"kind", "code"}:
            raise ProfileError(f"invalid binding {data!r}")
        try:
            kind = ActionKind(data.get("kind"))
        except ValueError:
            raise ProfileError(f"unknown action kind {data.get('kind')!r}") from None
        return cls(kind, data.get("code"))


def factory_binding(label: int) -> Binding:
    if is_thumb(label):
        return Binding.key(FACTORY_KEY_CODES[label - 1])
    kind, code = TOP_BUTTONS[label][1]
    return Binding(ActionKind(kind), code)


@dataclass(frozen=True)
class Layout:
    """20 bindings: thumb labels 1-12, then the top buttons 13-20.

    A 12-entry layout (older profiles) is padded with Default for 13-20.
    """

    bindings: tuple[Binding, ...]
    # CPI, polling and lighting. Unset fields leave the mouse as it is.
    settings: DeviceSettings = UNSET

    def __post_init__(self) -> None:
        if not isinstance(self.settings, DeviceSettings):
            raise ProfileError("layout settings must be DeviceSettings")
        if not isinstance(self.bindings, tuple) or len(self.bindings) not in (THUMB_COUNT,
                                                                                BUTTON_COUNT):
            raise ProfileError(f"a layout needs {THUMB_COUNT} or {BUTTON_COUNT} bindings")
        if not all(isinstance(b, Binding) for b in self.bindings):
            raise ProfileError("layout entries must be bindings")
        if len(self.bindings) == THUMB_COUNT:
            object.__setattr__(self, "bindings", self.bindings + tuple(
                Binding.default() for _ in range(BUTTON_COUNT - THUMB_COUNT)))

    def binding(self, label: int) -> Binding:
        return self.bindings[label - 1]

    def with_binding(self, label: int, binding: Binding) -> "Layout":
        items = list(self.bindings)
        items[label - 1] = binding
        return Layout(tuple(items), self.settings)

    def with_settings(self, settings: DeviceSettings) -> "Layout":
        return Layout(self.bindings, settings)

    def resolved(self) -> "Layout":
        """Replace each Default binding with that button's factory binding."""
        return Layout(tuple(factory_binding(i + 1) if b.kind is ActionKind.DEFAULT else b
                            for i, b in enumerate(self.bindings)), self.settings)

    def has_left_click(self) -> bool:
        return any(b == Binding.mouse("BTN_LEFT") for b in self.resolved().bindings)

    def to_json(self) -> list:
        return [b.to_json() for b in self.bindings]

    @classmethod
    def from_json(cls, data: object) -> "Layout":
        if not isinstance(data, list):
            raise ProfileError("layout must be a list")
        return cls(tuple(Binding.from_json(item) for item in data))


FACTORY_LAYOUT = Layout(tuple(factory_binding(n) for n in range(1, BUTTON_COUNT + 1)),
                        FACTORY_SETTINGS)


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    layout: Layout
    builtin: bool = False

    def to_json(self) -> dict:
        data = {"id": self.id, "name": self.name, "layout": self.layout.to_json()}
        if not self.layout.settings.is_empty():
            data["settings"] = self.layout.settings.to_json()
        return data

    @classmethod
    def from_json(cls, data: object) -> "Profile":
        if (not isinstance(data, dict) or not {"id", "name", "layout"} <= set(data)
                or set(data) - {"id", "name", "layout", "settings"}):
            raise ProfileError("invalid profile entry")
        pid, name = data["id"], data["name"]
        if not isinstance(pid, str) or not pid or pid in (FACTORY_PROFILE_ID, DEVICE_PROFILE_ID):
            raise ProfileError(f"invalid profile id {pid!r}")
        if not isinstance(name, str) or not name.strip():
            raise ProfileError("profile name must be non-empty text")
        try:
            settings = DeviceSettings.from_json(data.get("settings", {}))
        except SettingsError as exc:
            raise ProfileError(str(exc)) from None
        return cls(pid, name, Layout.from_json(data["layout"]).with_settings(settings))


FACTORY_PROFILE = Profile(FACTORY_PROFILE_ID, FACTORY_PROFILE_NAME, FACTORY_LAYOUT, builtin=True)


def default_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "aerocommand"


class CorruptCatalogError(Exception):
    def __init__(self, path: Path, reason: str):
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def parse_catalog(data: object) -> list[Profile]:
    if not isinstance(data, dict):
        raise ProfileError("catalog must be an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ProfileError(f"unsupported schema version {data.get('schema_version')!r}")
    entries = data.get("profiles")
    if not isinstance(entries, list):
        raise ProfileError("catalog has no profile list")
    profiles = [Profile.from_json(e) for e in entries]
    if len({p.id for p in profiles}) != len(profiles):
        raise ProfileError("duplicate profile id")
    return profiles


class ProfileStore:
    """Single versioned JSON catalog of user profiles.

    The built-in factory profile is never stored and cannot be changed.
    A corrupt catalog is reported by ``load`` and kept as a backup copy
    before the next save replaces it.
    """

    FILENAME = "profiles.json"

    def __init__(self, config_dir: Path | None = None):
        self.dir = Path(config_dir) if config_dir else default_config_dir()
        self.path = self.dir / self.FILENAME
        self._profiles: list[Profile] = []
        self._corrupt = False
        self.corrupt_backup: Path | None = None
        # Read from the mouse this session. Never saved; read-only like the factory one.
        self.device_profile: Profile | None = None

    def load(self) -> None:
        self._profiles = []
        self._corrupt = False
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._profiles = parse_catalog(data)
        except (OSError, ValueError) as exc:
            self._corrupt = True
            raise CorruptCatalogError(self.path, str(exc)) from exc

    @property
    def profiles(self) -> list[Profile]:
        device = [self.device_profile] if self.device_profile else []
        return [*device, FACTORY_PROFILE, *self._profiles]

    def get(self, profile_id: str) -> Profile:
        for p in self.profiles:
            if p.id == profile_id:
                return p
        raise KeyError(profile_id)

    def create(self, name: str, layout: Layout) -> Profile:
        profile = Profile(uuid.uuid4().hex, self._check_name(name), layout)
        self._commit([*self._profiles, profile])
        return profile

    def update(self, profile_id: str, *, name: str | None = None, layout: Layout | None = None) -> Profile:
        old = self._user_profile(profile_id)
        new = Profile(old.id, self._check_name(name) if name is not None else old.name,
                      layout if layout is not None else old.layout)
        self._commit([new if p.id == profile_id else p for p in self._profiles])
        return new

    def duplicate(self, profile_id: str, name: str) -> Profile:
        return self.create(name, self.get(profile_id).layout)

    def delete(self, profile_id: str) -> None:
        self._user_profile(profile_id)
        self._commit([p for p in self._profiles if p.id != profile_id])

    def _user_profile(self, profile_id: str) -> Profile:
        if profile_id == FACTORY_PROFILE_ID:
            raise ProfileError("the factory thumb layout cannot be changed")
        if profile_id == DEVICE_PROFILE_ID:
            raise ProfileError("the layout read from the mouse cannot be changed; save a copy")
        for p in self._profiles:
            if p.id == profile_id:
                return p
        raise KeyError(profile_id)

    @staticmethod
    def _check_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ProfileError("profile name must be non-empty text")
        return name.strip()

    def _commit(self, profiles: list[Profile]) -> None:
        if self._corrupt and self.path.exists():
            backup = self.path.with_name(f"{self.FILENAME}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(self.path, backup)
            self.corrupt_backup = backup
            self._corrupt = False
        atomic_write_json(self.path, {
            "schema_version": SCHEMA_VERSION,
            "profiles": [p.to_json() for p in profiles],
        })
        self._profiles = profiles
