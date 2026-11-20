# RatCommander (Aerox 9 Linux configurator)

The Python package is `aerocommand` (`src/aerocommand/`), config lives in `~/.config/aerocommand/`. The docs still use the planning name `aerox9_configurator` for module paths. Keep SteelSeries and Aerox names out of the app name and icon, keep the non-affiliation notice in README, never add SteelSeries assets or decompiled code, and keep Rivalcfg credited.

Read [the product spec](docs/PRODUCT-SPEC.md) for scope and UX, [the implementation plan](docs/IMPLEMENTATION-PLAN.md) for task order and tests, and [the hardware checklist](docs/HARDWARE-VERIFICATION.md) before working with a real device.

- This is an Aerox 9 button configurator, not a general mouse driver or a SteelSeries GG clone. Prefer Python and PySide6 Qt Widgets unless the project records a different decision.
- Keep profiles and backend code independent of Qt. Use the fake backend for offline tests and explicit demo mode. A real-device error must never silently fall back to fake success.
- Editing, saving a local profile, launching, closing, or reconnecting must not write to hardware. Only an explicit, validated apply may write.
- The editor shows desired settings. A cached write is not device readback. Never claim hardware verification from an offline test, mock, CLI exit code, or cloud session.
- The side view (`side_view_data.py`) stores coordinates traced from a reference photo of the owner's mouse model: the owner chose this. Store coordinates only, never the photo, textures or logos.
- Keep the primary mouse controls at their verified stock assignments in v0.1. If the protocol rewrites a complete button table, tell the user before applying that existing custom bindings outside the thumb grid may be replaced. Never use a global device reset to restore the thumb layout.
- Keep device access unprivileged at runtime. No broad HID permissions, no background daemon, and no privilege escalation from the GUI.
- Recheck release support before using the experimental patch. Pin the chosen backend revision and retain its attribution. Keep raw button order and transport details out of the GUI.
- Run unit tests and the offscreen UI smoke test before reporting an implementation milestone complete. Report hardware checks separately for each transport.
