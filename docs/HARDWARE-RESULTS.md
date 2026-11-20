# Hardware results

## 2026-11-18, owner's mouse, USB cable

- **Tester:** owner, with the app driven over the owner's session
- **System:** CachyOS, kernel 7.3.4, KDE Plasma 6.8.3 on Wayland
- **Model / transport:** 1038:185a (wired), config interface 3. Firmware not read.
- **Backend:** own read/write code in `readback.py`, `writer.py`, `hid_backend.py`, using the table format from Rivalcfg PR #243 (`4a8f45f`) and Rivalcfg v4.17.0's setting commands, over PyPI `hidapi` 0.15 (libusb backend)
- **Access:** `packaging/70-aerocommand.rules` (uaccess, 1038:1858 and 1038:185a only)

| Check | Result |
| --- | --- |
| Discovery | Wired mouse found; permission errors reported before the rule was installed. |
| Readback | `0xAA` + page 0/1/2 returns the full 20-slot button table. CPI (`0xAD`), polling (`0xAB`), reactive colour (`0xA6`), dim timer (`0xA3`) and startup effect (`0xA7`) also answer. Zone colours (`0xA1`) do not. |
| Label → slot mapping | Matches PR #243's order (3, 6, 9, 12, 2, 5, 8, 11, 1, 4, 7, 10), checked against an evtest baseline of the owner's custom layout. |
| Unchanged rewrite | Buttons, then settings, rewritten as read: read-back identical. |
| One-button probe | Button 12 set to F8: read-back F8 and evtest shows `KEY_F8`; all other buttons unchanged. |
| Persistence | After the save command and an unplug/replug, button 12 still reads F8. |
| Restore | Loading the pre-probe backup and applying it restored the owner's layout, verified by read-back. |
| Shortcuts / disabled | Read correctly from a GG-made layout (Ctrl+Shift+F6, two disabled buttons); written back unchanged. |

**Found during testing:** the save command (`0x11 0x00`) sends a reply that must be drained before reading back.

**Not tested:** 2.4 GHz receiver (blocked in the app), Bluetooth, zone-colour writes (no read-back), WoW Edition, other distros or X11.

## 2026-11-18, owner's mouse, 2.4 GHz receiver

- **Tester:** owner, with the app driven over the owner's session
- **System:** Manjaro, kernel 7.2.9, KDE Plasma (main PC; ASUS TUF B650M-PLUS, no onboard Bluetooth)
- **Model / transport:** 1038:1858 (receiver), config interface 3. Firmware not read.
- **Backend:** as above, using the receiver form of the write commands
- **Access:** `packaging/70-aerocommand.rules`

| Check | Result |
| --- | --- |
| Discovery | Receiver found on interface 3 once the udev rule was installed. |
| Readback | The plain read commands (`0xAA` pages, `0xAD`, `0xAB`, `0xA6`, `0xA3`, `0xA7`) answer exactly as over the cable. `0xEA` also returns the table. |
| Plain writes | `0x2A` + `0x11` are accepted (hidapi reports bytes written) but **ignored**: button 12 → F8 read back as disabled. |
| Receiver writes | With 0x40 added to the command byte (`0x6A` table, `0x6B` polling, `0x51` save, as in Rivalcfg's `_patch_command`), the mouse answers each packet (`6a 00 …`, `51 00 …`) and the change takes effect. |
| One-button probe | Button 12 set to F8: read-back F8, and input events show `KEY_F8` (code 66) on each press. |
| Unchanged rewrite | Buttons and settings through the app's `apply()`: read-back identical. |
| Settings | Polling 1000 → 500 Hz: read-back 500. |
| Persistence | After switching the mouse off and on: button 12 still F8, but **polling back to 1000 Hz**. The mouse does not appear to keep the polling rate across power cycles. |
| Restore | Button 12 back to disabled and polling back to 1000 Hz, verified by read-back. |

**Not tested:** zone colours and other settings over the receiver, having both receiver and cable attached, Bluetooth (no adapter on this PC; on the laptop the link drops every 30 s, see below).

## Bluetooth, laptop

The mouse pairs, but the link drops every 30 s. `btmon` shows the laptop's Realtek controller (`0bda:4852`) delivering the mouse's first ATT packet (Exchange MTU) before the connection-complete event; the kernel drops it ("ACL packet for unknown connection handle"), the mouse waits for an answer, and the 30 s ATT timeout ends the connection. Same result on the LTS kernel. Over Bluetooth the mouse exposes a vendor report (id 4, 64 bytes in and out), not yet probed.

## 2026-11-20, battery over the 2.4 GHz receiver

With the receiver connected, the battery query returned `d2 03 …`. RatCommander displayed **Battery 10%** beside the connection status, matching Rivalcfg 4.17.0. The physical off/on check was skipped. Automated tests cover a missing reply followed by a fresh reading.
