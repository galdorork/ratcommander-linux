"""Encoding and the write path, against a simulated mouse that speaks the real protocol."""

import json

import pytest

from aerocommand.backend import ApplyStatus, DeviceRef, Transport
from aerocommand.backups import list_backups
from aerocommand.hid_backend import HidBackend
from aerocommand.profiles import FACTORY_LAYOUT, Binding
from aerocommand.readback import parse_pages
from aerocommand.settings import DeviceSettings
from aerocommand.writer import SAVE, encode_field, settings_reports, table_reports

from test_readback import CAPTURE, SETTINGS_CAPTURE

OWNER = parse_pages(CAPTURE).layout()


def test_field_encoding():
    assert encode_field(Binding.key("KEY_F10")) == bytes([0x51, 0x43, 0, 0, 0])
    assert encode_field(Binding.shortcut(["MOD_LCTRL", "MOD_LSHIFT"], "KEY_F6")) == \
        bytes([0x51, 0xE0, 0xE1, 0x3F, 0])
    assert encode_field(Binding.mouse("BTN_BACK")) == bytes([4, 0, 0, 0, 0])
    assert encode_field(Binding.function("CPI_CYCLE")) == bytes([0x30, 0, 0, 0, 0])
    assert encode_field(Binding.disabled()) == bytes(5)


def test_owner_table_round_trips():
    reports = table_reports(OWNER)
    assert [r[:3] for r in reports] == [b"\x00\x2a\x00", b"\x00\x2a\x01", b"\x00\x2a\x02"]
    assert [len(r) - 3 for r in reports] == [30, 30, 40]
    replies = [b"\xaa" + r[3:] for r in reports]          # what a read would return
    assert parse_pages(replies).layout().bindings == OWNER.bindings
    # Key fields are byte-identical to what the mouse reported.
    assert reports[1][3:8] == CAPTURE[1][1:6]
    assert reports[2][3 + 25:3 + 30] == CAPTURE[2][1 + 25:1 + 30]   # Ctrl+Shift+F6


def test_settings_reports_only_for_set_values():
    assert settings_reports(DeviceSettings()) == []
    out = settings_reports(DeviceSettings(cpi_presets=(400, 3400), polling_hz=500,
                                          dim_timer_s=30, startup_effect="off"), active_cpi=5)
    assert out[0] == bytes([0, 0x2D, 2, 0, 0x04, 0x28])      # active 5 > count -> first
    assert out[1] == bytes([0, 0x2B, 0x01])
    assert out[2] == bytes([0, 0x23, 0x0F, 0x01, 0, 0, 0x30, 0x75, 0x00])
    assert out[3] == bytes([0, 0x27, 0, 0])


class SimMouse:
    """Answers reads from its stored state and applies writes, like the real mouse."""

    def __init__(self, fail_at=None, ignore_polling=False, pid=0x185A):
        self.pages = [bytearray(p[1:]) for p in CAPTURE]
        self.settings = dict(SETTINGS_CAPTURE)
        self.saved = 0
        self.writes = []
        self.raw = []                                    # every packet, as sent
        self.fail_at = fail_at
        self.ignore_polling = ignore_polling
        self.pid = pid
        self.reply = None
        sim = self

        class Dev:
            def open_path(self, path):
                pass

            def write(self, data):
                return sim.handle(bytes(data))

            def read(self, n, timeout_ms=0):
                if timeout_ms <= 20 or sim.reply is None:
                    return []
                r, sim.reply = sim.reply, None
                return list(r)

            def close(self):
                pass

        self.device = Dev

    def enumerate(self, vid, pid):
        return [{"product_id": self.pid, "interface_number": 3, "path": b"1-2:1.3"}]

    def handle(self, data):
        self.raw.append(data)
        cmd = data[1]
        if self.pid == 0x1858 and not cmd & 0x80:
            # Receiver: plain writes are accepted and ignored (seen on the owner's
            # mouse); the 0x40 form is applied and answered with a reply packet.
            if not cmd & 0x40:
                self.writes.append(data)
                return len(data)
            cmd &= ~0x40
            data = bytes([data[0], cmd]) + data[2:]
            self.reply = bytes([cmd | 0x40, 0, 0, 0])
        if cmd & 0x80:                                   # read request
            if cmd == 0xD2:
                self.reply = b"\xd2\x03"
            elif cmd == 0xAA:
                self.reply = b"\xaa" + bytes(self.pages[data[2]])
            else:
                name = {0xAD: "cpi", 0xAB: "polling", 0xA6: "reactive", 0xA3: "dim",
                        0xA7: "startup"}[cmd]
                self.reply = self.settings[name]
            return len(data)
        self.writes.append(data)
        if self.fail_at is not None and len(self.writes) > self.fail_at:
            return -1
        if cmd == 0x2A:
            self.pages[data[2]] = bytearray(data[3:])
        elif cmd == 0x2B and not self.ignore_polling:
            self.settings["polling"] = bytes([0xAB, data[2]])
        elif cmd == 0x11:
            self.saved += 1
        return len(data)


