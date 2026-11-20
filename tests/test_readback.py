"""Readback decoding, using the bytes captured from the owner's mouse on 2026-11-18."""

import pytest

from aerocommand.backend import DeviceRef, Transport
from aerocommand.hid_backend import HidBackend, read_table
from aerocommand.profiles import Binding
from aerocommand.readback import ReadbackError, parse_pages, read_request

H = bytes.fromhex
JUNK = H("0b0000009a4600200c000000cd46002084340020245a002084340020")
CAPTURE = [
    H("aa 01 00 00 00 00 02 00 00 00 00 03 00 00 00 00 33 00 00 00 00 34 00 00 00 00 30 00 00 00 00 00 00 00 00 00") + JUNK,
    H("aa 51 42 00 00 00 05 b6 00 00 00 04 26 00 00 00 00 2e 00 00 00 51 3f 00 00 00 51 22 00 00 00 00 00 00 00 00") + JUNK,
    H("aa 51 25 00 00 00 51 2d 00 00 00 51 43 00 00 00 51 40 00 00 00 00 24 00 00 00 51 e0 e1 3f 00 31 00 00 00 00 32 00 00 00 00"),
]


def test_owner_layout_decodes():
    layout = parse_pages(CAPTURE).thumb_layout()
    expected = {
        1: Binding.key("KEY_F10"), 2: Binding.key("KEY_F6"), 3: Binding.key("KEY_F9"),
        4: Binding.key("KEY_F7"), 5: Binding.key("KEY_5"), 6: Binding.mouse("BTN_FORWARD"),
        7: Binding.disabled(), 8: Binding.key("KEY_8"), 9: Binding.mouse("BTN_BACK"),
        10: Binding.shortcut(["MOD_LCTRL", "MOD_LSHIFT"], "KEY_F6"),
        11: Binding.key("KEY_MINUS"), 12: Binding.disabled(),
    }
    assert {n: layout.binding(n) for n in range(1, 13)} == expected
    assert layout.binding(10).label() == "Ctrl+Shift+F6"


def test_top_buttons_decode():
    layout = parse_pages(CAPTURE).layout()
    assert layout.binding(13) == Binding.mouse("BTN_LEFT")
    assert layout.binding(15) == Binding.mouse("BTN_MIDDLE")
    assert layout.binding(16) == Binding.function("TILT_LEFT")
    assert layout.binding(18) == Binding.function("CPI_CYCLE")
    assert layout.binding(20) == Binding.function("SCROLL_DOWN")
    assert layout.resolved() == layout.resolved().resolved()


def test_other_buttons_are_described():
    other = parse_pages(CAPTURE).other_buttons()
    assert other["Left button"] == "Left click"
    assert other["CPI button"] == "CPI cycle"
    assert other["Scroll down"] == "Scroll down"


def test_bad_replies_are_rejected():
    with pytest.raises(ReadbackError):
        parse_pages(CAPTURE[:2])
    with pytest.raises(ReadbackError):
        parse_pages([CAPTURE[0], b"\x2a" + CAPTURE[1][1:], CAPTURE[2]])
    with pytest.raises(ReadbackError):
        parse_pages([CAPTURE[0], CAPTURE[1], CAPTURE[2][:20]])


def test_unknown_thumb_code_is_not_guessed():
    odd = bytearray(CAPTURE[1])
    odd[1] = 0x99
    with pytest.raises(ReadbackError, match="button 3 "):
        parse_pages([CAPTURE[0], bytes(odd), CAPTURE[2]]).thumb_layout()


def test_read_table_sends_only_read_requests():
    sent = []
    pages = iter(CAPTURE)
    replies = read_table(sent.append, lambda: list(next(pages)), drain=lambda: [])
    assert sent == [read_request(0), read_request(1), read_request(2)]
    assert all(p[1] == 0xAA for p in sent)
    assert replies == CAPTURE


class FakeHid:
    def __init__(self, replies, open_error=False, pid=0x185A):
        self.replies, self.open_error, self.pid = list(replies), open_error, pid
        self.sent = []
        outer = self

        class Dev:
            def open_path(self, path):
                if outer.open_error:
                    raise OSError("open failed")

            def write(self, data):
                outer.sent.append(bytes(data))
                return len(data)

            def read(self, n, timeout_ms=0):
                if timeout_ms <= 20 or not outer.replies:
                    return []
                return list(outer.replies.pop(0))

            def close(self):
                pass

        self.device = Dev

    def enumerate(self, vid, pid):
        return [{"product_id": self.pid, "interface_number": i, "path": f"1-2:1.{i}".encode()}
                for i in range(6)]


def test_hid_backend_reads_wired_mouse():
    fake = FakeHid(CAPTURE)
    backend = HidBackend(fake)
    disc = backend.discover()
    assert [d.transport for d in disc.devices] == [Transport.WIRED]
    result = backend.read_layout(disc.devices[0])
    assert result.layout.binding(1) == Binding.key("KEY_F10")
    assert all(s[1] & 0x80 for s in fake.sent)          # only read requests


def test_hid_backend_permission_and_receiver():
    assert HidBackend(FakeHid([], open_error=True)).discover().problem.value == "no_permission"
    fake = FakeHid(CAPTURE, pid=0x1858)
    backend = HidBackend(fake)
    receiver = backend.discover().devices[0]
    assert receiver.transport is Transport.RECEIVER
    result = backend.read_layout(receiver)
    assert result.layout.binding(1) == Binding.key("KEY_F10")
    assert all(s[1] & 0x80 for s in fake.sent)          # plain read requests only


def test_hid_backend_never_writes_the_table():
    fake = FakeHid(CAPTURE)
    backend = HidBackend(fake)
    device = backend.discover().devices[0]
    result = backend.apply(device, parse_pages(CAPTURE).thumb_layout())
    assert result.status.value == "rejected"
    assert fake.sent == []


SETTINGS_CAPTURE = {   # owner's mouse, 2026-11-18 (trailing bytes are stale buffer data)
    "cpi": H("ad 05 04 04 09 0d 1b 28 00 00 00 51 43"),
    "polling": H("ab 00 04 04 09 0d 1b 28 00"),
    "reactive": H("a6 01 00 ff ff ff 1b 28 00"),
    "dim": H("a3 0f 01 01 00 30 75 00 00"),
    "startup": H("a7 01 00 01 00 30 75 00 00"),
}


def test_settings_decode():
    from aerocommand.readback import parse_settings
    s, active = parse_settings(SETTINGS_CAPTURE)
    assert s.cpi_presets == (400, 800, 1200, 2400, 3400)
    assert active == 5
    assert s.polling_hz == 1000
    assert s.reactive_color == "#ffffff"
    assert s.dim_timer_s == 30
    assert s.startup_effect == "rainbow"
    assert s.zone_colors is None            # the mouse doesn't report these


def test_settings_bad_replies_stay_unset():
    from aerocommand.readback import parse_settings
    s, active = parse_settings({"cpi": H("ad 09 00"), "polling": H("ab 07"), "dim": b""})
    assert s.is_empty() and active is None


def test_hid_backend_reads_settings_too():
    from aerocommand.readback import SETTINGS_REQUESTS
    fake = FakeHid(CAPTURE + [SETTINGS_CAPTURE[n] for n in SETTINGS_REQUESTS])
    backend = HidBackend(fake)
    result = backend.read_layout(backend.discover().devices[0])
    assert result.layout.settings.cpi_presets[-1] == 3400
    assert result.other_buttons["Active CPI preset"] == "5"
    assert [s[1] for s in fake.sent] == [0xAA] * 3 + list(SETTINGS_REQUESTS.values())
