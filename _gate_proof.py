"""Gate proof for SpeakEasy LLM-polish change. Exit 0 = all behaviors hold."""
import settings
import llm_cleanup

d = settings.load()
assert d["llm_cleanup"] is False, "polish must default OFF (existing behavior)"
assert d["show_dot"] is True, "dot must default ON (existing behavior)"
assert d["llm_model"] == "openai/gpt-4o-mini"

# empty/blank key must raise so main.py falls back to raw transcript
for bad_key in ("", "   "):
    try:
        llm_cleanup.clean_sync("hello world", bad_key, "openai/gpt-4o-mini")
    except ValueError:
        pass
    else:
        raise SystemExit(f"FAIL: blank key {bad_key!r} did not raise")

# blank transcript passes through untouched (never polished into nothing)
assert llm_cleanup.clean_sync("   ", "k", "m") == "   "

print("PROOF OK: defaults safe + blank-key raises + blank-text passthrough")
