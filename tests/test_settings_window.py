"""Pure-logic tests for the hotkey recorder in settings_window.py.

These exercise the keysym->token mapping, combo building, and validation
without ever creating a Tk widget — no window is opened in this file.
"""
from settings_window import (
    build_combo,
    is_f_key_token,
    keysym_to_token,
    validate_combo,
)


def test_letters_and_digits_map_to_lowercase_char():
    assert keysym_to_token("d") == "d"
    assert keysym_to_token("D") == "d"
    assert keysym_to_token("5") == "5"


def test_modifiers_map_to_pynput_tokens():
    assert keysym_to_token("Control_L") == "<ctrl>"
    assert keysym_to_token("Control_R") == "<ctrl>"
    assert keysym_to_token("Alt_L") == "<alt>"
    assert keysym_to_token("Shift_R") == "<shift>"
    assert keysym_to_token("Super_L") == "<cmd>"


def test_space_and_fkeys():
    assert keysym_to_token("space") == "<space>"
    assert keysym_to_token("F9") == "<f9>"
    assert keysym_to_token("F12") == "<f12>"


def test_named_keys_map_via_pynput_key_names():
    assert keysym_to_token("Return") == "<enter>"
    assert keysym_to_token("BackSpace") == "<backspace>"
    assert keysym_to_token("Left") == "<left>"


def test_escape_and_unknown_keysym_are_unmappable():
    assert keysym_to_token("Escape") is None
    assert keysym_to_token("") is None
    assert keysym_to_token("SomeVendorSpecificKey_9000") is None


def test_is_f_key_token():
    assert is_f_key_token("<f9>") is True
    assert is_f_key_token("<f1>") is True
    assert is_f_key_token("<ctrl>") is False
    assert is_f_key_token("d") is False


def test_build_combo_orders_modifiers_consistently():
    combo = build_combo({"<alt>", "<ctrl>"}, "d")
    assert combo == "<ctrl>+<alt>+d"


def test_validate_combo_requires_modifier_unless_fkey():
    ok, msg = validate_combo(set(), "d")
    assert ok is False
    assert "modifier" in msg.lower()

    ok, combo = validate_combo(set(), "<f9>")
    assert ok is True
    assert combo == "<f9>"


def test_validate_combo_accepts_normal_combo():
    ok, combo = validate_combo({"<ctrl>", "<alt>"}, "d")
    assert ok is True
    assert combo == "<ctrl>+<alt>+d"
