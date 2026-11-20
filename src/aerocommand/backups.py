"""Backups of what was on the mouse, taken right before every write. No Qt.

A backup holds the raw replies the mouse gave (so nothing is lost even if the
decoder changes later) and the decoded layout and settings, so it can be
loaded into the editor and written back.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .profiles import Layout, ProfileError, atomic_write_json
from .settings import DeviceSettings

SCHEMA = 1


@dataclass(frozen=True)
class Backup:
    path: Path
    taken_at: str          # local time, "2026-11-18 11:20:05"
    device: str
    layout: Layout
    raw: dict

    @property
    def title(self) -> str:
        return f"{self.taken_at} · {self.device}"


def save_backup(folder: Path, device: str, layout: Layout, raw: dict,
                active_cpi: int | None = None) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"mouse-{stamp}.json"
    n = 1
    while path.exists():
        n += 1
        path = folder / f"mouse-{stamp}-{n}.json"
    atomic_write_json(path, {
        "schema_version": SCHEMA,
        "taken_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": device,
        "layout": layout.to_json(),
        "settings": layout.settings.to_json(),
        "active_cpi": active_cpi,
        "raw": raw,
    })
    return path


def load_backup(path: Path) -> Backup:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA:
            raise ProfileError("unsupported backup version")
        layout = Layout.from_json(data["layout"]).with_settings(
            DeviceSettings.from_json(data.get("settings", {})))
        return Backup(path, str(data["taken_at"]), str(data["device"]), layout,
                      dict(data.get("raw", {})))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ProfileError(f"{path.name}: {exc}") from None


def list_backups(folder: Path) -> list[Backup]:
    """Newest first. Unreadable files are skipped."""
    out = []
    for path in sorted(folder.glob("mouse-*.json"), reverse=True):
        try:
            out.append(load_backup(path))
        except ProfileError:
            continue
    return out
