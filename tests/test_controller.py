import threading

import pytest

from aerocommand.backend import ApplyStatus, DisabledBackend, FakeBackend, FakeScenario
from aerocommand.controller import (ApplyRequest, Controller, DeviceState, ThreadRunner)
from aerocommand.profiles import (FACTORY_LAYOUT, FACTORY_PROFILE_ID, Binding, ProfileError,
                                  ProfileStore)


def make(store, scenario=FakeScenario.SUCCESS, **kw):
    backend = FakeBackend(scenario, **kw)
    c = Controller(store, backend)
    c.start()
    return c, backend


def test_local_actions_never_write(store):
    c, b = make(store)
    c.select_button(1)
    c.set_binding(Binding.key("KEY_F8"))
    c.save_as("Mine")
    c.set_binding(Binding.key("KEY_F9"), label=2)
    c.save_profile()
    c.rename_profile("Mine 2")
    c.duplicate_profile("Copy")
    c.load_factory_layout()
    c.refresh_devices()
    c.refresh_devices()
    c.load_profile(store.profiles[1].id)
    assert b.apply_calls == 0 and b.device_layout is None


def test_first_apply_needs_full_table_acknowledgement(store):
    c, b = make(store)
    assert c.apply() is ApplyRequest.NEEDS_ACKNOWLEDGEMENT
    assert b.apply_calls == 0
    assert c.apply(acknowledge_full_table=True) is ApplyRequest.STARTED
    assert c.apply() is ApplyRequest.STARTED  # acknowledged once per session
    assert b.apply_calls == 2


def test_apply_writes_exactly_what_is_shown_without_saving(store, config_dir):
    c, b = make(store)
    c.set_binding(Binding.key("KEY_F8"), label=1)
    c.set_binding(Binding.default(), label=2)
    c.apply(acknowledge_full_table=True)
    expected = FACTORY_LAYOUT.with_binding(1, Binding.key("KEY_F8"))
    assert b.device_layout == expected
    assert c.device_state is DeviceState.WRITE_COMPLETED
    assert c.last_result.status is ApplyStatus.COMPLETED_UNVERIFIED
    assert c.dirty  # applying did not save a profile
    assert not (config_dir / "profiles.json").exists()
    assert (config_dir / "last-written.json").exists()


def test_interruption_preserves_draft_and_does_not_retry(store):
    c, b = make(store, FakeScenario.INTERRUPT)
    c.set_binding(Binding.key("KEY_F8"), label=1)
    draft = c.draft
    c.apply(acknowledge_full_table=True)
    assert b.apply_calls == 1
    assert c.device_state is DeviceState.STATE_UNKNOWN
    assert c.draft == draft and not c.writing
    assert c.last_written is None


def test_snapshot_failure_is_reported_separately_and_not_retried(store, config_dir):
    c, b = make(store)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "last-written.json").mkdir()  # makes the snapshot write fail
    c.apply(acknowledge_full_table=True)
    assert b.apply_calls == 1
    assert c.device_state is DeviceState.WRITE_COMPLETED
    assert "local record" in c.notice


@pytest.mark.parametrize("scenario", [FakeScenario.NO_DEVICE, FakeScenario.NO_PERMISSION])
def test_apply_unavailable_without_device(store, scenario):
    c, b = make(store, scenario)
    assert c.apply_blocker()
    assert c.apply(acknowledge_full_table=True) is ApplyRequest.UNAVAILABLE
    assert b.apply_calls == 0


def test_disabled_backend_blocks_apply(store):
    c = Controller(store, DisabledBackend())
    c.start()
    assert "not enabled" in c.apply_blocker()
    assert c.apply(acknowledge_full_table=True) is ApplyRequest.UNAVAILABLE


def test_factory_profile_cannot_be_saved_over(store):
    c, _ = make(store)
    c.set_binding(Binding.key("KEY_F8"))
    with pytest.raises(ValueError):
        c.save_profile()
    assert store.get(FACTORY_PROFILE_ID).layout == FACTORY_LAYOUT


