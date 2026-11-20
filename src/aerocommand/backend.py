"""Device discovery and apply contract, plus the simulated demo backend.

No Qt imports. A real backend lives in its own module and must never fall
back to the simulated one.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .profiles import ActionKind, Binding, Layout


class Transport(str, Enum):
    RECEIVER = "2.4 GHz receiver"
    WIRED = "USB cable"
    SIMULATED = "Simulated"


@dataclass(frozen=True)
class DeviceRef:
    """A device found by one discovery. ``token`` is opaque to the UI."""

    token: str
    model: str
    transport: Transport


class DiscoveryProblem(str, Enum):
    NO_DEVICE = "no_device"
    NO_PERMISSION = "no_permission"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    HARDWARE_DISABLED = "hardware_disabled"


@dataclass(frozen=True)
class Discovery:
    devices: tuple[DeviceRef, ...] = ()
    problem: DiscoveryProblem | None = None
    detail: str = ""


class ApplyStatus(str, Enum):
    COMPLETED_VERIFIED = "completed_verified"      # written, saved, read back identical
    COMPLETED_PARTIALLY_VERIFIED = "completed_partially_verified"
    VERIFY_MISMATCH = "verify_mismatch"            # written, but the read-back differs
    COMPLETED_UNVERIFIED = "completed_unverified"
    REJECTED = "rejected"  # known: no write started
    INTERRUPTED_UNKNOWN = "interrupted_unknown"  # a partial write is possible


@dataclass(frozen=True)
class ApplyResult:
    status: ApplyStatus
    message: str = ""
    backup: str = ""                      # path of the backup taken before writing
    readback: "ReadResult | None" = None  # what the mouse reported after writing


@dataclass(frozen=True)
class ReadResult:
    """What a read of the mouse's stored button table returned."""

    layout: Layout | None = None          # None: not read (see message)
    message: str = ""
    other_buttons: dict = field(default_factory=dict)


class Backend(Protocol):
    simulated: bool
    can_read: bool

    def discover(self) -> Discovery: ...

    def read_battery(self, device: DeviceRef) -> int | None: ...

    def supports(self, binding: Binding) -> bool: ...

    def apply(self, device: DeviceRef, layout: Layout, *, lighting_only: bool = False,
              button: int | None = None) -> ApplyResult: ...

    def read_layout(self, device: DeviceRef) -> ReadResult: ...


class DisabledBackend:
    """Used by ordinary builds until a real transport passes hardware checks."""

    simulated = False
    can_read = False

    def read_battery(self, device: DeviceRef) -> int | None:
        return None

    def discover(self) -> Discovery:
        return Discovery(
            problem=DiscoveryProblem.HARDWARE_DISABLED,
            detail="Writing to a mouse is not enabled in this build. "
                   "You can still edit and save profiles, or start with --demo.",
        )

    def supports(self, binding: Binding) -> bool:
        return binding.kind in (ActionKind.DEFAULT, ActionKind.KEY, ActionKind.MOUSE_BUTTON,
                                ActionKind.FUNCTION)

    def apply(self, device: DeviceRef, layout: Layout, *, lighting_only: bool = False,
              button: int | None = None) -> ApplyResult:
        return ApplyResult(ApplyStatus.REJECTED, "Hardware writes are disabled in this build.")

    def read_layout(self, device: DeviceRef) -> ReadResult:
        return ReadResult(message="Reading is not available in this build.")


class FakeScenario(str, Enum):
    SUCCESS = "success"
    NO_DEVICE = "no-device"
    NO_PERMISSION = "no-permission"
    REJECT = "reject"
    INTERRUPT = "interrupt"


DEMO_DEVICE = DeviceRef("demo-0", "Simulated thumb-grid mouse", Transport.SIMULATED)

