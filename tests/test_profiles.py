import json

import pytest

from aerocommand.profiles import (FACTORY_LAYOUT, FACTORY_PROFILE_ID, ActionKind, Binding,
                                  CorruptCatalogError, Layout, ProfileError, ProfileStore,
                                  accessible_name, grid_position)


def test_grid_matches_printed_layout():
    rows = [[None] * 4 for _ in range(3)]
    for label in range(1, 13):
        r, c = grid_position(label)
        rows[r][c] = label
    assert rows == [[3, 6, 9, 12], [2, 5, 8, 11], [1, 4, 7, 10]]
    assert accessible_name(3) == "Thumb 3, top row, first column"
    assert accessible_name(10) == "Thumb 10, bottom row, fourth column"


def test_factory_layout_is_number_row():
    labels = [b.label() for b in FACTORY_LAYOUT.bindings[:12]]
    assert labels == [f"Key {k}" for k in "1234567890-="]


@pytest.mark.parametrize("bad", [
    lambda: Binding(ActionKind.KEY, "KEY_NOPE"),
    lambda: Binding(ActionKind.MOUSE_BUTTON, "KEY_A"),
    lambda: Binding(ActionKind.DEFAULT, "KEY_A"),
    lambda: Binding("macro", "x"),
])
def test_invalid_bindings_rejected(bad):
    with pytest.raises(ProfileError):
        bad()


@pytest.mark.parametrize("count", [0, 11, 13, 21])
def test_layout_needs_twelve_or_twenty(count):
    with pytest.raises(ProfileError):
        Layout(tuple(Binding.default() for _ in range(count)))


def test_twelve_entry_layout_is_padded_and_factory_top_buttons_resolve():
    layout = Layout(tuple(Binding.default() for _ in range(12)))
    assert len(layout.bindings) == 20
    assert layout.resolved().binding(13) == Binding.mouse("BTN_LEFT")
    assert layout.resolved().binding(18) == Binding.function("CPI_CYCLE")
    assert layout.has_left_click()
    assert not layout.with_binding(13, Binding.key("KEY_A")).has_left_click()


def test_layout_round_trip_preserves_order():
    layout = FACTORY_LAYOUT.with_binding(1, Binding.key("KEY_F8")).with_binding(12, Binding.mouse("BTN_BACK"))
    assert Layout.from_json(json.loads(json.dumps(layout.to_json()))).bindings == layout.bindings


def test_resolved_replaces_default_with_factory():
    layout = FACTORY_LAYOUT.with_binding(5, Binding.default())
    assert layout.resolved() == FACTORY_LAYOUT


def test_from_json_rejects_unknown_fields_and_kinds():
    with pytest.raises(ProfileError):
        Binding.from_json({"kind": "key", "code": "KEY_A", "extra": 1})
    with pytest.raises(ProfileError):
        Binding.from_json({"kind": "macro"})
    with pytest.raises(ProfileError):
        Binding.from_json({"kind": "shortcut", "code": "KEY_A"})      # needs a modifier
    assert Binding.from_json({"kind": "disabled"}) == Binding.disabled()


def test_store_create_save_reload(config_dir):
    s = ProfileStore(config_dir)
    s.load()
    p = s.create("Games", FACTORY_LAYOUT.with_binding(1, Binding.key("KEY_F8")))
    s.update(p.id, name="Gaming")
    d = s.duplicate(p.id, "Gaming copy")
    s2 = ProfileStore(config_dir)
    s2.load()
    assert [x.name for x in s2.profiles] == ["Factory thumb layout", "Gaming", "Gaming copy"]
    assert s2.get(d.id).layout == p.layout
    assert d.id != p.id
    data = json.loads((config_dir / "profiles.json").read_text())
    assert data["schema_version"] == 1


def test_factory_profile_is_immutable(store):
    with pytest.raises(ProfileError):
        store.update(FACTORY_PROFILE_ID, name="x")
    with pytest.raises(ProfileError):
        store.delete(FACTORY_PROFILE_ID)


def test_empty_name_rejected(store):
    with pytest.raises(ProfileError):
        store.create("  ", FACTORY_LAYOUT)


@pytest.mark.parametrize("content", [
    "{not json",
    json.dumps({"schema_version": 99, "profiles": []}),
    json.dumps({"schema_version": 1, "profiles": [{"id": "a", "name": "A", "layout": []}]}),
])
def test_corrupt_catalog_reported_and_preserved(config_dir, content):
    config_dir.mkdir(parents=True)
    path = config_dir / "profiles.json"
    path.write_text(content)
    s = ProfileStore(config_dir)
    with pytest.raises(CorruptCatalogError):
        s.load()
    assert path.read_text() == content  # untouched by load
    s.create("New", FACTORY_LAYOUT)
    assert s.corrupt_backup is not None and s.corrupt_backup.read_text() == content
    assert json.loads(path.read_text())["profiles"][0]["name"] == "New"


def test_atomic_save_leaves_no_temp_files(store, config_dir):
    store.create("A", FACTORY_LAYOUT)
    assert sorted(p.name for p in config_dir.iterdir()) == ["profiles.json"]


def test_settings_round_trip_through_a_saved_profile(config_dir):
    from aerocommand.settings import FACTORY_SETTINGS, DeviceSettings, SettingsError
    s = ProfileStore(config_dir)
    s.load()
    settings = DeviceSettings(cpi_presets=(800, 1600), zone_colors=("#112233", "#445566",
                                                                    "#778899"))
    p = s.create("Lit", FACTORY_LAYOUT.with_settings(settings))
    s2 = ProfileStore(config_dir)
    s2.load()
    loaded = s2.get(p.id).layout.settings
    assert loaded == settings and loaded.polling_hz is None
    assert loaded.effective().polling_hz == FACTORY_SETTINGS.polling_hz
    for bad in (dict(cpi_presets=(150,)), dict(cpi_presets=()), dict(polling_hz=300),
                dict(zone_colors=("red", "#000000", "#000000")), dict(dim_timer_s=-1)):
        with pytest.raises(SettingsError):
            DeviceSettings(**bad)
