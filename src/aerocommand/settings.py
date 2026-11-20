"""CPI, polling and lighting settings of a profile. No Qt, no hardware.

Every field may be ``None``, meaning "not set by this profile": the value on
the mouse is left as it is. The factory profile sets all of them. Ranges and
choices follow Rivalcfg's profile for this mouse (TrueMove Air sensor).
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

CPI_MIN, CPI_MAX, CPI_STEP = 100, 18000, 100
MAX_CPI_PRESETS = 5
POLLING_RATES = (125, 250, 500, 1000)
STARTUP_EFFECTS = {
    "off": "Off",
    "reactive": "Reactive only",
    "rainbow": "Rainbow",
    "reactive-rainbow": "Rainbow with reactive flash",
}
ZONE_NAMES = ("Top zone", "Middle zone", "Bottom zone")
DIM_TIMER_MAX = 1200
REACTIVE_OFF = "off"

_HEX = re.compile(r"^#[0-9a-f]{6}$")


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceSettings:
    cpi_presets: tuple[int, ...] | None = None
    polling_hz: int | None = None
    zone_colors: tuple[str, str, str] | None = None
    reactive_color: str | None = None          # "#rrggbb" or "off"
    startup_effect: str | None = None
    dim_timer_s: int | None = None

    def __post_init__(self) -> None:
        if self.cpi_presets is not None:
            p = self.cpi_presets
            if not isinstance(p, tuple) or not 1 <= len(p) <= MAX_CPI_PRESETS:
                raise SettingsError(f"between 1 and {MAX_CPI_PRESETS} CPI presets")
            for v in p:
                if not isinstance(v, int) or not CPI_MIN <= v <= CPI_MAX or v % CPI_STEP:
                    raise SettingsError(f"CPI {v!r} must be {CPI_MIN}-{CPI_MAX} in steps "
                                        f"of {CPI_STEP}")
        if self.polling_hz is not None and self.polling_hz not in POLLING_RATES:
            raise SettingsError(f"polling rate {self.polling_hz!r}")
        if self.zone_colors is not None:
            if (not isinstance(self.zone_colors, tuple) or len(self.zone_colors) != 3
                    or not all(isinstance(c, str) and _HEX.match(c) for c in self.zone_colors)):
                raise SettingsError(f"zone colours {self.zone_colors!r}")
        if self.reactive_color is not None and self.reactive_color != REACTIVE_OFF:
            if not (isinstance(self.reactive_color, str) and _HEX.match(self.reactive_color)):
                raise SettingsError(f"reactive colour {self.reactive_color!r}")
        if self.startup_effect is not None and self.startup_effect not in STARTUP_EFFECTS:
            raise SettingsError(f"startup effect {self.startup_effect!r}")
        if self.dim_timer_s is not None and (not isinstance(self.dim_timer_s, int)
                                             or not 0 <= self.dim_timer_s <= DIM_TIMER_MAX):
            raise SettingsError(f"dim timer {self.dim_timer_s!r}")

    def replace(self, **changes) -> "DeviceSettings":
        return dataclasses.replace(self, **changes)

    def lighting(self) -> "DeviceSettings":
        return DeviceSettings(zone_colors=self.zone_colors, reactive_color=self.reactive_color,
                              startup_effect=self.startup_effect, dim_timer_s=self.dim_timer_s)

    def overlay(self, values: "DeviceSettings") -> "DeviceSettings":
        return self.replace(**{f.name: getattr(values, f.name) for f in dataclasses.fields(values)
                               if getattr(values, f.name) is not None})

    def effective(self) -> "DeviceSettings":
        """Unset fields filled with factory values, for display."""
        return DeviceSettings(**{f.name: getattr(self, f.name)
                                 if getattr(self, f.name) is not None
                                 else getattr(FACTORY_SETTINGS, f.name)
                                 for f in dataclasses.fields(self)})

    def is_set(self, name: str) -> bool:
        return getattr(self, name) is not None

    def is_empty(self) -> bool:
        return all(getattr(self, f.name) is None for f in dataclasses.fields(self))

    def to_json(self) -> dict:
        out = {}
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if v is not None:
                out[f.name] = list(v) if isinstance(v, tuple) else v
        return out

    @classmethod
    def from_json(cls, data: object) -> "DeviceSettings":
        names = {f.name for f in dataclasses.fields(cls)}
        if not isinstance(data, dict) or set(data) - names:
            raise SettingsError(f"invalid settings {data!r}")
        values = {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}
        return cls(**values)


FACTORY_SETTINGS = DeviceSettings(
    cpi_presets=(400, 800, 1200, 2400, 3200),
    polling_hz=1000,
    zone_colors=("#ff0000", "#00ff00", "#0000ff"),
    reactive_color=REACTIVE_OFF,
    startup_effect="rainbow",
    dim_timer_s=30,
)
UNSET = DeviceSettings()
