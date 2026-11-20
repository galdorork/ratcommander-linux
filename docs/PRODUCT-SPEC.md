# Product spec — Aerox 9 Linux Configurator

**Proposed first release:** v0.1  
**Audience:** Linux desktop users who already own a standard SteelSeries Aerox 9 Wireless  
**Primary outcome:** Edit the 12 thumb buttons on Linux and persist one layout on the mouse, with no remapping process running afterward.

## Approach

Build a small native desktop app in Python and PySide6 Qt Widgets. Reuse Rivalcfg behind an adapter. Its v4.17.0 Aerox 9 documentation lists button mapping as unsupported, while PR #243 contains an experimental implementation that sends the button table in three packets. One user reported using the fork successfully, but that is not verification on our mouse. Prefer a supported upstream release if one becomes available.

We considered a frontend for Input Remapper, which would be useful for app-specific shortcuts but would keep the bindings on the Linux host. We also considered a fresh HID implementation, which would duplicate work already done in Rivalcfg. A Rivalcfg-backed GUI best matches the onboard goal. PySide6 is a proposed default for a standalone app. Rivalcfg’s maintainer has discussed a GTK 4 frontend of their own, so revisit toolkit and integration choices if upstream collaboration becomes the goal.

## First release

| Area | v0.1 behavior |
| --- | --- |
| Editor | Click a button in the physical 12-button grid, then choose a supported binding. Provide keyboard navigation, visible focus, and accessible labels such as “Thumb 3, top row, first column.” |
| Bindings | Default, single keyboard key, and supported mouse button. Only show actions verified by the chosen backend. Add “Disabled” only after validating it. Treat keys as physical key usages and document how the host keyboard layout affects displayed characters. |
| Profiles | Create, rename, duplicate, save and load named profiles on disk. Keep a built-in, immutable **Factory thumb layout**. Loading it populates the editor and does not write until **Apply to mouse**. |
| Apply | Write the displayed layout to the selected device only. Keep main clicks, scroll controls and CPI button at their verified factory assignments in any full-table write. Do not change CPI presets, polling, lighting or other device settings. |
| Target | Standard Aerox 9 Wireless. Prove the 2.4 GHz dongle path first. Offer wired Apply only after it independently passes hardware checks. No configuration over Bluetooth, no promise about how an applied layout behaves in Bluetooth mode, and no support claim for the WoW Edition without its own testing. |
| Offline | Open and edit saved profiles without a mouse. Explicit **Demo mode** exercises the workflow with a simulated device and clearly says that nothing is written to hardware. |
| Later | DPI, lighting, polling, battery, additional models, automatic app switching, macros, firmware updates, and distro packaging are out of scope. v0.1 needs a documented local install, not a Flatpak or AppImage. |

### Physical layout

The numbers here are the labels printed on the mouse. They are **not** USB command slot numbers.

| Row | Column 1 | Column 2 | Column 3 | Column 4 |
| --- | --- | --- | --- | --- |
| Top | 3 | 6 | 9 | 12 |
| Middle | 2 | 5 | 8 | 11 |
| Bottom | 1 | 4 | 7 | 10 |

The factory thumb sequence is the standard top number row: physical usages for `1` through `0`, then `-` and `=` in US-QWERTY notation. Verify the printed-label-to-backend-slot mapping on actual hardware. Use an original diagram or plain grid, with no SteelSeries logo or copied GG artwork.

### Screen and state

Use one window. Put model, transport and connection state at the top. Place the 12-button grid next to the selected button’s binding control. Make **Save profile** and **Apply to mouse** distinct. Preserve the system theme and do not use color alone for status.

- **No device / no permission / unsupported / ambiguous target:** keep editing available, disable Apply, and give a specific next step. Multiple usable devices require explicit selection if the backend can address them individually. Otherwise show how to remove the ambiguity.
- **Draft modified:** mark unsaved profile edits. Saving locally does not mean those edits are on the mouse. Applying an unsaved draft writes exactly what is shown and does not silently save a named profile.
- **First full-table write:** explain before applying that any prior custom bindings outside the 12 thumb buttons may be replaced by stock assignments. If the stock assignments cannot be verified, leave real Apply unavailable. A factory thumb layout is not a backup of previous GG settings.
- **Writing:** freeze the device selection and serialize writes. Keep the UI responsive. Show progress and disable repeated clicks while the operation is in flight.
- **Backend reported success:** use “Write completed” and, if no readback is supported, “Device settings were not read back.” A local snapshot is “Last written by this app” and is never shown as “Current on mouse.” Reconnecting or using another configurator can invalidate any assumption that it is still current.
- **Interrupted write:** show “Device state unknown.” Preserve the draft and previous successful snapshot, do not auto-retry, and offer deliberate reapply or application of the factory thumb layout once the device is reachable. If a write completed but the local snapshot could not be saved, report the two outcomes separately.

## Sources and confidence

- [SteelSeries Aerox 9 manual, page 9](https://downloads.steelseriescdn.com/guides/MO_aerox_9_wl_pig_web.pdf) — physical keypad and default number-row mapping.
- [SteelSeries onboard memory support](https://support.steelseries.com/hc/en-us/articles/15250138269837-Aerox-Mice-Onboard-Memory) — basic key and mouse bindings can persist. Software macros do not.
- [Rivalcfg Aerox 9 documentation](https://flozz.github.io/rivalcfg/devices/aerox9_wireless.html) and [PR #243](https://github.com/flozz/rivalcfg/pull/243) — released feature gap and experimental three-packet write. Treat reliable readback, persistence behavior and mode parity as unverified until tested.
- [Rivalcfg maintainer roadmap](https://rivalcfg.flozz.org/news/10-years-of-rivalcfg-new-web-site-and-a-logo/) — future GTK frontend and the limits of settings readback. Do not infer current device settings from local cache.
- [Qt for Python](https://doc.qt.io/qtforpython-6/) — toolkit documentation and licensing. Review dependency and asset notices before distributing builds.
