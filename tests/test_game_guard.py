"""Tests for game_guard.py's pure process-list logic (no polling thread started)."""
from game_guard import _matching_process, _normalize


def test_normalize_lowercases_and_strips():
    result = _normalize(["  Fortnite.exe ", "VALORANT.exe", ""])
    assert result == frozenset({"fortnite.exe", "valorant.exe"})


def test_normalize_drops_blank_entries():
    assert _normalize(["", "   ", None or ""]) == frozenset()


def test_matching_process_none_when_psutil_reports_nothing(monkeypatch):
    class _FakeProc:
        def __init__(self, name):
            self.info = {"name": name}

    class _FakePsutil:
        @staticmethod
        def process_iter(_attrs):
            return [_FakeProc("explorer.exe"), _FakeProc("chrome.exe")]

        NoSuchProcess = Exception
        AccessDenied = Exception

    import sys
    monkeypatch.setitem(sys.modules, "psutil", _FakePsutil)

    assert _matching_process(frozenset({"fortnite.exe"})) is None


def test_matching_process_finds_configured_process(monkeypatch):
    class _FakeProc:
        def __init__(self, name):
            self.info = {"name": name}

    class _FakePsutil:
        @staticmethod
        def process_iter(_attrs):
            return [_FakeProc("explorer.exe"), _FakeProc("FortniteClient-Win64-Shipping.exe")]

        NoSuchProcess = Exception
        AccessDenied = Exception

    import sys
    monkeypatch.setitem(sys.modules, "psutil", _FakePsutil)

    matched = _matching_process(frozenset({"fortniteclient-win64-shipping.exe"}))
    assert matched == "fortniteclient-win64-shipping.exe"