def test_threaded_apply_is_serialized_and_locks_editing(store):
    gate = threading.Event()
    pending = []
    runner = ThreadRunner(pending.append)  # completions wait until we run them
    backend = FakeBackend(gate=gate)
    c = Controller(store, backend, runner)
    c.start()
    shown = c.draft.with_binding(1, Binding.key("KEY_F8"))
    c.set_binding(Binding.key("KEY_F8"), label=1)
    assert c.apply(acknowledge_full_table=True) is ApplyRequest.STARTED
    assert c.apply() is ApplyRequest.BUSY
    assert c.apply() is ApplyRequest.BUSY
    with pytest.raises(RuntimeError):
        c.set_binding(Binding.key("KEY_F9"))
    gate.set()
    runner.shutdown()
    for fn in pending:
        fn()
    assert backend.apply_calls == 1
    assert backend.device_layout == shown
    assert not c.writing


def test_corrupt_catalog_reported_on_start(config_dir):
    config_dir.mkdir(parents=True)
    (config_dir / "profiles.json").write_text("{oops")
    c = Controller(ProfileStore(config_dir), FakeBackend())
    c.start()
    assert "could not be read" in c.notice
    assert (config_dir / "profiles.json").read_text() == "{oops"


def test_launch_reads_the_mouse_into_an_on_mouse_profile(store):
    from aerocommand.backend import DEMO_DEVICE_LAYOUT
    from aerocommand.profiles import DEVICE_PROFILE_ID
    backend = FakeBackend()
    backend.readable = True
    c = Controller(store, backend)
    c.start()
    assert backend.read_calls == 1
    assert c.profile_id == DEVICE_PROFILE_ID
    assert c.draft == DEMO_DEVICE_LAYOUT and not c.dirty
    assert store.profiles[0].name.startswith("On the mouse")
    assert backend.apply_calls == 0
    with pytest.raises(ProfileError):
        store.update(DEVICE_PROFILE_ID, name="x")


def test_read_does_not_replace_an_edit_in_progress(store):
    from aerocommand.profiles import FACTORY_PROFILE_ID
    backend = FakeBackend()
    c = Controller(store, backend)
    c.start()
    c.set_binding(Binding.key("KEY_A"), 1)
    backend.readable = True
    c.refresh_devices()
    assert c.profile_id == FACTORY_PROFILE_ID and c.draft.binding(1) == Binding.key("KEY_A")
    assert store.device_profile is not None


@pytest.mark.parametrize("edited", [False, True])
def test_refresh_updates_baseline_and_preserves_edits(store, edited):
    backend = FakeBackend(readable=True)
    c = Controller(store, backend)
    c.start()
    if edited:
        c.set_binding(Binding.key("KEY_F7"), 12)
    before = c.draft
    backend.device_layout = before.with_binding(12, Binding.key("KEY_F9"))
    c.refresh_devices()
    assert store.device_profile.layout == backend.device_layout
    assert c.draft == (before if edited else backend.device_layout)
    assert c.dirty == edited


def test_switch_device_while_read_is_pending(store, monkeypatch):
    from aerocommand.backend import DeviceRef, Discovery, ReadResult, Transport

    wired = DeviceRef("usb", "Aerox 9", Transport.WIRED)
    receiver = DeviceRef("radio", "Aerox 9", Transport.RECEIVER)
    layouts = {wired: FACTORY_LAYOUT.with_binding(12, Binding.key("KEY_F8")),
               receiver: FACTORY_LAYOUT.with_binding(12, Binding.key("KEY_F9"))}
    backend = FakeBackend(readable=True)
    monkeypatch.setattr(backend, "discover", lambda: Discovery(devices=(wired, receiver)))
    monkeypatch.setattr(backend, "read_layout", lambda d: ReadResult(layouts[d]))
    pending = []
    c = Controller(store, backend, lambda job, done: pending.append(lambda: done(job())))
    c.start()
    c.select_device(wired.token)
    c.select_device(receiver.token)
    pending.pop(0)()
    assert c.read_result is None and store.device_profile is None
    assert c.reading and c.apply() is ApplyRequest.UNAVAILABLE
    pending.pop(0)()
    assert c.draft == layouts[receiver] and not c.dirty
    pending.pop(0)()  # Receiver battery query follows the layout read.
    assert not pending and backend.apply_calls == 0