# What the simulated mouse reports in demo mode: a customised layout, so the
# read is visible.
DEMO_DEVICE_LAYOUT = Layout((
    Binding.key("KEY_F10"), Binding.key("KEY_F6"), Binding.key("KEY_F9"), Binding.key("KEY_F7"),
    Binding.key("KEY_5"), Binding.mouse("BTN_FORWARD"), Binding.disabled(), Binding.key("KEY_8"),
    Binding.mouse("BTN_BACK"), Binding.shortcut(["MOD_LCTRL", "MOD_LSHIFT"], "KEY_F6"),
    Binding.key("KEY_MINUS"), Binding.disabled(),
))


@dataclass
class FakeBackend:
    """Simulated device for tests and explicit demo mode.

    ``device_layout`` changes only inside ``apply``. After an interrupted
    write it is ``None``, meaning unknown. ``gate`` lets tests hold an apply
    in flight.
    """

    scenario: FakeScenario = FakeScenario.SUCCESS
    delay: float = 0.0
    gate: threading.Event | None = None
    simulated: bool = field(default=True, init=False)
    device_layout: Layout | None = None
    applied: list[Layout] = field(default_factory=list)
    apply_calls: int = 0
    readable: bool = False      # demo mode turns this on to show a read at launch
    read_calls: int = 0

    @property
    def can_read(self) -> bool:
        return self.readable

    def read_battery(self, device: DeviceRef) -> int | None:
        return None

    def discover(self) -> Discovery:
        if self.scenario is FakeScenario.NO_DEVICE:
            return Discovery(problem=DiscoveryProblem.NO_DEVICE,
                             detail="No simulated mouse is connected.")
        if self.scenario is FakeScenario.NO_PERMISSION:
            return Discovery(problem=DiscoveryProblem.NO_PERMISSION,
                             detail="Simulated permission error: the device cannot be opened.")
        return Discovery(devices=(DEMO_DEVICE,))

    def supports(self, binding: Binding) -> bool:
        return True

    def read_layout(self, device: DeviceRef) -> ReadResult:
        self.read_calls += 1
        if not self.readable:
            return ReadResult(message="The simulated mouse can't be read.")
        if self.device_layout is None and self.apply_calls:
            return ReadResult(message="The simulated mouse is in an unknown state.")
        return ReadResult(self.device_layout or DEMO_DEVICE_LAYOUT,
                          other_buttons={"Left button": "Left click"})

    def apply(self, device: DeviceRef, layout: Layout, *, lighting_only: bool = False,
              button: int | None = None) -> ApplyResult:
        self.apply_calls += 1
        if self.gate is not None:
            self.gate.wait(10)
        elif self.delay:
            threading.Event().wait(self.delay)
        if device != DEMO_DEVICE or self.scenario in (FakeScenario.NO_DEVICE, FakeScenario.NO_PERMISSION):
            return ApplyResult(ApplyStatus.REJECTED, "The simulated device is not reachable.")
        if self.scenario is FakeScenario.REJECT:
            return ApplyResult(ApplyStatus.REJECTED, "Simulated rejection before any packet was sent.")
        if self.scenario is FakeScenario.INTERRUPT:
            self.device_layout = None
            return ApplyResult(ApplyStatus.INTERRUPTED_UNKNOWN,
                               "Simulated disconnect after the first packet.")
        if button is not None:
            current = self.device_layout or DEMO_DEVICE_LAYOUT
            layout = current.with_binding(button, layout.resolved().binding(button))
            if not layout.has_left_click():
                return ApplyResult(ApplyStatus.REJECTED, "Keep Left click on the mouse.")
        elif lighting_only:
            current = self.device_layout or DEMO_DEVICE_LAYOUT
            layout = current.with_settings(current.settings.overlay(layout.settings.lighting()))
        self.device_layout = layout
        self.applied.append(layout)
        readback = self.read_layout(device) if self.readable else None
        return ApplyResult(ApplyStatus.COMPLETED_UNVERIFIED, "Simulated write completed.",
                           readback=readback)
