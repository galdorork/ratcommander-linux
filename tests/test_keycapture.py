from aerocommand.keycapture import KEY_GROUPS, is_modifier, key_from_scan_code
from aerocommand.profiles import KEYS


def test_physical_codes():
    assert key_from_scan_code(30 + 8) == "KEY_A"      # same position on AZERTY (Q legend)
    assert key_from_scan_code(2 + 8) == "KEY_1"
    assert key_from_scan_code(11 + 8) == "KEY_0"
    assert key_from_scan_code(88 + 8) == "KEY_F12"
    assert key_from_scan_code(1 + 8) == "KEY_ESCAPE"
    assert key_from_scan_code(999) is None


def test_modifiers_are_not_mappings():
    for code in (29, 42, 54, 56, 97, 100, 125, 126):
        assert is_modifier(code + 8)
        assert key_from_scan_code(code + 8) is None


def test_every_key_is_reachable_by_capture_and_menu():
    captured = {key_from_scan_code(c) for c in range(8, 300)} - {None}
    assert captured == set(KEYS)
    assert sorted(k for _, ks in KEY_GROUPS for k in ks) == sorted(KEYS)
