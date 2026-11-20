"""Real device access: discovery, reading, and writing with a backup first.

Read and write are confirmed on the owner's mouse over the USB cable and the
2.4 GHz receiver (see docs/HARDWARE-RESULTS.md). Over the receiver, writes use
the 0x40 form of each command and the mouse answers every packet. Uses the
``hid`` module from the ``hidapi`` package (the same one Rivalcfg uses).
"""

from __future__ import annotations

import os
from typing import Callable

from .backend import (ApplyResult, ApplyStatus, DeviceRef, Discovery, DiscoveryProblem,
                      ReadResult, Transport)
from .profiles import ActionKind, Binding, Layout
from .backups import save_backup
from .readback import (PAGE_FIELDS, SETTINGS_REQUESTS, ReadbackError, parse_pages,
                       parse_settings, read_request, settings_request)
from .writer import SAVE, EncodeError, for_receiver, settings_reports, single_button_reports, table_reports

VENDOR_ID = 0x1038
CONFIG_INTERFACE = 3
MODELS = {
    0x185A: ("Aerox 9 Wireless", Transport.WIRED),
    0x1858: ("Aerox 9 Wireless", Transport.RECEIVER),
}
READ_TIMEOUT_MS = 300


class HidBackend:
    simulated = False
    can_read = True
    can_write = True
    command_delay = 0.05

    def __init__(self, hid_module=None, backup_dir=None, sleep=None):
        if hid_module is None:
            import hid as hid_module  # noqa: PLC0415 - optional dependency
        import time
        self.hid = hid_module
        self.backup_dir = backup_dir
        self.sleep = sleep or time.sleep

    # -- discovery -------------------------------------------------------
    def discover(self) -> Discovery:
        if "RIVALCFG_DRY" in os.environ:
            return Discovery(problem=DiscoveryProblem.UNSUPPORTED,
                             detail="RIVALCFG_DRY is set; unset it to talk to the real mouse.")
        found = []
        for info in self.hid.enumerate(VENDOR_ID, 0):
            pid = info.get("product_id")
            if pid in MODELS and info.get("interface_number") == CONFIG_INTERFACE:
                model, transport = MODELS[pid]
                path = info["path"]
                token = path.decode() if isinstance(path, bytes) else str(path)
                found.append(DeviceRef(token, model, transport))
        if not found:
            return Discovery(problem=DiscoveryProblem.NO_DEVICE,
                             detail="No supported mouse found. Connect it and press Refresh.")
        try:
            self._open(found[0]).close()
        except OSError:
            return Discovery(problem=DiscoveryProblem.NO_PERMISSION,
                             detail="The mouse was found but can't be opened. "
                                    "Install the udev rule from the README, then replug it.")
        return Discovery(devices=tuple(found))

    def _open(self, device: DeviceRef):
        dev = self.hid.device()
        dev.open_path(device.token.encode())
        return dev

    # -- reading ---------------------------------------------------------
    def read_battery(self, device: DeviceRef) -> int | None:
        """Read the receiver battery report using Rivalcfg's Aerox 9 encoding."""
        if device.transport is not Transport.RECEIVER:
            return None
        try:
            dev = self._open(device)
            try:
                if dev.write(b"\x00\xd2") != 2:
                    return None
                reply = dev.read(64, timeout_ms=READ_TIMEOUT_MS)
            finally:
                dev.close()
        except OSError:
            return None
        if len(reply) < 2 or reply[0] != 0xD2:
            return None
        step = reply[1] & 0x7F  # bit 7 means charging
        return (step - 1) * 5 if 1 <= step <= 21 else None

    def _read_all(self, dev):
        """Read buttons and settings. Returns (ReadResult, raw replies, active preset)."""
        read = lambda: dev.read(64, timeout_ms=READ_TIMEOUT_MS)   # noqa: E731
        drain = lambda: dev.read(64, timeout_ms=20)               # noqa: E731
        pages = read_table(dev.write, read, drain)
        table = parse_pages(pages)
        replies = read_settings(dev.write, read, drain)
        settings, active = parse_settings(replies)
        other = table.other_buttons()
        if active:
            other["Active CPI preset"] = str(active)
        raw = {"table": [p.hex() for p in pages],
               "settings": {k: v.hex() for k, v in replies.items()}}
        return (ReadResult(table.layout().with_settings(settings), other_buttons=other),
                raw, active)

    def read_layout(self, device: DeviceRef) -> ReadResult:
        try:
            dev = self._open(device)
        except OSError as exc:
            return ReadResult(message=f"Couldn't open the mouse: {exc}")
        try:
            return self._read_all(dev)[0]
        except (OSError, ReadbackError) as exc:
            return ReadResult(message=f"Couldn't read the button table: {exc}")
        finally:
            dev.close()

    # -- editing and writing ---------------------------------------------
    def supports(self, binding: Binding) -> bool:
        return binding.kind in (ActionKind.DEFAULT, ActionKind.KEY, ActionKind.MOUSE_BUTTON,
                                ActionKind.SHORTCUT, ActionKind.FUNCTION, ActionKind.DISABLED)

    def write_blocker(self, device: DeviceRef) -> str | None:
        if self.backup_dir is None:
            return "No backup folder is set, so writing is off."
        return None

    def apply(self, device: DeviceRef, layout: Layout, *, lighting_only: bool = False,
              button: int | None = None) -> ApplyResult:
        """Back up, write, save to the mouse's memory, then read back and compare."""
        blocker = self.write_blocker(device)
        if blocker:
            return ApplyResult(ApplyStatus.REJECTED, blocker)
        if button is None and not lighting_only and not layout.has_left_click():
            return ApplyResult(ApplyStatus.REJECTED, "Keep Left click on at least one button.")
        # Make sure the target is still the same, single device before touching it.
        current = self.discover()
        if device.token not in {d.token for d in current.devices}:
            return ApplyResult(ApplyStatus.REJECTED,
                               "The mouse changed or was unplugged. Press Refresh and try again.")
        try:
            settings = layout.settings.lighting() if lighting_only else layout.settings
            if lighting_only and settings.is_empty():
                return ApplyResult(ApplyStatus.REJECTED, "Choose a lighting setting first.")
            reports = [] if lighting_only or button is not None else table_reports(layout)
        except (EncodeError, KeyError) as exc:
            return ApplyResult(ApplyStatus.REJECTED, f"Can't encode this layout: {exc}")
        try:
            dev = self._open(device)
        except OSError as exc:
            return ApplyResult(ApplyStatus.REJECTED, f"Couldn't open the mouse: {exc}")
        sent = 0
        try:
            try:
                before, raw, active = self._read_all(dev)
                if button is not None and before.layout.binding(button) == layout.resolved().binding(button):
                    return ApplyResult(ApplyStatus.REJECTED, "The mouse already has this mapping.",
                                       readback=before)
                backup = save_backup(self.backup_dir, f"{device.model} / {device.transport.value}",
                                     before.layout, raw, active)
            except (OSError, ReadbackError) as exc:
                return ApplyResult(ApplyStatus.REJECTED,
                                   f"Couldn't back up the mouse first, so nothing was written: {exc}")
            try:
                expected = layout
                if button is not None:
                    binding = layout.resolved().binding(button)
                    expected = before.layout.with_binding(button, binding)
                    if not expected.has_left_click():
                        return ApplyResult(ApplyStatus.REJECTED, "Keep Left click on at least one "
                                           "button on the mouse.", backup=str(backup))
                    pages = [bytes.fromhex(page) for page in raw["table"]]
                    reports = single_button_reports(pages, button, binding)
                else:
                    reports += settings_reports(settings, active)
                    if lighting_only:
                        expected = before.layout.with_settings(before.layout.settings.overlay(settings))
            except (EncodeError, KeyError) as exc:
                return ApplyResult(ApplyStatus.REJECTED, f"Can't encode the settings: {exc}",
                                   backup=str(backup))
            packets = [*reports, SAVE]
            receiver = device.transport is Transport.RECEIVER
            if receiver:
                packets = [for_receiver(p) for p in packets]
            try:
                for report in packets:
                    if dev.write(report) <= 0:
                        raise OSError("the mouse did not accept a packet")
                    sent += 1
                    if receiver:            # the receiver answers each write packet
                        dev.read(64, timeout_ms=READ_TIMEOUT_MS)
                    self.sleep(self.command_delay)
            except OSError as exc:
                status = ApplyStatus.REJECTED if sent == 0 else ApplyStatus.INTERRUPTED_UNKNOWN
                return ApplyResult(status, f"Writing stopped after {sent} of {len(packets)} "
                                           f"packets: {exc}", backup=str(backup))
            # The save command answers (11 00 ...); drain replies before reading back.
            self.sleep(0.2)
            while dev.read(64, timeout_ms=100):
                pass
            try:
                after = self._read_all(dev)[0]
            except (OSError, ReadbackError) as exc:
                return ApplyResult(ApplyStatus.COMPLETED_UNVERIFIED,
                                   f"Written, but reading it back failed: {exc}",
                                   backup=str(backup))
            problems = compare(expected, after.layout)
            if problems:
                return ApplyResult(ApplyStatus.VERIFY_MISMATCH,
                                   "The mouse reports something different: " + "; ".join(problems),
                                   backup=str(backup), readback=after)
            if button is not None:
                return ApplyResult(ApplyStatus.COMPLETED_VERIFIED,
                                   f"Button {button} saved. All 20 mappings checked.",
                                   backup=str(backup), readback=after)
            if layout.settings.zone_colors is not None:
                return ApplyResult(ApplyStatus.COMPLETED_PARTIALLY_VERIFIED,
                                   "Read-back matched for readable settings and button mappings. Zone colours "
                                   "were sent. The mouse cannot report their values.",
                                   backup=str(backup), readback=after)
            return ApplyResult(ApplyStatus.COMPLETED_VERIFIED, "Written and read back.",
                               backup=str(backup), readback=after)
        finally:
            dev.close()


