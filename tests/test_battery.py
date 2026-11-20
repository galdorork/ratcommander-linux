import pytest

from aerocommand.backend import DeviceRef, Discovery, FakeBackend, Transport
from aerocommand.controller import Controller
from aerocommand.hid_backend import HidBackend
from aerocommand.window import MainWindow

RECEIVER = DeviceRef("receiver", "Aerox 9 Wireless", Transport.RECEIVER)


@pytest.mark.parametrize("reply, expected", [
    (b"\xd2\x01", 0), (b"\xd2\x03", 10), (b"\xd2\x95", 100),
    (b"", None), (b"\xd2", None), (b"\xd2\x00", None),
    (b"\xd2\xff", None), (b"\xaa\x03", None),
])
def test_receiver_battery_query(reply, expected):
    class Port:
        def open_path(self, path):
            assert path == b"receiver"

        def write(self, report):
            assert report == b"\x00\xd2"
            return len(report)

        def read(self, size, timeout_ms):
            assert timeout_ms > 0
            return reply

        def close(self):
            pass

    class Hid:
        device = Port

    assert HidBackend(Hid()).read_battery(RECEIVER) == expected


def test_receiver_status_tracks_sleep_wake_and_selection(qtbot, store):
    levels = iter([10, None, 0])

    class ReceiverBackend(FakeBackend):
        def discover(self):
            return Discovery(devices=(RECEIVER,))

        def read_battery(self, device):
            return next(levels)

    controller = Controller(store, ReceiverBackend())
    window = MainWindow(controller, demo=False)
    qtbot.addWidget(window)
    controller.start()
    assert "Battery 10%" in window.device_status.text()
    window.battery_timer.timeout.emit()
    assert "Battery unavailable" in window.device_status.text()
    window.battery_timer.timeout.emit()
    assert "Battery 0%" in window.device_status.text()
    controller.select_device(None)
    assert "Battery" not in window.device_status.text()
    assert not window.battery_timer.isActive()
