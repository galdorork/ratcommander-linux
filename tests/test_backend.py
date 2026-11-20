from aerocommand.backend import (DEMO_DEVICE, ApplyStatus, DisabledBackend, DiscoveryProblem,
                                 FakeBackend, FakeScenario)
from aerocommand.profiles import FACTORY_LAYOUT, Binding


def test_fake_state_changes_only_on_apply():
    b = FakeBackend()
    assert b.discover().devices == (DEMO_DEVICE,)
    assert b.device_layout is None and b.apply_calls == 0
    layout = FACTORY_LAYOUT.with_binding(1, Binding.key("KEY_F8"))
    result = b.apply(DEMO_DEVICE, layout)
    assert result.status is ApplyStatus.COMPLETED_UNVERIFIED
    assert b.device_layout == layout and b.applied == [layout]


def test_fake_problem_scenarios():
    assert FakeBackend(FakeScenario.NO_DEVICE).discover().problem is DiscoveryProblem.NO_DEVICE
    assert FakeBackend(FakeScenario.NO_PERMISSION).discover().problem is DiscoveryProblem.NO_PERMISSION


def test_fake_interrupt_makes_state_unknown():
    b = FakeBackend(FakeScenario.INTERRUPT)
    b.device_layout = FACTORY_LAYOUT
    assert b.apply(DEMO_DEVICE, FACTORY_LAYOUT).status is ApplyStatus.INTERRUPTED_UNKNOWN
    assert b.device_layout is None


def test_fake_reject_writes_nothing():
    b = FakeBackend(FakeScenario.REJECT)
    assert b.apply(DEMO_DEVICE, FACTORY_LAYOUT).status is ApplyStatus.REJECTED
    assert b.device_layout is None and b.applied == []


def test_disabled_backend_never_succeeds():
    b = DisabledBackend()
    assert not b.simulated
    assert b.discover().problem is DiscoveryProblem.HARDWARE_DISABLED
    assert b.apply(DEMO_DEVICE, FACTORY_LAYOUT).status is ApplyStatus.REJECTED
