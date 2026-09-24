"""Pure-logic tests for settings.py: defaults merge, language mapping, process parsing."""
import json

import settings


def test_defaults_has_all_expected_keys():
    expected = {
        "autostart", "dot_x", "dot_y", "llm_cleanup", "llm_api_key", "llm_model",
        "show_dot", "hotkey", "mouse_button", "model", "language",
        "game_guard", "game_processes",
    }
    assert expected.issubset(settings.DEFAULTS.keys())


def test_load_merges_old_settings_file_with_new_defaults(tmp_path, monkeypatch):
    """An old settings.json missing new keys must still load with the new
    defaults filled in — this is what lets a v1.0 upgrade not break someone's
    saved preferences."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old_data = {"autostart": True, "llm_cleanup": True}
    settings_dir = tmp_path / settings.APP_NAME
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(json.dumps(old_data), encoding="utf-8")

    loaded = settings.load()

    # Old values are preserved...
    assert loaded["autostart"] is True
    assert loaded["llm_cleanup"] is True
    # ...and new keys fall back to their defaults.
    assert loaded["hotkey"] == settings.DEFAULTS["hotkey"]
    assert loaded["mouse_button"] is True
    assert loaded["model"] == "small"
    assert loaded["game_processes"] == settings.DEFAULTS["game_processes"]


def test_load_returns_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    loaded = settings.load()
    assert loaded == settings.DEFAULTS


def test_load_recovers_from_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings_dir = tmp_path / settings.APP_NAME
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text("{not valid json", encoding="utf-8")

    loaded = settings.load()

    assert loaded == settings.DEFAULTS


def test_save_then_load_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data = dict(settings.DEFAULTS)
    data["hotkey"] = "<ctrl>+<shift>+m"

    assert settings.save(data) is True
    assert settings.load()["hotkey"] == "<ctrl>+<shift>+m"


def test_language_to_whisper_auto_means_none():
    assert settings.language_to_whisper("auto") is None
    assert settings.language_to_whisper("") is None
    assert settings.language_to_whisper("  ") is None


def test_language_to_whisper_passes_through_code():
    assert settings.language_to_whisper("en") == "en"
    assert settings.language_to_whisper("ES") == "es"
    assert settings.language_to_whisper(" fr ") == "fr"


def test_parse_game_processes_splits_and_normalizes():
    raw = "FortniteClient-Win64-Shipping.exe,  fortnitelauncher.exe , ,  valorant.exe"
    assert settings.parse_game_processes(raw) == [
        "fortniteclient-win64-shipping.exe",
        "fortnitelauncher.exe",
        "valorant.exe",
    ]


def test_parse_game_processes_empty_string():
    assert settings.parse_game_processes("") == []
    assert settings.parse_game_processes("   ") == []
