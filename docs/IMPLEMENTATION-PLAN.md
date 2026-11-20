# Aerox 9 Linux Configurator implementation plan

**Goal:** Ship a native editor that can apply and retain a complete thumb-button layout on one verified Aerox 9 transport.  
**Architecture:** Qt window → controller → independent profile store and injectable mouse backend. Keep hardware IO off the GUI thread. Treat the protocol and host permissions as adapter concerns.  
**Stack:** Python 3.11+ (proposed baseline), PySide6 Qt Widgets, pytest and pytest-qt, `pyproject.toml`.  
**Spec:** [PRODUCT-SPEC.md](PRODUCT-SPEC.md).

## Proposed modules

| Path | Responsibility |
| --- | --- |
| `src/aerox9_configurator/profiles.py` | `Binding`, `Layout`, factory defaults and profile serialization |
| `src/aerox9_configurator/backend.py` | Device enumeration and apply contract, result types, fake backend |
| `src/aerox9_configurator/rivalcfg_backend.py` | Rivalcfg device selection, capability check, slot translation and apply |
| `src/aerox9_configurator/window.py` | Window, controls and state presentation |
| `src/aerox9_configurator/controller.py` | Editing, local saves, apply lifecycle, snapshots and error handling |
| `src/aerox9_configurator/__main__.py` | App startup and explicit `--demo` mode |

**Boundary contracts.** `Binding(kind, code)` uses a validated action kind and a stable key or button identifier, never a free-form Rivalcfg expression. `Layout` has exactly 12 bindings in printed-label order 1–12. `DeviceRef` holds a session-scoped opaque target, model and transport. `Backend.discover() -> list[DeviceRef]` lists attached candidates. `Backend.apply(device: DeviceRef, layout: Layout) -> ApplyResult` takes the whole desired layout and reports one of `completed_unverified`, `rejected` (known no write started), or `interrupted_unknown` (a partial write is possible). Demo mode uses the same contract with simulated status in the UI.

## M0 — Confirm the backend before pinning it

- [ ] Check the latest [Rivalcfg release](https://github.com/flozz/rivalcfg/releases), [Aerox 9 docs](https://flozz.github.io/rivalcfg/devices/aerox9_wireless.html), and [PR #243](https://github.com/flozz/rivalcfg/pull/243). If a stable release supports Aerox 9 bindings, start there. Otherwise inspect PR head `4a8f45f1029d68621e264946ffd1101613745ba6` as the initial candidate and confirm it is the intended revision before use.
- [ ] Record the exact source and revision, dependencies, license and attribution, device match logic, how the full table and save command are formed, and whether any reliable readback exists. Distinguish source inspection from hardware evidence. If network access blocks source inspection, note it and proceed with the fake backend.
- [ ] Prefer a small Python library adapter so the backend can target a specific handle. Use the existing CLI for a local probe if useful. If the CLI cannot guarantee which attached device it selects, do not use it for ambiguous targets.

**Exit:** Add the findings to `docs/BACKEND-NOTES.md`, including unknowns and what the hardware run must resolve. No device writes.

## M1 — Profile model and fake backend

- [ ] Add `pyproject.toml`, the package, profile model and backend contract. Write profile tests first in `tests/test_profiles.py`. Reject missing or extra thumb slots, unknown schema versions, unsupported actions and invalid codes. Prove that serialization preserves the full ordered layout.
- [ ] Store a single versioned JSON profile catalog under `${XDG_CONFIG_HOME:-$HOME/.config}/aerox9-configurator/`. Use stable internal IDs for profile identity, names as data only, and atomic replace for local saves. A corrupt file should be reported and preserved, not silently overwritten.
- [ ] Implement the fake backend with configurable no-device, permission, success and interruption outcomes. Test that state changes in the fake only when apply is called. Use an isolated temporary config directory in tests.

**Exit:** `python -m pytest tests/test_profiles.py tests/test_backend.py -q` passes. No Qt or hardware required for these tests.

## M2 — Deliver the visual editor in demo mode

- [ ] Wire the Qt window to the controller. Render the grid in the physical order specified in the product spec. Provide the binding editor, named profile actions, device status, distinct local Save and device Apply, and a persistent **Demo mode** indicator. With no real backend, ordinary startup may edit profiles but cannot Apply.
- [ ] Save drafts and local profiles without touching the backend. Serialize applies through a single worker, snapshot the displayed layout at click time, and prevent edits and duplicate applies while that write runs.
- [ ] Cover behavior with `tests/test_controller.py` and `tests/test_window.py`. Verify that opening, editing, saving, factory-layout loading, reconnecting and closing issue zero writes. Verify that double-clicking Apply triggers one operation, an interruption preserves the draft, and local snapshot failure after a successful write does not turn that write into a retry.
- [ ] Run `QT_QPA_PLATFORM=offscreen python -m pytest -q`. Manually launch `python -m aerox9_configurator --demo` after installing the project in a virtual environment. Confirm keyboard access to the grid and readability in the system theme.

**Exit:** Codex can demo the full workflow with no attached mouse and provide the launch command. No real backend exposed to the UI.

## M3 — Add the real adapter and validate on the owner’s machine

- [ ] Put device-specific permissions and prerequisites in the README. Check the chosen HIDAPI backend before writing udev rules. If needed, supply a separately installed rule scoped to the supported SteelSeries product IDs and the correct device node type. Do not run the app as root or grant access to all HID devices. See [Rivalcfg Linux install notes](https://flozz.github.io/rivalcfg/install.html) and [HIDAPI’s example](https://github.com/libusb/hidapi/blob/master/udev/69-hid.rules).
- [ ] Implement the adapter against the pinned backend. Revalidate target identity immediately before writing. Refuse no permission, unvalidated mode, or ambiguous devices before sending any packets. Reject arbitrary actions, use the verified stock bindings for all non-thumb entries, and avoid general settings or reset APIs.
- [ ] Add `tests/test_rivalcfg_backend.py` with a recording transport or library stub. Assert full slot order from a fixture derived from the reviewed implementation and confirmed against the mouse. Simulate failures before the first packet, after the first packet and on save, and verify accurate result classification with no automatic retry. Treat persistence failure after any packet as unknown.
- [ ] Run [the hardware checklist](HARDWARE-VERIFICATION.md) on the actual mouse. Use an explicitly invoked development probe for the first owner-supervised write, then an owner-run development build for the GUI checks. Keep real Apply gated in ordinary builds until the transport passes. If both transports are present, make targeting unambiguous or block the write.

**Exit:** At least one transport passes the full hardware checklist. If neither does, ship a demo only and record the blocker. Do not report untested wired, Bluetooth, WoW Edition, or cross-distro support.

## M4 — First usable release

- [ ] Provide virtual-environment install and launch instructions with pinned dependencies, demo and real-mode commands, and a troubleshooting section for permission and target errors.
- [ ] Run the entire suite offscreen and smoke-test the GUI on the owner’s Linux desktop. Record OS, session type and tested transport. If another session type or distro is unavailable, list it as untested.
- [ ] Link the recorded hardware results and source notices. Name remaining limitations, especially lack of reliable readback if still applicable and the effect of full-table writes on existing custom assignments.

**Exit:** A user can edit, apply, close the app, power-cycle the mouse, and still use the new mapping on a supported transport. Local draft and device write status remain distinguishable throughout.
