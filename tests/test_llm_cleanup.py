"""Tests for llm_cleanup's request-building and failure handling.

urllib.request.urlopen is mocked throughout — no real network call is made.
"""
import json

import pytest

import llm_cleanup


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_blank_key_raises_without_network(monkeypatch):
    called = {"count": 0}

    def _fail_if_called(*_args, **_kwargs):
        called["count"] += 1
        raise AssertionError("urlopen should not be called with a blank key")

    monkeypatch.setattr(llm_cleanup.urllib.request, "urlopen", _fail_if_called)

    with pytest.raises(ValueError):
        llm_cleanup.clean_sync("hello world", "  ", "openai/gpt-4o-mini")
    assert called["count"] == 0


def test_blank_text_passes_through_without_network(monkeypatch):
    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("urlopen should not be called for blank text")

    monkeypatch.setattr(llm_cleanup.urllib.request, "urlopen", _fail_if_called)

    assert llm_cleanup.clean_sync("   ", "some-key", "some-model") == "   "


def test_request_body_includes_system_prompt_and_text(monkeypatch):
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse({"choices": [{"message": {"content": "Cleaned text."}}]})

    monkeypatch.setattr(llm_cleanup.urllib.request, "urlopen", _fake_urlopen)

    result = llm_cleanup.clean_sync("um so like hello", "sk-test-key", "openai/gpt-4o-mini")

    assert result == "Cleaned text."
    assert captured["url"] == llm_cleanup.OPENROUTER_URL
    assert captured["headers"]["Authorization"] == "Bearer sk-test-key"
    messages = captured["body"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "um so like hello"}
    assert captured["body"]["model"] == "openai/gpt-4o-mini"


def test_empty_polish_result_raises(monkeypatch):
    def _fake_urlopen(req, timeout=None):
        return _FakeResponse({"choices": [{"message": {"content": "   "}}]})

    monkeypatch.setattr(llm_cleanup.urllib.request, "urlopen", _fake_urlopen)

    with pytest.raises(ValueError):
        llm_cleanup.clean_sync("hello", "sk-test-key", "some-model")


def test_malformed_response_raises(monkeypatch):
    def _fake_urlopen(req, timeout=None):
        return _FakeResponse({"unexpected": "shape"})

    monkeypatch.setattr(llm_cleanup.urllib.request, "urlopen", _fake_urlopen)

    with pytest.raises(ValueError):
        llm_cleanup.clean_sync("hello", "sk-test-key", "some-model")
