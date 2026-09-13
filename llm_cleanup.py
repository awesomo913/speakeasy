"""Optional LLM polish pass for SpeakEasy transcriptions.

Takes Whisper's raw transcript and returns a cleaned version: filler words
("um", "uh", "like") removed, punctuation fixed, tone applied — while
preserving code terms, camelCase identifiers, file paths, and symbols
(the coder niche Pithflow leaves open).

Design rules (match the rest of SpeakEasy):
- Stdlib only (urllib) — no new dependencies, exe build unchanged.
- NEVER loses dictation: any failure raises, and main.py falls back to the
  raw transcript. An unpolished paste always beats a lost one.
- Reads the API key + model fresh from settings on every call, so GUI
  changes apply immediately without a restart.
- Provider: OpenRouter (same key type as the image-generator MCP setup).
"""
from __future__ import annotations

import json
import threading
import traceback
import urllib.request
from collections.abc import Callable

try:
    from crash_logger import log_event
except Exception:  # pragma: no cover
    def log_event(*_args, **_kwargs):
        pass


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_S = 30

SYSTEM_PROMPT = (
    "Clean up this voice-dictation transcript for immediate use. "
    "Remove filler words (um, uh, like, you know) and false starts. "
    "Fix punctuation, capitalization, and grammar. "
    "CRITICAL: preserve code terms exactly — camelCase identifiers, "
    "function names, file paths, symbols, and technical jargon must not be "
    "'corrected' into plain English. "
    "Return ONLY the cleaned text, no quotes, no commentary."
)


def clean_sync(raw_text: str, api_key: str, model: str) -> str:
    """Polish raw_text via OpenRouter. Raises on any failure (caller falls back)."""
    if not raw_text.strip():
        return raw_text
    if not api_key.strip():
        raise ValueError("no API key configured")

    payload = json.dumps({
        "model": model.strip() or "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/awesomo913/speakeasy",
            "X-Title": "SpeakEasy",
        },
    )
    import time
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_event("failure", "llm polish request failed", {"error": str(exc)})
        raise
    try:
        polished = body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as exc:
        log_event("failure", "llm polish bad response", {"error": str(exc)})
        raise ValueError(f"unexpected API response: {str(body)[:200]}")
    log_event("perf", "llm polish",
              {"in_chars": len(raw_text), "out_chars": len(polished),
               "ms": round((time.perf_counter() - t0) * 1000), "model": model})
    if not polished:
        raise ValueError("empty polish result")
    return polished


def clean_async(
    raw_text: str,
    api_key: str,
    model: str,
    on_done: Callable[[str], None],
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """Threaded wrapper (mirrors Transcriber.transcribe_async)."""
    def _run():
        try:
            on_done(clean_sync(raw_text, api_key, model))
        except Exception as exc:
            log_event("failure", "llm polish thread error",
                      {"error": str(exc), "tb": traceback.format_exc()})
            if on_error:
                on_error(exc)

    threading.Thread(target=_run, daemon=True).start()
