import pytest

from aerocommand.profiles import ProfileStore


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-should-not-be-used"))
    return d


@pytest.fixture
def store(config_dir):
    s = ProfileStore(config_dir)
    s.load()
    return s
