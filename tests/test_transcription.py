"""Tests for transcription.py's settings resolution (no model is ever loaded)."""
import transcription


def test_configured_model_defaults_when_settings_missing(monkeypatch):
    monkeypatch.setattr(transcription, "_settings", None)
    assert transcription._configured_model() == transcription.DEFAULT_MODEL


def test_configured_model_reads_valid_setting(monkeypatch):
    class _FakeSettings:
        def load(self):
            return {"model": "medium"}

    monkeypatch.setattr(transcription, "_settings", _FakeSettings())
    assert transcription._configured_model() == "medium"


def test_configured_model_rejects_unknown_value(monkeypatch):
    class _FakeSettings:
        def load(self):
            return {"model": "gpt-5000"}

    monkeypatch.setattr(transcription, "_settings", _FakeSettings())
    assert transcription._configured_model() == transcription.DEFAULT_MODEL


def test_configured_language_auto_is_none(monkeypatch):
    class _FakeSettings:
        def load(self):
            return {"language": "auto"}

    monkeypatch.setattr(transcription, "_settings", _FakeSettings())
    assert transcription._configured_language() is None


def test_configured_language_specific_code(monkeypatch):
    class _FakeSettings:
        def load(self):
            return {"language": "de"}

    monkeypatch.setattr(transcription, "_settings", _FakeSettings())
    assert transcription._configured_language() == "de"


def test_configured_language_none_when_settings_missing(monkeypatch):
    monkeypatch.setattr(transcription, "_settings", None)
    assert transcription._configured_language() is None
