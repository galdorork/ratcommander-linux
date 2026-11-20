# Backend notes (M0)

## Update, 18 November 2026: readback works over USB cable

Tested on the owner's mouse (wired, 1038:185a, interface 3). Sending output report `[0x00, 0xAA, page]` for pages 0, 1 and 2 returns `0xAA` followed by that page's button fields: 6, 6 and 8 fields of 5 bytes, the same layout and order PR #243 writes. The thumb slot order in the PR is correct (labels 3, 6, 9, 12, 2, 5, 8, 11, 1, 4, 7, 10). Field codes seen: `0x51` key, with up to two modifier usages (`0xE0`–`0xE7`) before the key usage (for example `51 E0 E1 3F` is Ctrl+Shift+F6); `0x01`–`0x05` mouse buttons (4 = back, 5 = forward); `0x30` CPI cycle; `0x31`/`0x32` scroll; `0x33`/`0x34` probably wheel tilt; `0x00` disabled. Bytes after a non-key code are left over and must be ignored. The receiver path is untested. This answers unknowns 2, 3, 6 and 7 below for the wired path: the app reads the table at launch (`readback.py`, `hid_backend.py`).


**Checked:** 15 November 2026, by source inspection only. Nothing here has been confirmed on a real mouse.

## Sources and revisions

| Item | Finding |
| --- | --- |
| Latest Rivalcfg release | **v4.17.0** (PyPI and git tag; repository head `779ea52`, 2026-10-07). Its Aerox 9 page still lists **button mapping as unsupported**. |
| PR #243 | Head is **`4a8f45f1029d68621e264946ffd1101613745ba6`** (3 commits by Zebreus, 2025-03-10), matching the handoff's candidate. Branched from `651337e` (2024-10-29). It is still unmerged. It **merges cleanly onto v4.17.0** in a local test merge (no conflicts in `buttons.py` or `mouse.py`). |
| License | Rivalcfg is under the **WTFPL v2**. Keep its attribution and link to the project and PR author when we pin it. |
| Runtime dependency | `hidapi>=0.14.0` (Python `hid` module, which uses the hidraw or libusb backend depending on the wheel). |

**Decision for now:** no stable release supports Aerox 9 bindings, so the candidate stays PR #243 at `4a8f45f`, rebased (or merged) onto v4.17.0. It is **not** vendored or installed in this repository yet. M3 pins it.

## What the PR does

Changed files: `rivalcfg/devices/aerox9_wireless_wired.py`, `rivalcfg/handlers/buttons/buttons.py`, `rivalcfg/mouse.py`, and docs.

- Adds a `buttons_mapping` setting to the **wired** Aerox 9 profile: HID output report, command `0x2A`, 20 button fields of 5 bytes (100 bytes).
- The 2.4 GHz profile (`aerox9_wireless_wireless.py`, PIDs `0x1858` and WoW `0x1874`) copies every wired setting through `_patch_command`, which ORs `0x40` into the command (so `0x6A`) and adds a 64-byte readback after each packet. So the receiver path **inherits** button mapping without its own code. That readback is a reply to the write, **not** a read of the stored mapping.
- `split_packet_at: [30, 60]` makes the handler return three packets, each prefixed with its index: `[0] + bytes 0–29`, `[1] + bytes 30–59`, `[2] + bytes 60–99`. That is 6, 6 and 8 button fields.
- `mouse.py` now writes each packet in turn, then records the value in Rivalcfg's local settings cache. The cache is not device state.
- Saving to onboard memory is a separate `save_command` (`0x11 0x00`, or `0x51 0x00` over 2.4 GHz). The PR does not change it.

### Field order in the table (from the PR, unverified)

| Offset | PR name | PR default | Printed label (our reading) |
| --- | --- | --- | --- |
| 0, 5, 10 | Button1–3 | button1–3 | Left, right, middle click |
| 15, 20 | Button4–5 | button4–5 | PR comments say "Wheel Left/Right" (tilt?), **unclear** |
| 25 | Button6 | dpi | CPI button |
| 30, 35, 40, 45 | Numpad3, 6, 9, 12 | 3, 6, 9, = | Top row, columns 1–4 |
| 50, 55, 60, 65 | Numpad2, 5, 8, 11 | 2, 5, 8, - | Middle row, columns 1–4 |
| 70, 75, 80, 85 | Numpad1, 4, 7, 10 | 1, 4, 7, 0 | Bottom row, columns 1–4 |
| 90, 95 | ScrollUp, ScrollDown | scrollup, scrolldown | Wheel up/down |

The thumb order is row by row from the top, which matches the printed-label grid in the product spec. The PR author's own comments mark slots 35 (`# dpi?`) and 45 (`# numpad7`) as uncertain, so the hardware run must confirm every label.

Field encoding: keyboard key = `0x51, <HID usage>`, multimedia = `0x61, <code>`, mouse button = `<button id>`, CPI cycle = `0x30`, disabled = `0x00`. Keys come from Rivalcfg's US-QWERTY table, which maps names to HID usages (for example `1` = `0x1E`, `-` = `0x2D`, `=` = `0x2E`, `F1` = `0x3A`). So bindings are physical key usages, as the spec requires.

## Device selection

- `rivalcfg.get_first_mouse()` picks the **first** supported device it finds, so it is not safe when both the receiver and the cable are attached.
- `usbhid.open_device(vid, pid, endpoint)` opens the first hidraw interface with that VID:PID and interface number (3 for the Aerox 9). Receiver (`1038:1858`) and wired (`1038:185a`) have different PIDs, so the adapter can address each one explicitly. Two identical receivers would still be ambiguous, so the adapter must refuse in that case.
- `RIVALCFG_DRY` in the environment silently swaps in a fake HID device. The real adapter must **refuse to run** if it is set, so a real-mode Apply can never report fake success.
- The adapter should call the handler's `process_value` with a dict mapping (`{"buttons": {...}}`) rather than building CLI strings, and should write packets itself through a narrow transport, so tests can record exact bytes and classify failures by packet.

## Unknowns the hardware run must resolve

1. Whether PR #243 writes correctly over the **2.4 GHz receiver** (the PR was reported working by one user; transport not stated).
2. The printed-label to offset mapping for all 12 thumb buttons, especially offsets 35 and 45.
3. The true stock assignments of the non-thumb fields (offsets 15 and 20 above all). Until confirmed, real Apply stays unavailable because a full-table write rewrites them.
4. Whether the button table needs the save command to persist across a power cycle, and whether saving also persists other settings.
5. Whether the 64-byte reply after each 2.4 GHz packet signals success or failure in a usable way.
6. Whether any reliable readback of the stored mapping exists. Assume **none**: the app shows "Last written by this app", never "Current on mouse".
7. Whether `0x00` ("disabled") works as a binding. It stays hidden until tested.
8. Wired behaviour, WoW Edition (`0x1874`) and Bluetooth: untested and out of scope for v0.1.

## Not done in M0

- No device writes, no udev rules, no installation of Rivalcfg.
- The GitHub API was not reachable from this session. The PR's discussion thread and review comments were **not** read, only its code (fetched with git). Read them before pinning in M3.
