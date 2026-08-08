from effdir_editor.version import app_title, get_version


def test_baked_version_is_used_in_title(monkeypatch):
    monkeypatch.delenv("EFFDIR_EDITOR_VERSION", raising=False)
    assert app_title() == f"EFFDIR Editor {get_version()}"
    assert app_title("example.dat") == f"EFFDIR Editor {get_version()} — example.dat"


def test_environment_version_override(monkeypatch):
    monkeypatch.setenv("EFFDIR_EDITOR_VERSION", "v2026.8.1")
    assert get_version() == "2026.8.1"
    assert app_title() == "EFFDIR Editor 2026.8.1"