def backend(sim, tmp_path):
    return HidBackend(sim, backup_dir=tmp_path / "backups", sleep=lambda s: None)


def test_apply_backs_up_writes_saves_and_verifies(tmp_path):
    sim = SimMouse()
    b = backend(sim, tmp_path)
    device = b.discover().devices[0]
    wanted = OWNER.with_binding(12, Binding.key("KEY_F8"))
    result = b.apply(device, wanted)
    assert result.status is ApplyStatus.COMPLETED_VERIFIED, result.message
    assert sim.saved == 1 and sim.writes[-1] == SAVE
    assert result.readback.layout.binding(12) == Binding.key("KEY_F8")
    backups = list_backups(tmp_path / "backups")
    assert len(backups) == 1 and backups[0].layout.binding(12) == Binding.disabled()
    raw = json.loads(backups[0].path.read_text())["raw"]
    assert raw["table"][1] == CAPTURE[1].hex()           # raw bytes kept as read


def test_unset_settings_are_not_written(tmp_path):
    sim = SimMouse()
    result = backend(sim, tmp_path).apply(backend(sim, tmp_path).discover().devices[0], OWNER)
    assert result.status is ApplyStatus.COMPLETED_VERIFIED
    assert {w[1] for w in sim.writes} == {0x2A, 0x11}


def test_failure_on_first_packet_is_rejected_after_backup(tmp_path):
    sim = SimMouse(fail_at=0)
    result = backend(sim, tmp_path).apply(backend(sim, tmp_path).discover().devices[0], OWNER)
    assert result.status is ApplyStatus.REJECTED
    assert result.backup


def test_failure_mid_write_is_unknown_and_never_retried(tmp_path):
    sim = SimMouse(fail_at=1)
    result = backend(sim, tmp_path).apply(backend(sim, tmp_path).discover().devices[0], OWNER)
    assert result.status is ApplyStatus.INTERRUPTED_UNKNOWN
    assert len(sim.writes) == 2 and sim.saved == 0


def test_mismatch_is_reported(tmp_path):
    sim = SimMouse(ignore_polling=True)
    b = backend(sim, tmp_path)
    result = b.apply(b.discover().devices[0], OWNER.with_settings(DeviceSettings(polling_hz=500)))
    assert result.status is ApplyStatus.VERIFY_MISMATCH
    assert "polling" in result.message


def test_receiver_writes_use_the_0x40_commands_and_verify(tmp_path):
    sim = SimMouse(pid=0x1858)
    b = backend(sim, tmp_path)
    device = b.discover().devices[0]
    assert device.transport is Transport.RECEIVER
    wanted = OWNER.with_binding(12, Binding.key("KEY_F8")).with_settings(
        DeviceSettings(polling_hz=500))
    result = b.apply(device, wanted)
    assert result.status is ApplyStatus.COMPLETED_VERIFIED, result.message
    assert [w[1] for w in sim.raw if not w[1] & 0x80] == [0x6A, 0x6A, 0x6A, 0x6B, 0x51]
    assert sim.saved == 1 and result.readback.layout.binding(12) == Binding.key("KEY_F8")
    assert len(list_backups(tmp_path / "backups")) == 1


def test_plain_writes_to_the_receiver_would_not_verify(tmp_path):
    # Guards the finding: without the 0x40 form the receiver ignores the change.
    sim = SimMouse(pid=0x1858)
    sim.handle(table_reports(OWNER.with_binding(12, Binding.key("KEY_F8")))[1])
    assert parse_pages([b"\xaa" + bytes(p) for p in sim.pages]).layout().binding(12) == \
        Binding.disabled()


def test_refuses_unplugged_and_no_backup_folder(tmp_path):
    sim = SimMouse()
    b = backend(sim, tmp_path)
    assert b.apply(DeviceRef("gone", "m", Transport.WIRED), OWNER).status is ApplyStatus.REJECTED
    nob = HidBackend(sim, backup_dir=None)
    assert nob.apply(nob.discover().devices[0], OWNER).status is ApplyStatus.REJECTED
    assert sim.writes == []


def test_no_write_when_backup_cannot_be_saved(tmp_path):
    sim = SimMouse()
    blocker = tmp_path / "file"
    blocker.write_text("x")
    b = HidBackend(sim, backup_dir=blocker / "backups", sleep=lambda s: None)
    result = b.apply(b.discover().devices[0], OWNER)
    assert result.status is ApplyStatus.REJECTED and sim.writes == []