def compare(wanted: Layout, got: Layout) -> list[str]:
    """Differences between what was written and what the mouse reports."""
    from .profiles import button_title
    problems = []
    w = wanted.resolved()
    for n, (a, b) in enumerate(zip(w.bindings, got.bindings), start=1):
        if a != b:
            problems.append(f"{button_title(n)} is {b.label()} instead of {a.label()}")
    for name in ("cpi_presets", "polling_hz", "reactive_color", "dim_timer_s",
                 "startup_effect"):          # zone colours can't be read back
        want = getattr(w.settings, name)
        if want is not None and getattr(got.settings, name) != want:
            problems.append(f"{name.replace('_', ' ')} is {getattr(got.settings, name)!r}")
    return problems


def read_table(write: Callable[[bytes], object], read: Callable[[], list],
               drain: Callable[[], list]) -> list[bytes]:
    """Ask for each page in turn and collect the replies. Sends only read requests."""
    while drain():
        pass
    replies = []
    for page in range(len(PAGE_FIELDS)):
        write(read_request(page))
        reply = bytes(read())
        if not reply:
            raise ReadbackError(f"no reply for page {page}")
        replies.append(reply)
        while drain():
            pass
    return replies


def read_settings(write: Callable[[bytes], object], read: Callable[[], list],
                  drain: Callable[[], list]) -> dict[str, bytes]:
    """Send each settings read request once; a missing reply leaves that value unset."""
    replies = {}
    for name in SETTINGS_REQUESTS:
        write(settings_request(name))
        replies[name] = bytes(read())
        while drain():
            pass
    return replies
