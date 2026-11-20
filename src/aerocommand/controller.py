"""Editing, local saves and the apply lifecycle. No Qt imports.

Only ``apply`` ever reaches ``Backend.apply``. Everything else, including
loading the factory layout, saving, refreshing devices and closing, is local.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import time

from .backend import (ApplyResult, ApplyStatus, Backend, DeviceRef, Discovery,
                      DiscoveryProblem, ReadResult, Transport)
from .profiles import (BUTTON_COUNT, DEVICE_PROFILE_ID, FACTORY_PROFILE_ID, Binding,
                       CorruptCatalogError, Layout, Profile, ProfileError, ProfileStore,
                       atomic_write_json)

Job = Callable[[], ApplyResult]
Done = Callable[[ApplyResult], None]


class SyncRunner:
    """Runs the job immediately. For tests."""

    def __call__(self, job: Job, done: Done) -> None:
        done(job())


class ThreadRunner:
    """Runs jobs one at a time on a single worker thread.

    ``dispatch`` must deliver the completion callback on the UI thread.
    """

    def __init__(self, dispatch: Callable[[Callable[[], None]], None]):
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="apply")
        self._dispatch = dispatch

    def __call__(self, job: Job, done: Done) -> None:
        def run() -> None:
            try:
                result = job()
            except Exception as exc:  # backend bug: treat as unknown state
                result = ApplyResult(ApplyStatus.INTERRUPTED_UNKNOWN, f"Unexpected error: {exc}")
                if getattr(job, "is_read", False):
                    result = ReadResult(message=f"Unexpected error: {exc}")
            self._dispatch(lambda: done(result))

        self._pool.submit(run)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)


class ApplyRequest(str, Enum):
    STARTED = "started"
    NEEDS_ACKNOWLEDGEMENT = "needs_acknowledgement"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class DeviceState(str, Enum):
    UNKNOWN = "unknown"            # nothing written this session
    WRITE_COMPLETED = "completed"  # backend reported success, not read back
    STATE_UNKNOWN = "state_unknown"  # interrupted write


@dataclass
class Snapshot:
    layout: Layout
    device_key: str


FULL_TABLE_WARNING = (
    "Applying writes all 20 buttons, plus any CPI and lighting values this profile sets, "
    "and saves them in the mouse's memory. What's on the mouse now is backed up first; "
    "you can restore it from the menu under Backups. Settings this profile leaves unset "
    "stay as they are."
)


class Controller:
    SNAPSHOT_FILE = "last-written.json"

    def __init__(self, store: ProfileStore, backend: Backend, runner=None):
        self.store = store
        self.backend = backend
        self.runner = runner or SyncRunner()
        self._listeners: list[Callable[[], None]] = []

        self.notice = ""  # last local problem (profile store, snapshot)
        self.profile_id = FACTORY_PROFILE_ID
        self.draft: Layout = store.get(FACTORY_PROFILE_ID).layout
        self.selected_label = 1
        # Edit history for undo/redo: (draft, selected button) before each edit.
        self._undo: list[tuple[Layout, int]] = []
        self._redo: list[tuple[Layout, int]] = []
        self.discovery = Discovery()
        self.device: DeviceRef | None = None
        self.writing = False
        self.device_state = DeviceState.UNKNOWN
        self.last_result_lighting_only = False
        self.last_result: ApplyResult | None = None
        self.last_written: Snapshot | None = None
        self.full_table_acknowledged = False
        self.reading = False
        self.battery_level: int | None = None
        self._battery_pending = False
        self._selection_revision = 0
        self.read_result: ReadResult | None = None
        self.read_time = ""          # local HH:MM of the last successful read

    # -- observers -------------------------------------------------------
    def subscribe(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _changed(self) -> None:
        for fn in list(self._listeners):
            fn()

    # -- startup ---------------------------------------------------------
    def start(self) -> None:
        try:
            self.store.load()
        except CorruptCatalogError as exc:
            self.notice = (f"Your saved profiles could not be read ({exc.reason}). "
                           f"The file was left untouched; it will be backed up before the next save.")
        self.refresh_devices()

    # -- profiles --------------------------------------------------------
    @property
    def profile(self):
        return self.store.get(self.profile_id)

    @property
    def dirty(self) -> bool:
        return self.draft != self.profile.layout

    def load_profile(self, profile_id: str) -> None:
        self._require_idle()
        self.profile_id = self.store.get(profile_id).id
        self.draft = self.profile.layout
        self._undo.clear()
        self._redo.clear()
        self._changed()

    def save_profile(self) -> None:
        """Save the draft into the current profile. The factory layout is read-only."""
        self._require_idle()
        self._local(lambda: self.store.update(self.profile_id, layout=self.draft))

    def save_as(self, name: str) -> None:
        self._require_idle()

        def op():
            self.profile_id = self.store.create(name, self.draft).id
        self._local(op)

    def rename_profile(self, name: str) -> None:
        self._local(lambda: self.store.update(self.profile_id, name=name))

    def duplicate_profile(self, name: str) -> None:
        self._require_idle()

        def op():
            copy = self.store.duplicate(self.profile_id, name)
            self.profile_id = copy.id
            self.draft = copy.layout
        self._local(op)

    def delete_profile(self) -> None:
        self._require_idle()

        def op():
            self.store.delete(self.profile_id)
            self.profile_id = FACTORY_PROFILE_ID
            self.draft = self.profile.layout
        self._local(op)

    def _local(self, op) -> None:
        try:
            op()
            if self.store.corrupt_backup:
                self.notice = f"The unreadable profile file was kept as {self.store.corrupt_backup}."
                self.store.corrupt_backup = None
        except ProfileError:
            raise
        except OSError as exc:
            self.notice = f"Could not save profiles: {exc}"
        self._changed()

    # -- editing ---------------------------------------------------------
    def select_button(self, label: int) -> None:
        if not 1 <= label <= BUTTON_COUNT:
            raise ValueError(label)
        self.selected_label = label
        self._changed()

    def set_binding(self, binding: Binding, label: int | None = None) -> None:
        self._require_idle()
        if not self.backend.supports(binding):
            raise ProfileError(f"{binding.label()} is not supported by this device")
        label = label or self.selected_label
        if self.draft.binding(label) == binding:
            return
        self._undo.append((self.draft, self.selected_label))
        self._redo.clear()
        self.draft = self.draft.with_binding(label, binding)
        self._changed()

    def can_disable_selected(self) -> bool:
        label = self.selected_label
        return (self.draft.resolved().binding(label) != Binding.mouse("BTN_LEFT")
                or self.draft.with_binding(label, Binding.disabled()).has_left_click())

    def set_selected_enabled(self, enabled: bool) -> None:
        label = self.selected_label
        disabled = Binding.disabled()
        if enabled == (self.draft.binding(label) != disabled):
            return
        if not enabled:
            if not self.can_disable_selected():
                raise ProfileError("Assign Left click to another button first.")
            self.set_binding(disabled, label)
            return
        # A mouse read reports only Disabled. Recover a previous mapping from
        # this edit history when available, otherwise use the profile or default.
        previous = self.saved_binding(label)
        for layout, _ in reversed(self._undo):
            if layout.binding(label) != disabled:
                previous = layout.binding(label)
                break
        self.set_binding(previous if previous != disabled else Binding.default(), label)

    # -- undo / revert ---------------------------------------------------
    @property
    def can_undo(self) -> bool:
        return bool(self._undo) and not self.writing

    @property
    def can_redo(self) -> bool:
        return bool(self._redo) and not self.writing

    def undo(self) -> None:
        self._require_idle()
        if not self._undo:
            return
        self._redo.append((self.draft, self.selected_label))
        self.draft, self.selected_label = self._undo.pop()
        self._changed()

    def redo(self) -> None:
        self._require_idle()
        if not self._redo:
            return
        self._undo.append((self.draft, self.selected_label))
        self.draft, self.selected_label = self._redo.pop()
        self._changed()

    def set_settings(self, **changes) -> None:
        """Change CPI, polling or lighting values in the draft. Undoable."""
        self._require_idle()
        settings = self.draft.settings.replace(**changes)
        if settings == self.draft.settings:
            return
        self._undo.append((self.draft, self.selected_label))
        self._redo.clear()
        self.draft = self.draft.with_settings(settings)
        self._changed()

    def load_layout(self, layout: Layout) -> None:
        """Put a whole layout (for example a backup) into the draft. Undoable."""
        self._require_idle()
        if layout == self.draft:
            return
        self._undo.append((self.draft, self.selected_label))
        self._redo.clear()
        self.draft = layout
        self._changed()

    def saved_binding(self, label: int | None = None) -> Binding:
        """The binding in the loaded profile (or as read from the mouse)."""
        return self.profile.layout.binding(label or self.selected_label)

    def revert_button(self, label: int | None = None) -> None:
        """Put one button back to the loaded profile's value. Undoable."""
        label = label or self.selected_label
        self.set_binding_unchecked(self.saved_binding(label), label)

    def set_binding_unchecked(self, binding: Binding, label: int) -> None:
        """Like set_binding, but for values that came from a profile or the mouse."""
        self._require_idle()
        if self.draft.binding(label) == binding:
            return
        self._undo.append((self.draft, self.selected_label))
        self._redo.clear()
        self.draft = self.draft.with_binding(label, binding)
        self._changed()

    def _require_idle(self) -> None:
        if self.writing:
            raise RuntimeError("editing is paused while a write is in progress")

    # -- devices ---------------------------------------------------------
    def refresh_devices(self) -> None:
        if self.writing:
            return
        self.discovery = self.backend.discover()
        devices = self.discovery.devices
        selected = next((d for d in devices if d == self.device), None)
        if selected is None and len(devices) == 1:
            selected = devices[0]
        self._set_device(selected)

    def select_device(self, token: str | None) -> None:
        if self.writing:
            return
        self._set_device(next((d for d in self.discovery.devices if d.token == token), None))

    def _set_device(self, device: DeviceRef | None) -> None:
        if device != self.device:
            self._selection_revision += 1
            self.battery_level = None
            if self.profile_id == DEVICE_PROFILE_ID:
                was_dirty = self.dirty
                self.profile_id = FACTORY_PROFILE_ID
                if not was_dirty:
                    self.draft = self.profile.layout
                    self._undo.clear()
                    self._redo.clear()
            self.store.device_profile = None
            self.read_time = ""
            self.read_result = None
            self.last_result = None
            self.last_written = None
            self.device_state = DeviceState.UNKNOWN
            self.device = device
        self._changed()
        self.read_device()
        if not self.backend.can_read:
            self.refresh_battery()

    def refresh_battery(self) -> None:
        device = self.device
        if (device is None or device.transport is not Transport.RECEIVER
                or self.writing or self._battery_pending):
            return
        revision = self._selection_revision
        self._battery_pending = True

        def done(level):
            self._battery_pending = False
            if revision != self._selection_revision:
                self.refresh_battery()
                return
            # An unexpected worker failure also invalidates the previous reading.
            self.battery_level = level if isinstance(level, int) else None
            self._changed()

        self.runner(lambda: self.backend.read_battery(device), done)

    # -- reading ---------------------------------------------------------
    def read_device(self) -> None:
        """Read the stored button table. Sends only read requests; never writes."""
        if self.writing or self.reading or self.device is None:
            return
        if not getattr(self.backend, "can_read", False):
            return
        reader = self.backend.read_layout
        device = self.device
        revision = self._selection_revision
        self.reading = True
        self._changed()

        def job():
            return reader(device)
        job.is_read = True
        self.runner(job, lambda result: self._read_done(revision, result))

    def _read_done(self, revision: int, result: ReadResult) -> None:
        self.reading = False
        if revision != self._selection_revision:
            self.read_device()
            self._changed()
            return
        self.read_result = result
        if result.layout is not None:
            was_dirty = self.dirty
            self.read_time = time.strftime("%H:%M")
            self.store.device_profile = Profile(
                DEVICE_PROFILE_ID, f"On the mouse (read {self.read_time})", result.layout,
                builtin=True)
            # Show it straight away unless the user is in the middle of an edit.
            if not was_dirty and self.profile_id in (FACTORY_PROFILE_ID, DEVICE_PROFILE_ID):
                self.profile_id = DEVICE_PROFILE_ID
                self.draft = result.layout
                self._undo.clear()
                self._redo.clear()
        self.refresh_battery()
        self._changed()

    def apply_blocker(self, lighting_only: bool = False, button: int | None = None) -> str | None:
        """Why Apply is unavailable, or None."""
        if self.writing:
            return "A write is in progress."
        if self.reading:
            return "Reading the mouse…"
        problem = self.discovery.problem
        if problem is not None:
            return self.discovery.detail or problem.value
        if not self.discovery.devices:
            return "No mouse found. Connect it and press Refresh."
        if lighting_only and self.draft.settings.lighting().is_empty():
            return "Choose a lighting setting first."
        if button is None and not lighting_only and not self.draft.has_left_click():
            return "Keep Left click on at least one button, or you won't be able to click."
        blocker = getattr(self.backend, "write_blocker", None)
        if blocker is not None and self.device is not None and blocker(self.device):
            return blocker(self.device)
        if not getattr(self.backend, "can_write", True):
            return "Writing to the mouse isn't enabled yet. Reading works."
        if self.device is None:
            return "More than one mouse is connected. Choose which one to write to."
        if button is not None:
            if self.read_result is None or self.read_result.layout is None:
                return "Refresh to read the current mapping from the mouse."
            current = self.read_result.layout.resolved().binding(button)
            wanted = self.draft.resolved().binding(button)
            if not self.read_result.layout.with_binding(button, wanted).has_left_click():
                return "Apply Left click to another button on the mouse first."
            if wanted == current:
                return "This button already has this mapping on the mouse."
        return None

    # -- apply -----------------------------------------------------------
    def apply(self, acknowledge_full_table: bool = False, *, lighting_only: bool = False,
              button: int | None = None) -> ApplyRequest:
        if self.writing:
            return ApplyRequest.BUSY
        if self.apply_blocker(lighting_only, button) is not None:
            return ApplyRequest.UNAVAILABLE
        if not lighting_only and button is None:
            if not (self.full_table_acknowledged or acknowledge_full_table):
                return ApplyRequest.NEEDS_ACKNOWLEDGEMENT
            self.full_table_acknowledged = True

        layout = self.draft.resolved()  # snapshot of what is shown, at click time
        device = self.device
        self.writing = True
        self._changed()
        self.runner(lambda: self.backend.apply(device, layout, lighting_only=lighting_only, button=button),
                    lambda result: self._apply_done(device, layout, result, lighting_only, button))
        return ApplyRequest.STARTED

    def _apply_done(self, device: DeviceRef, layout: Layout, result: ApplyResult, lighting_only: bool,
                    button: int | None) -> None:
        self.writing = False
        self.last_result_lighting_only = lighting_only
        self.last_result = result
        if result.readback is not None and result.readback.layout is not None:
            # What the mouse now reports becomes the "On the mouse" profile.
            self.read_result = result.readback
            self.read_time = time.strftime("%H:%M")
            self.store.device_profile = Profile(
                DEVICE_PROFILE_ID, f"On the mouse (read {self.read_time})",
                result.readback.layout, builtin=True)
        elif result.status in (ApplyStatus.INTERRUPTED_UNKNOWN, ApplyStatus.COMPLETED_UNVERIFIED):
            self.read_result = None
        if result.status in (ApplyStatus.COMPLETED_VERIFIED, ApplyStatus.VERIFY_MISMATCH,
                             ApplyStatus.COMPLETED_PARTIALLY_VERIFIED, ApplyStatus.COMPLETED_UNVERIFIED):
            self.device_state = DeviceState.WRITE_COMPLETED
            if lighting_only or button is not None:
                # A complete profile was never sent. Keep the previous full-write record.
                self._changed()
                return
            self.last_written = Snapshot(layout, f"{device.model} / {device.transport.value}")
            try:
                self._save_snapshot()
            except OSError as exc:
                self.notice = (f"The write completed, but the local record of it could not be "
                               f"saved: {exc}")
        elif result.status is ApplyStatus.INTERRUPTED_UNKNOWN:
            self.device_state = DeviceState.STATE_UNKNOWN
        self._changed()

    def _save_snapshot(self) -> None:
        snap = self.last_written
        atomic_write_json(self.store.dir / self.SNAPSHOT_FILE, {
            "schema_version": 1,
            "device": snap.device_key,
            "layout": snap.layout.to_json(),
        })

    def load_factory_layout(self) -> None:
        self.load_profile(FACTORY_PROFILE_ID)