def test_full_flow_in_the_window(qtbot, store, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from aerocommand.backups_dialog import BackupsDialog
    from aerocommand.controller import Controller
    from aerocommand.window import MainWindow
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    sim = SimMouse()
    b = HidBackend(sim, backup_dir=store.dir / "backups", sleep=lambda s: None)
    c = Controller(store, b)
    w = MainWindow(c, demo=False)
    qtbot.addWidget(w)
    c.start()
    assert c.draft.binding(12) == Binding.disabled()          # read from the mouse
    c.select_button(12)
    w._set(Binding.key("KEY_F8"))
    assert w.apply_btn.isEnabled()
    w._apply()
    assert "read back" in w.apply_status.text()
    assert c.store.device_profile.layout.binding(12) == Binding.key("KEY_F8")
    # Restore: load the backup into the editor and apply it.
    dlg = BackupsDialog(store.dir / "backups")
    assert len(dlg.backups) == 1
    c.load_layout(dlg.backups[0].layout)
    assert c.draft.binding(12) == Binding.disabled()
    w._apply()
    assert sim.pages[1][15] == 0x00                    # button 12 back to disabled
    assert len(list_backups(store.dir / "backups")) == 2


def test_zone_colour_apply_reports_partial_verification(qtbot, store):
    from aerocommand.controller import Controller
    from aerocommand.window import MainWindow

    sim = SimMouse()
    c = Controller(store, backend(sim, store.dir))
    window = MainWindow(c, demo=False)
    qtbot.addWidget(window)
    c.start()
    c.set_settings(zone_colors=("#112233", "#445566", "#778899"))
    c.apply(acknowledge_full_table=True)
    assert c.last_result.status is ApplyStatus.COMPLETED_PARTIALLY_VERIFIED
    assert "Zone colours were sent" in window.apply_status.text()
    assert c.last_written and c.last_result.readback.layout.settings.zone_colors is None
    assert len([w for w in sim.writes if w[1] == 0x21]) == 3


@pytest.mark.parametrize("pid,flag", [(0x185A, 0), (0x1858, 0x40)])
def test_lighting_tab_writes_only_lighting_and_save(pid, flag, qtbot, store):
    from aerocommand.controller import Controller
    from aerocommand.window import MainWindow

    sim = SimMouse(pid=pid)
    c = Controller(store, backend(sim, store.dir))
    w = MainWindow(c, demo=False)
    qtbot.addWidget(w)
    c.start()
    original = c.draft
    c.set_binding(Binding.key("KEY_F8"), 12)
    c.set_settings(polling_hz=125, cpi_presets=(800,), zone_colors=("#123456",) * 3)
    w.view_tabs.setCurrentIndex(3)
    assert w.apply_btn.text() == "Apply Lighting Only"
    w.apply_btn.click()
    writes = [p[1] for p in sim.raw if not p[1] & 0x80]
    assert writes == [cmd | flag for cmd in (0x21, 0x21, 0x21, 0x26, 0x23, 0x27, 0x11)]
    assert c.last_result.status is ApplyStatus.COMPLETED_PARTIALLY_VERIFIED
    assert c.read_result.layout.bindings == original.bindings
    assert c.read_result.layout.settings == original.settings
    assert c.draft.binding(12) == Binding.key("KEY_F8") and c.draft.settings.polling_hz == 125
    assert list_backups(store.dir / "backups")[0].layout == original
    assert c.last_written is None and not c.full_table_acknowledged
    w.view_tabs.setCurrentIndex(0)
    assert w.apply_btn.text() == "Apply Full Profile"


@pytest.mark.parametrize("pid,flag", [(0x185A, 0), (0x1858, 0x40)])
def test_apply_one_button_preserves_live_bytes(pid, flag, qtbot, store):
    from aerocommand.controller import Controller
    from aerocommand.window import MainWindow

    sim = SimMouse(pid=pid)
    c = Controller(store, backend(sim, store.dir))
    w = MainWindow(c, demo=False)
    qtbot.addWidget(w)
    c.start()
    c.select_button(12)
    c.set_binding(Binding.key("KEY_F8"))
    c.set_binding(Binding.key("KEY_F1"), 3)
    c.set_settings(polling_hz=125)
    # Another editor changed button 3 since launch, including its unused bytes.
    sim.pages[1][:5] = bytes.fromhex("04 99 88 77 66")
    expected = [page[:size] for page, size in zip(sim.pages, (30, 30, 40), strict=True)]
    expected[1][15:20] = encode_field(Binding.key("KEY_F8"))
    w.single_btn.click()
    assert c.last_result.status is ApplyStatus.COMPLETED_VERIFIED
    assert sim.pages == expected
    assert [p[1] for p in sim.raw if not p[1] & 0x80] == [0x2A | flag] * 3 + [0x11 | flag]
    assert c.draft.binding(3) == Binding.key("KEY_F1")
    assert c.last_result.backup and not c.full_table_acknowledged


def test_single_button_left_click_guard_uses_live_mouse(tmp_path):
    sim = SimMouse()
    b = backend(sim, tmp_path)
    draft = OWNER.with_binding(13, Binding.disabled()).with_binding(14, Binding.mouse("BTN_LEFT"))
    result = b.apply(b.discover().devices[0], draft, button=13)
    assert result.status is ApplyStatus.REJECTED
    assert sim.writes == []


def test_full_profile_without_left_click_is_rejected_before_writing(tmp_path):
    sim = SimMouse()
    b = backend(sim, tmp_path)
    result = b.apply(b.discover().devices[0], OWNER.with_binding(13, Binding.disabled()))
    assert result.status is ApplyStatus.REJECTED and sim.writes == []
