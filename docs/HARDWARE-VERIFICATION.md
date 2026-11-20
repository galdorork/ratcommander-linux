# Hardware verification — Aerox 9 Wireless

This is an owner-run checklist on the Linux machine that has the actual mouse. An offscreen GUI test, mock transport or successful CLI exit cannot establish physical mapping or persistence.

## Before a write

1. Record the Linux distro, session type, exact model, connection mode and backend revision. Record firmware only if a trusted tool exposes it.
2. If you have a custom GG layout you want to keep, document it first. A screenshot or profile record gives you a reference for manual restoration. Do not assume this tool can read and back up what is on the mouse.
3. Pause any host remapper for the Aerox 9 so the raw button events are observable. Keep a keyboard or spare mouse available. Use a key-event viewer such as `evtest` on the relevant Aerox keyboard interface, or use a suitable desktop event viewer. If the mouse exposes more than one input interface, identify which one emits the thumb keys.
4. Start with the 2.4 GHz receiver only. Run `lsusb -d 1038:` to confirm the visible USB transport. The standard device IDs are `1038:1858` for the receiver and `1038:185a` for wired. IDs alone do not prove there is a reachable mouse behind the receiver or identify the interface the backend must open. See the [Rivalcfg device list](https://rivalcfg.flozz.org/devices.html).
5. Verify the intended target and default non-thumb controls before applying a full table. If the backend cannot select the right target, or if the stock control map is not established, stop the write test and record why.

## Run for each transport you intend to support

| Check | Procedure and pass condition |
| --- | --- |
| Discovery | The app identifies the correct model and transport. An absent mouse, sleeping/unreachable receiver pairing, or denied permissions does not produce a successful write status. |
| One-button probe | On a known factory thumb layout, map only printed thumb button **1** to an unambiguous supported key such as `F8`. Press all 12 thumb buttons and compare against baseline. Only button 1 changes. Main clicks, wheel and CPI controls retain their verified stock behavior. |
| Full grid | Apply a temporary layout of distinct supported key usages, such as `F1`–`F12` if available. Record the observed usage for every printed label. Exercise all columns and packet boundaries. Confirm press and release for each button. |
| Persistence | Close the configurator, switch the mouse off and back on, and reconnect the same transport. With no remapper or configurator running, confirm the full mapping again. |
| Profile switching | Apply a different saved profile, then reapply the first. Each explicit apply produces the intended events. Loading or saving a profile locally never changes observed events. |
| Restore | Load **Factory thumb layout** and explicitly apply it. Verify the twelve factory number-row usages, primary controls and previously noted CPI/polling/lighting settings. Do not use a general device reset as part of the test. |
| Disconnection and recovery | First simulate mid-write failure in tests. On real hardware, check disconnect before Apply and clean reconnect. If a real interruption occurs, verify the app reports unknown state, keeps the draft, and permits a deliberate reapply without silently retrying. |
| Wired | Unplug the receiver before plugging in the mouse by cable, then repeat this checklist. Later check that having both paths attached cannot cause a write to the wrong target. An untested or failing path stays disabled. |

## Record results

- Date / tester:
- Distro / kernel / Wayland or X11:
- Model / firmware if available:
- Backend release or commit:
- 2.4 GHz result, including observed button 1–12 events:
- Wired result, including observed button 1–12 events:
- Behavior after power cycle:
- Stock restoration and unrelated settings:
- Readback available, or observed behavior only:
- Any blockers and the next test:
